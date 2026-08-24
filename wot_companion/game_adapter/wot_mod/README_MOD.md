# WoT Companion Bridge — mod POC

Ce mod est la **source d'événements réelle** : il tourne dans World of Tanks et
transmet au compagnon externe, via un socket local, uniquement des informations
**normalement disponibles au joueur** (Fair Play garanti par construction).

> ⚙️ **Version de Python du client.** Les clients de release n'exécutent pas le
> code source `.py` embarqué dans un `.wotmod` : ils n'importent que du **bytecode
> `.pyc` compilé pour LEUR version exacte de Python**. Pour connaître cette
> version, lire le *magic number* (4 premiers octets) d'un `.pyc` d'un mod qui
> fonctionne : `03f30d0a` = Python 2.7, `550d0d0a` = Python 3.8. Compiler ensuite
> le mod avec la même version :
> ```
> python2.7 -c "import py_compile; py_compile.compile('mod_wotcompanion.py', cfile='mod_wotcompanion.pyc')"
> ```
> puis empaqueter `meta.xml` + `res/scripts/client/gui/mods/mod_wotcompanion.pyc`
> dans un ZIP **STORED** renommé `.wotmod`. La source est compatible 2.7 et 3.x.

> ⚠️ **Statut : POC.** Les points marqués `# POC:` dans `mod_wotcompanion.py`
> dépendent de l'API interne du client WoT, qui varie selon la version. Le mod
> est **défensif** (tout est en `try/except` : il ne peut pas faire planter le
> jeu) et embarque un **mode DISCOVERY** qui journalise les attributs
> disponibles dans `python.log`. On ajuste ensemble à partir de ces logs.

---

## Étape 0 — Tester SANS le jeu d'abord (recommandé)

Avant de toucher à WoT, prouve que tout le logiciel marche sur ton PC :

```bash
# Fenêtre 1 : le compagnon
python -m wot_companion.tools.live

# Fenêtre 2 : un injecteur qui rejoue des batailles réelles simulées
python -m wot_companion.tools.inject --scenarios
```

Tu dois voir les conseils s'afficher en direct dans la fenêtre 1. Si oui, le
**moteur + pont + affichage + historique** fonctionnent : il ne reste qu'à
brancher la vraie source (le mod).

---

## Étape 1 — Construire le paquet

```bash
python -m wot_companion.game_adapter.wot_mod.build_wotmod
# -> crée dist/com.wotcompanion.bridge_0.1.0.wotmod
```

## Étape 2 — Installer dans WoT

1. Repère ton dossier de jeu, p. ex. `C:\Games\World_of_Tanks_EU\`.
2. Ouvre le sous-dossier `mods\<version_du_jeu>\` (ex. `mods\1.27.0.0\`).
   Crée-le s'il n'existe pas.
3. Copies-y `com.wotcompanion.bridge_0.1.0.wotmod`.

## Étape 3 — Lancer

1. Démarre le compagnon **avant** le jeu :
   ```bash
   python -m wot_companion.tools.live
   ```
2. Lance World of Tanks et entre en bataille.
3. Le mod se connecte au compagnon (port 47800) et envoie le contexte ; les
   conseils apparaissent dans la fenêtre du compagnon.

---

## Étape 4 — Valider les données (définition de fini du POC, Annexe C)

Le mode DISCOVERY écrit un rapport **valeur par valeur** à deux moments (au
départ, puis ~6 s plus tard quand l'arène est peuplée), dans **deux endroits** :

- le fichier dédié **`wot_companion_discovery.log`** (dans le dossier de travail
  du jeu) — le plus simple à retrouver et à me coller ;
- `python.log` (`%APPDATA%\Wargaming.net\WorldOfTanks\python.log`), lignes
  `[WoTCompanion]`.

**Colle-moi le bloc `===== DISCOVERY =====`** : il contient exactement ce qu'il
me faut (nom de carte brut, descripteur du char, tags de classe, échantillon
d'`arena.vehicles`, HP/maxHP…) pour corriger les hooks et les tables de
normalisation en un seul aller-retour. Pour **chaque** donnée du POC, on note :
source, fréquence, stabilité, statut Fair Play :

| Donnée | Événement émis | À vérifier dans les logs |
|--------|----------------|--------------------------|
| Entrée/sortie de bataille | `BATTLE_START` / `BATTLE_END` | 1 paire par bataille, sans doublon |
| Char du joueur | `PLAYER_VEHICLE` | `vehicle_id`/`class` corrects |
| Carte | `MAP_INFO` | `map_id` normalisé (voir `MAP_NAME_MAP`) |
| Spawn | `SPAWN_INFO` | heuristique nord/sud à confirmer |
| Composition | `TEAM_COMPOSITION` | classes agrégées cohérentes |
| HP propre | `PLAYER_HP_CHANGED` | suit bien tes HP |
| Vivants | `TEAM_COUNT` | décroît quand des chars meurent |
| Temps | `CLOCK_TICK` | ~toutes les 2 s |

Si une donnée manque ou est fausse, copie-moi les lignes `python.log`
correspondantes : on ajuste le hook (`# POC:`) ou la table de normalisation.

Une fois les données clés **fiables et stables**, la décision **Go/No-Go MVP**
(§19) peut être prise.

---

## Réglages (en haut de `mod_wotcompanion.py`)

- `PORT` : port du compagnon (défaut 47800, doit matcher `--port` du lanceur).
- `POLL_INTERVAL_S` : cadence de lecture d'état (défaut 2 s ; impact perf faible).
- `DISCOVERY` : `True` pour journaliser les attributs (à passer à `False` une
  fois le POC validé).

## Ce que le mod NE fait jamais

Aucune lecture de reload adverse, position non spot, direction de canon,
trajectoire d'arty ; aucune automatisation du tir ou des entrées. Voir
`FAIR_PLAY_MATRIX.md` à la racine du dépôt.

## Désinstallation

Supprime le fichier `.wotmod` du dossier `mods\<version>\`. Aucune autre trace.
