# WoT Companion

Compagnon intelligent pour **World of Tanks** : coaching, aide à la décision et
progression du joueur. Le compagnon **conseille**, il n'automatise jamais les
actions du joueur, et respecte strictement la politique **Fair Play** de Wargaming.

> Implémentation du cahier des charges *WoT Companion – Cahier des charges
> fonctionnel et technique v1.0* (23/08/2026).

---

## Ce que couvre ce dépôt

Ce dépôt implémente le **cœur logiciel déterministe** du MVP V0.1 — c'est-à-dire
tout ce qui se trouve **en aval du client WoT** et qui peut être développé et
testé sans le jeu, comme le recommande la roadmap (§17.1) :

| Composant | État | Module |
|-----------|------|--------|
| Contrat d'événements + `EventEnvelope` IPC (§9.2) | ✅ | `game_adapter/` |
| **FairPlayFilter** + whitelist + audit (§10.1) | ✅ | `core/fairplay/` |
| `BattleContext` normalisé + Feature Builder (§7.1) | ✅ | `core/context/` |
| Règles tactiques (plan initial, HP, tempo, repli, fin de partie) (§5) | ✅ | `core/rules/` |
| Scoring pondéré (§7.2) + Arbitre anti-spam (§11.1) | ✅ | `core/scoring/` |
| Base de connaissances : 5 cartes, 7 archétypes, 21 plans (§7.3, §13.1) | ✅ | `knowledge/` |
| Profil / historique **SQLite** + tendances (§6, §8.1) | ✅ | `profile/` |
| Personnalités textuelles + rendu (§4.2) | ✅ | `ui/` |
| **Simulateur de batailles** (faux événements, §17.1) | ✅ | `game_adapter/simulator.py` |
| API Wargaming (optionnelle, hors ligne par défaut) (§6 GAR-006) | ✅ (stub) | `integrations/wargaming_api/` |
| Reformulation LLM (optionnelle, hors chemin critique) (§7.4) | ✅ (stub) | `integrations/llm_optional/` |
| Suite de tests + cas de recette **REC-01→REC-10** (§14) | ✅ | `tests/` |

### Ce qui reste à faire *après un POC sur le client réel*

Le **Game Adapter réel** (bridge avec le client WoT) est fourni ici sous forme
**d'interface** (`GameAdapter`) et **d'adaptateur simulé**. Son implémentation
concrète dépend d'informations qui ne peuvent être confirmées que par
expérimentation sur le client (le cahier des charges les marque « à valider par
POC »). L'architecture isole volontairement cette couche pour que **rien du
moteur ne change** quand le vrai adaptateur sera branché.

Sont également différés (conformément au périmètre §2.2) : overlay graphique
2D réel, analyse de replays, TTS, cloud/synchro.

---

## Démarrage rapide

Aucune dépendance externe pour le cœur (bibliothèque standard uniquement).
`pytest` sert aux tests ; `requests` n'est requis que pour l'API Wargaming.

```bash
# Vérifier la cohérence de la base de connaissances
python -m wot_companion.tools.kb_check

# Lancer une simulation de bout en bout (3 batailles synthétiques)
python -m wot_companion.tools.run_simulation

# Changer la personnalité et l'intensité, exporter le journal, voir l'audit Fair Play
python -m wot_companion.tools.run_simulation --personality commandant --intensity 1.3 \
    --journal journal.jsonl --audit

# Tests
pip install pytest
python -m pytest
```

Exemple de sortie (personnalité *coach*) :

```
[NORMAL]     Medium de tir a distance - Prokhorovka south. Privilegie ligne 1 ouest ...
[CRITICAL]   Ton flanc (ville) cede alors que tu as encore tes HP. Prepare un repli ...

--- Garage : synthese de session ---
  2 batailles - DPG moyen 500, assist 0.
  HP perdus tot dans 50% des parties : axe prioritaire = discipline early game.
```

---

## Tester en conditions réelles (POC)

Le compagnon reçoit ses événements via un **pont IPC socket local** (contrat
`EventEnvelope`, §9.2). Trois couches découplées : la **source** d'événements, le
**pont**, le **moteur+affichage**. On valide de la plus sûre à la plus réelle.

### 1. Chaîne complète, sans le jeu (marche tout de suite)

Deux fenêtres de terminal sur ton PC :

```bash
# Fenêtre 1 — le compagnon (écoute le pont, affiche les conseils en direct)
python -m wot_companion.tools.live

# Fenêtre 2 — un injecteur qui rejoue de vraies batailles simulées
python -m wot_companion.tools.inject --scenarios          # accéléré
python -m wot_companion.tools.inject --scenarios --realtime  # au rythme réel
```

Tu vois les conseils s'afficher live et l'historique s'écrire dans
`wot_companion.sqlite`. Cela prouve que **moteur + pont + affichage + profil**
fonctionnent de bout en bout.

### 2. Avec le vrai client WoT (le POC)

> 📘 **Guide d'installation pas à pas** (récupération GitHub, build du mod, dossier `mods`, récupération du log) :
> [`GUIDE_INSTALLATION.md`](GUIDE_INSTALLATION.md).


Un **mod WoT autonome et défensif** lit uniquement les données autorisées et les
envoie sur le pont. Il est fourni avec un mode *discovery* pour valider, champ
par champ, ce que le client expose réellement.

