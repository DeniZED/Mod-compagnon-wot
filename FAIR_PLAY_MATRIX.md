# Matrice Fair Play — WoT Companion

> Fichier versionné, à relire avant toute release majeure et à revérifier à
> chaque patch important de World of Tanks (§20.1).
>
> Références officielles :
> - Politique / mods interdits : https://worldoftanks.eu/fr/content/guide/fair_play/prohibited_mods/
> - Fair Play Update janvier 2026 : https://worldoftanks.eu/fr/news/general-news/ban-wave-jan-2026/
> - Centre officiel des mods : https://worldoftanks.eu/fr/news/general-news/mod-hub-announcement/

## Principe

Le compagnon **interprète des informations normalement disponibles au joueur** et
les transforme en conseils. Il n'est ni un aimbot, ni un pilote automatique, ni
un outil de révélation. Le respect Fair Play est appliqué **par construction**
(whitelist + validation des règles au chargement), pas en contrôle final.

## Matrice de conception (annexe B du cahier des charges)

| Information / action | Consommable par le moteur ? | Implémentation |
|----------------------|:---------------------------:|----------------|
| Carte et véhicule du joueur | **Oui** | `MAP_INFO`, `PLAYER_VEHICLE` (whitelistés) |
| HP du joueur | **Oui** | `PLAYER_HP_CHANGED` |
| Composition d'équipe au chargement | **Oui** (agrégée) | `TEAM_COMPOSITION` (classes/tiers/comptes) |
| Position d'un ennemi actuellement affichée normalement | À encadrer | non consommée en V0.1 |
| Dernière position ennemie mémorisée au-delà du client | **Non** | `ENEMY_UNSPOTTED_POSITION` → **bloqué** |
| Reload ennemi | **Non** | `ENEMY_RELOAD` → **bloqué** |
| Direction de canon ennemie cachée / laser | **Non** | `ENEMY_GUN_DIRECTION` → **bloqué** |
| Trajectoire pour localiser une arty | **Non** | `ARTY_TRAJECTORY` → **bloqué** |
| Automatisation / blocage du tir | **Non** | `AUTO_FIRE` → **bloqué** |
| Conseil « replie-toi » basé sur état propre/équipe | **Oui** | règle `retreat.flank_collapse` |
| Conseil de position initiale (carte/char/compo) | **Oui** (à faire valider globalement) | règle `plan.initial` |
| Clic / mouvement clavier ou souris automatisé | **Non** | hors produit |

## Mécanismes techniques

1. **Whitelist des événements et champs** — `wot_companion/core/fairplay/whitelist.py`.
   Seuls les types listés et leurs champs déclarés sont acceptés ; tout champ
   non listé est retiré du payload (jamais remplacé).
2. **Types explicitement interdits** — `FORBIDDEN_EVENT_TYPES`
   (`wot_companion/core/events.py`) : rejetés et journalisés.
3. **Validation des règles au chargement** — une règle qui déclare une
   dépendance vers un champ non whitelisté est **refusée** avant même de
   s'exécuter (`FairPlayFilter.validate_rule`).
4. **Mode audit** — `FairPlayFilter.report` liste les champs réellement
   consommés par type d'événement et toutes les violations
   (`run_simulation --audit`).

## Tests Fair Play (négatifs)

Voir `tests/test_fairplay.py` :

- événement interdit (`ENEMY_RELOAD`) → bloqué ;
- événement inconnu → bloqué ;
- champ banni injecté dans un événement autorisé → retiré (pas d'invention) ;
- règle dépendant d'un champ interdit → refusée au chargement ;
- rapport d'audit correct (autorisés / bloqués / champs consommés).

## Checklist avant release (§10.1, §15.3)

- [ ] Relire la politique Fair Play officielle.
- [ ] `python -m pytest tests/test_fairplay.py` au vert.
- [ ] `run_simulation --audit` : 0 violation, champs consommés attendus.
- [ ] Aucune nouvelle règle ne dépend d'une donnée hors whitelist.
- [ ] Revalider les endpoints API et leurs conditions si dépendance réseau ajoutée.
- [ ] Viser la soumission au Centre officiel des mods avant diffusion large.
