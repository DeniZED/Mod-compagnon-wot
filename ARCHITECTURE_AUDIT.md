# ARCHITECTURE_AUDIT.md — Tactical Intelligence (Étape 1)

> Livrable de l'Étape 1 du plan « Tactical Intelligence » (§23, §30).
> Objectif : cartographier l'existant, repérer les points d'intégration des
> nouvelles briques (`Sector`, `MapGraph`, `VehicleTacticalProfile`,
> `SituationState`), et proposer une migration **sans refonte massive**.

---

## 1. Pipeline actuel (vérifié dans le code)

```
RawEvent → FairPlayFilter → BattleContext.apply() → FeatureBuilder.build()
        → [Rules].evaluate(RuleContext) → CandidateAdvice[]
        → Scorer → Arbiter.select() → TextRenderer → Overlay/Radar
```

Fichiers clés et rôle réel :

| Module | Rôle | Couplage |
|---|---|---|
| `core/engine.py` | Orchestration, cycle de vie bataille, push radar | Central |
| `core/context/battle_context.py` | État normalisé (données autorisées only) | Consommé par tout |
| `core/context/features.py` | Indicateurs dérivés (phase, spatial, HP…) | Dépend de context |
| `core/rules/base.py` | Contrat `Rule` + `RuleContext` | Interface stable |
| `core/rules/registry.py` | Liste des règles actives | Point d'ajout |
| `core/strategy.py` | `StrategicPicture` + `analyze()` (lecture macro) | Consommé par strategy.macro |
| `core/actions.py` | `score_actions()` — cerveau utilité | Consommé par strategy.macro |
| `core/maps.py` | `canonical_map_id`, `grid_cell` | Utilitaires purs |
| `tactical_knowledge/models.py` | `PositionCluster`, **`VehicleTacticalProfile`**, **`Archetype`**, **`RouteCluster`**, **`HistoricalThreatZone`** | Modèles purs |
| `tactical_knowledge/store.py` | `TacticalKnowledgeBase` (index par carte, `nearest_clusters`) | Injecté dans RuleContext |
| `tactical_knowledge/classify.py` | `VehicleClassifier`, `ARCHETYPE_BY_TAG`, `default_class_of` | Build hors-ligne |

**Points forts pour la migration :**

1. **`RuleContext` est le canal d'injection idéal.** Il porte déjà
   `battle`, `features`, `knowledge`, `tactical_kb`. Ajouter un `tactical_map`
   (résolveur de secteurs) et plus tard un `situation` s'y branche sans toucher
   les règles existantes.
2. **Les règles déclarent leurs dépendances Fair Play** (`dependencies`),
   validées au chargement (`engine._load_rules`). Toute nouvelle donnée passe
   par cette whitelist → Fair Play préservé par construction.