```bash
# Construire le paquet installable
python -m wot_companion.game_adapter.wot_mod.build_wotmod
# -> dist/com.wotcompanion.bridge_0.1.0.wotmod  (à copier dans mods/<version>/)
```

Procédure complète d'installation et de **validation des données** (définition
de fini du POC, Annexe C) :
[`wot_companion/game_adapter/wot_mod/README_MOD.md`](wot_companion/game_adapter/wot_mod/README_MOD.md).

> Le mod est marqué POC : ses points d'accroche (`# POC:`) dépendent de la
> version de WoT et s'ajustent à partir des logs `python.log` — sans jamais
> pouvoir faire planter le jeu (tout est en `try/except`).

### Mode silence en direct (BAT-008)

```bash
python -m wot_companion.tools.inject --silence   # bascule ON/OFF
```

### Progression : rapport de session & config (E8, GAR-002/003, §18)

Les préférences (personnalité, intensité, objectif) sont **persistées** dans
`wot_companion_config.json` : le compagnon les retient d'une session à l'autre.

L'historique local (SQLite) se consulte via un **rapport de session** — synthèse
multi-batailles par véhicule et par rôle, profil de coaching, axe prioritaire :

```bash
python -m wot_companion.tools.report --db wot_companion.sqlite
python -m wot_companion.tools.report --db ... --vehicle leopard_1   # filtrer
python -m wot_companion.tools.report --db ... --export diag.json    # diagnostic non sensible
python -m wot_companion.tools.report --db ... --reset               # supprimer mes données (§8.2)
```

---

## Architecture (pipeline de décision, §7.1)

```
Game Adapter (réel = POC / simulé)
   ↓ RawEvent
FairPlayFilter  ← whitelist des champs autorisés   (rejet + audit)
   ↓
BattleContext normalisé
   ↓
Feature Builder                                     (phase, équilibre, tempo…)
   ↓
Tactical Rules + Knowledge Base
   ↓ CandidateAdvice[] {urgence, impact, confiance}
Scorer (pondération §7.2)
   ↓
Advice Arbiter                                      (seuil, cooldowns, 1 seul conseil)
   ↓ AdviceObject
Text Renderer / Personality  (+ LLM optionnel)
   ↓
Overlay 2D (sink)
```

**Déterminisme (§7)** : mêmes événements + mêmes versions de règles/KB ⇒ même
recommandation. Le rejeu d'un journal reproduit exactement les décisions.

### Arborescence

```
wot_companion/
├─ game_adapter/     # interface GameAdapter, EventEnvelope, simulateur
│  ├─ ipc.py         # pont socket local (serveur + client)
│  └─ wot_mod/       # mod WoT POC (source réelle) + build .wotmod
├─ live/             # LiveRunner : pont -> moteur -> console
├─ core/
│  ├─ context/       # BattleContext + Feature Builder
│  ├─ rules/         # règles tactiques autorisées
│  ├─ scoring/       # Scorer + Arbiter (anti-spam)
│  ├─ fairplay/      # whitelist + FairPlayFilter (sécurité produit)
│  ├─ advice.py      # CandidateAdvice / AdviceObject
│  ├─ engine.py      # orchestration du pipeline
│  └─ journal.py     # journal des conseils (rejeu)
├─ knowledge/        # tanks/ maps/ tactics/ (JSON versionné) + loader
├─ profile/          # historique SQLite + tendances + profil joueur
├─ ui/               # personnalités, rendu texte, overlay (sink)
├─ integrations/     # wargaming_api/ (opt) + llm_optional/ (opt)
├─ tools/            # run_simulation, kb_check, live, inject
├─ settings.py
└─ app.py            # CompanionApp (câblage complet)
tests/               # unitaires + REC-01→REC-10
```

---

## Fair Play — au cœur de la conception

Le respect Fair Play est traité comme une **exigence de sécurité produit**, pas
comme une vérification finale (§10) :

- **Whitelist explicite** des types d'événements et des champs consommables
  (`core/fairplay/whitelist.py`). Tout ce qui n'est pas autorisé est refusé.
- Chaque **règle déclare ses dépendances de données** ; une règle qui dépend
  d'un champ non whitelisté est **refusée au chargement**.
- **Tests négatifs** : événements interdits (reload adverse, position non spot,
  direction de canon, trajectoire arty, automatisation du tir), champs bannis,
  données absentes.
- **Mode audit** : rapport des données consommées par fonction
  (`--audit`).
- La matrice de conception est versionnée dans
  [`FAIR_PLAY_MATRIX.md`](FAIR_PLAY_MATRIX.md).

Le compagnon **n'utilise aucune donnée ennemie cachée**, ne mémorise aucune
position illégitime et n'automatise aucune action.

---

## Confidentialité (§10.3)

- **Local-first** : historique en SQLite sur le PC du joueur.
- API Wargaming et LLM **désactivés par défaut**.
- Option « supprimer toutes mes données » (`HistoryStore.delete_all`).
- Aucune clé API ni donnée personnelle dans les logs.

---

## Versionnement (§12.3)

`SCHEMA_VERSION` (IPC) · `RULE_VERSION` (décisions) ·
`KNOWLEDGE_VERSION` (chars/cartes/plans) · `APP_VERSION`.
Migration SQLite versionnée via `PRAGMA user_version`.

## Licence

Propriétaire — prototype interne.
