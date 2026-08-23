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
├─ tools/            # run_simulation, kb_check
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