3. **Fallback déjà culturel.** Chaque règle rend `[]` si une donnée manque. Les
   nouvelles briques suivront la même règle (carte non annotée → silence /
   repli sur l'existant).
4. **Scaffolding déjà présent.** `VehicleTacticalProfile`, `Archetype` (21
   archétypes), `RouteCluster`, `HistoricalThreatZone` existent déjà comme
   dataclasses pures. La phase V0.4 (Vehicle Intelligence) et V0.5 (Route
   mining) partent donc d'une base, pas de zéro.
5. **`BattleContext.player_sector` existe déjà** (alimenté par l'event
   `PLAYER_POSITION`), aujourd'hui une simple chaîne. Le `Sector` tactique
   viendra l'enrichir sans casser le champ.

**Couplages à respecter (à ne pas casser) :**

- `BattleContext` ne contient QUE des données autorisées. Les dérivés vont dans
  `features` / `SituationState`, jamais dans le contexte brut.
- `Features` est consommé par ~11 familles de règles + l'arbitre → on n'y
  **retire** rien ; on **ajoute** des champs optionnels.
- Le mod Python 2.7 et le contrat IPC `EventEnvelope` ne bougent pas : toute
  l'intelligence nouvelle est côté compagnon Python 3, à partir des données déjà
  reçues.

---

## 2. Limite structurelle confirmée

Le raisonnement macro (`strategy.py` / `actions.py`) s'appuie sur des
**barycentres + distances** (centre de masse allié/ennemi, `NEAR_M`,
`ACTION_FAR_M`). Aucune notion de **géographie tactique** : ville, crête,
corridor lourd, ligne de sniper, route de repli. C'est le chantier prioritaire
(§4, §28).

Le `grid_cell` donne une case (« D7 »), mais une case n'a pas de **sémantique**
(est-ce une crête ? un champ ouvert ?). Le `Sector` apporte cette sémantique.

---

## 3. Plan de migration (sans refonte)

### Étape 2 — Tactical Map Model (CE CHANTIER)

Nouveau paquet **isolé** `wot_companion/tactical_map/`, purement additif :

```
tactical_map/
  models.py     # SectorType, Sector, MapEdge, MapGraph (dataclasses pures)
  resolver.py   # SectorResolver : (map_id, pos, bounds) -> Sector | None
  data/         # annotations JSON par carte (format normalisé 0..1)
    prokhorovka.json
    ruinberg.json
```

- Coordonnées de secteur en **fractions normalisées** `(fx, fz)` des bornes
  d'arène (même convention que `grid_cell` : fx=0 ouest→1 est, fz=0 nord→1 sud).
  Robuste aux bornes exactes, indépendant de la résolution.
- `SectorResolver.resolve()` : point-dans-polygone sur coords normalisées.
  Carte inconnue / bornes absentes → `None` (fallback sur l'existant).
- **Pas de branchement** dans le moteur/règles tant que non validé (mission
  §30.8). On livre les structures + données + tests, on valide, PUIS on intègre.

### Étape 3 — Vehicle Tactical Profile

Réutiliser `VehicleTacticalProfile`/`Archetype` déjà présents. Ajouter :
- un store JSON de profils (comme `store.py` pour les clusters) ;
- un résolveur à fallback `vehicle exact → archetype → class` (§6.3).

### Étape 4 — SituationState

Agrégateur **pur** consolidant `BattleContext` + `Features` + `Sector` +
profil véhicule + force locale. Introduit à côté de `Features` (pas de
remplacement) ; les règles le consomment progressivement via `RuleContext`.

### Étape 5 — Fusion familles → signaux

Faire évoluer les familles vers des **producteurs de signaux** (danger +0.25,
survival +0.30…) agrégés par action, au lieu de messages finaux (§11). Gros
chantier : après le backtester, pour pouvoir mesurer les régressions.

### Étape 6 — Replay Backtester

Le pipeline replays (`wot_companion/replays/`) produit déjà des timelines de
position. Le backtester rejoue une bataille → `BattleState` timeline → moteur →
`Advice` timeline → métriques (§15). Indispensable AVANT tout apprentissage.

### Étapes 7-10 — Route mining, replay prior, learned utility, personal coach

Inchangé par rapport au plan. Chacune derrière une métrique de backtest.

---

## 4. Cartes pilotes retenues

Critères : iconiques, layout 3-lignes clair, apparaissent dans les parties du
joueur (tier 10/11), géographie documentée.

1. **Prokhorovka** (`prokhorovka`) — l'archétype 3 lignes : champ/ligne de sniper
   sud, crête/centre, ville nord. Cas d'école pour valider ville vs champ.
2. **Ruinberg** (`ruinberg`) — ville dense (nord-est) + champ ouvert (sud-ouest) :
   contraste corridor lourd / ligne de vue longue.

Extensible ensuite (une carte = un JSON ajouté, zéro code).

---

## 5. Risques & garde-fous

| Risque | Garde-fou |
|---|---|
| Annotations imprécises vs vraie carte | Coords normalisées + secteurs larges ; validation en jeu avant intégration |
| Casser une carte non annotée | `resolve()` → `None` → fallback sur clusters + features actuels |
| Fair Play | Aucune donnée nouvelle côté mod ; secteurs = géographie statique, jamais une position ennemie |
| Régression des 184 tests | Paquet isolé, non branché ; suite complète re-jouée à chaque étape |
| Runtime alourdi | Résolution = un point-dans-polygone sur ~10 secteurs/carte, négligeable |

---

## 6. Conclusion

L'architecture est **prête à recevoir** la couche d'intelligence tactique :
canal d'injection propre (`RuleContext`), Fair Play par construction, culture du
fallback, et scaffolding véhicule/route déjà en place. La migration se fait par
**ajouts isolés validés un par un**, sans refonte. On démarre par le Tactical
Map Model minimal (2 cartes pilotes), non branché, à valider avant intégration.
