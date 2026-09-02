# WoT Companion — État des lieux (pour revue externe)

> Document de synthèse destiné à solliciter des idées d'amélioration.
> Il décrit ce qu'est le projet, comment il est construit, son niveau de
> performance actuel, ses limites connues et les questions ouvertes.

---

## 1. Concept & contrainte fondatrice

**WoT Companion** est un *overlay de coaching tactique* pour World of Tanks. Il
**conseille**, il **n'automatise jamais** (pas de bot, pas d'aim, pas d'input
envoyé au jeu). L'humain garde 100 % des décisions.

**Contrainte Fair Play absolue** (fil rouge de toute l'architecture) :

- Le mod ne lit **que des données autorisées** : position PROPRE du joueur,
  positions des ALLIÉS, positions des ennemis **déjà spottés**, HP, phase, temps
  restant, écart numérique (alliés vivants vs ennemis vivants).
- **Jamais** de position d'ennemi non spotté. On ne confond jamais un
  « ennemi live connu » avec une « zone de menace historique ».
- La base de connaissance tactique est **statistique et hors-ligne** (agrégée
  depuis des replays) — jamais une position ennemie temps-réel.
- Aucun scraping de service payant/propriétaire.
- Le mod ne peut jamais faire planter le jeu (tout en `try/except`, défensif).

Testé sur client réel : WoT EU, résolution ultrawide 3440×1440.

---

## 2. Architecture (3 couches découplées)

```
┌─────────────┐   IPC socket    ┌──────────────────────────┐   overlay Tk
│  Mod WoT    │  TCP 127.0.0.1  │   Compagnon (Python 3)   │  ┌───────────┐
│ (Python 2.7 │ ──────────────> │  moteur + règles +       │->│ mascotte  │
│  .pyc dans  │  EventEnvelope  │  arbitre + rendu         │  │ + bulle   │
│  le client) │  (JSON)         │                          │  ├───────────┤
└─────────────┘                 └──────────────────────────┘  │ radar     │
   lit données          reconnexion auto 3 s                   │ (minimap) │
   autorisées                                                  └───────────┘
```

- **Mod** (`game_adapter/wot_mod/`) : compilé en `.pyc` (magic Python 2.7),
  packagé en `.wotmod`. Client TCP qui se reconnecte seul toutes les 3 s → pas
  besoin de relancer le jeu pour (re)lancer le compagnon.
- **Pont IPC** : le compagnon est serveur TCP local (127.0.0.1:47800), le mod est
  client. Contrat `EventEnvelope` (JSON).
- **Compagnon** : moteur d'événements → contexte de bataille → features →
  règles → arbitre → rendu (overlay mascotte + radar). 100 % local, rien sur le
  réseau. ~8 600 lignes Python, 184 tests unitaires verts.

---

## 3. Base de connaissance tactique (replays → zones)

Le point fort « data » du projet.

- Pipeline de décodage de replays `.wotreplay` : Blowfish ECB + XOR-feedback +
  zlib, vectorisé numpy. Extraction des paquets de position (type 10).
- **12 999 replays exploités** → **181 074 zones** agrégées sur **72 cartes**.
- Modèle : `PositionCluster` indexé par
  `(carte, spawn, phase, classe_de_char)`, avec un *fallback class-agnostic* pour
  les chars non classifiés.
- Chaque zone porte : centre, rayon, popularité (% des références qui y sont),
  efficacité, scores dégâts/assist/survie, taille d'échantillon, confiance.
- La règle de placement compare la position live du joueur aux zones où les
  **meilleurs joueurs** performent (même carte, même phase, même classe) et
  suggère une **direction + case de grille minimap** (ex. « D7-2 »).

Grille minimap : colonnes 1–10, lignes `ABCDEFGHJK` (saute I), + sous-quadrant
pavé numérique (7-8-9 nord, 1-2-3 sud) → précision ~33 m dans une case de 100 m.

---

## 4. Le « cerveau tactique » : scoring d'actions par utilité

Refonte récente et cœur de la logique macro. Au lieu d'une échelle de priorités
figée (si A sinon si B…), on **note un jeu fixe d'actions candidates** par une
**utilité (valeur attendue)** dérivée de l'état de partie, et la meilleure gagne.
Si « TENIR » gagne → **silence** (pas de conseil superflu).

Actions candidates :

| Action        | Se déclenche quand…                                            |
|---------------|----------------------------------------------------------------|
| `HOLD`        | équilibré, en forme, au contact → **on se tait**               |
| `RELOCATE`    | secteur nettoyé + pas en défaveur → bascule vers le front      |
| `PUSH`        | avantage numérique + en forme + engagé → presser               |
| `REGROUP`     | léger sous-nombre (−2) → regrouper vers l'axe fort             |
| `FALL_BACK`   | sous-nombre net (−3+) → repli défensif / base                  |
| `DISENGAGE`   | HP bas (<45 %) + exposé → décrocher MAINTENANT (case de repli) |
| `GO_CAP`      | fin de partie + avantage + peu d'ennemis → conclure au cap     |

Chaque utilité est une **somme de contributions explicites bornée [0,1]**
(transparente, testable). Entrées = uniquement l'état lu en Fair Play. La sortie
est traduite en conseil concret (direction cardinale + case de grille).

---

## 5. Familles de règles & arbitrage

**Familles de règles** (chacune propose des conseils candidats) :
`initial_plan` (ouverture), `positioning.replay_zones` (zones de replays),
`positioning.spatial` (menace/isolement/surextension live), `strategy.macro`
(le cerveau ci-dessus), `reaction` (tir reçu), `hp_management`, `rotation`,
`retreat`, `endgame`, `tempo`, `positive`.

**Arbitre** : sélectionne **au plus UN** conseil par cycle. Chaque candidat reçoit
un score par somme pondérée :

- urgence (0–30), confiance (0–20), impact (0–25), contexte joueur (0–10)
- pénalité de répétition (0 à −30), pénalité d'intrusion selon la phase (0 à −20)

Puis filtres anti-spam :
- seuil de score minimal = 38, **modulé par l'intensité** (0 rare → 1.5 bavard ;
  facteur = 1.5 − intensité/2, donc en bavard le seuil descend ~28)
- cooldown global 12 s (entre deux conseils quelconques)
- cooldown de catégorie 45 s (empêche de répéter la même famille)
- plafond de 3 conseils en tout début de partie (hors critique)

Le moteur **préfère le silence** à un conseil faible.

---

## 6. Interface

- **Overlay mascotte** (Tkinter, transparent, sans bordure, click-through,
  toujours au-dessus) : char cartoon 12 visages (condition selon HP × expression
  selon le conseil) + bulle de texte. 4 **personnalités** (coach / commandant /
  détendu / silencieux) qui reformulent chaque conseil.
- **Radar tactique** (2ᵉ fenêtre transparente calée SUR la minimap) : marqueurs
  des zones conseillées, projection 1:1 exacte des bornes d'arène, taille =
  fraction de la hauteur d'écran. Se vide au retour garage / à la mort.
- Config persistante (`wot_companion_config.json`), historique local SQLite,
  rapport de session multi-batailles.

---

## 7. Niveau de performance actuel (tests en jeu réels)

**Ce qui marche bien**, validé sur logs de parties réelles (tier 10/11) :

- Le cerveau tactique déclenche les bonnes actions au bon moment : bascule
  quand le secteur est mort, poussée sur avantage, repli/défense sur sous-nombre,
  cap en fin de partie, décrochage précis (avec case de repli) à bas HP.
- Cadence saine : ~7 conseils macro sur une partie de 9 min, bien espacés, pas de
  spam. Le silence est respecté quand rien d'utile à dire.
- Conseils de placement issus des replays pertinents et **actionnables** (case de
  grille précise, pas juste une direction).
- Alignement radar sur la minimap satisfaisant, position joueur ~correcte.
- Robustesse : 0 crash, 0 erreur dans les logs, mod défensif, reconnexion auto.

**Corrections récentes issues des retours en jeu :**

- Faux positif de surextension (« devant la team » alors qu'à côté) → projection
  sur l'axe équipe→ennemi.
- Repli trop alarmiste dès −2 → distinction regroupement (−2) vs défense (−3+).
- **Incohérence à bas HP** : à 7 % de PV, le macro disait « décroche » pendant
  que la règle de placement disait « repositionne-toi au front » → les zones de
  replay se taisent désormais sous 30 % de PV (la survie prime).
- Commentaires après la mort supprimés ; direction d'ouverture en début de
  partie ajoutée.

**Estimation subjective du niveau** : le compagnon donne des conseils *corrects et
non trompeurs* la plupart du temps, avec une bonne discipline anti-spam. Il n'est
pas encore au niveau « meilleure décision qu'un très bon joueur » — c'est le
palier visé pour un déploiement réel.

---

## 8. Limites connues / problèmes ouverts

1. **Redondance inter-familles.** À bas HP, plusieurs familles disent la même
   chose sous des mots différents (réaction « décroche », HP « passe en soutien »,
   macro « décroche vers X »). L'arbitre n'en montre qu'un par cycle, mais sur la
   durée le joueur voit 3 variantes. Fusion à faire.

2. **Pas de notion d'axes de carte / flancs structurés.** Le raisonnement macro
   s'appuie sur des barycentres (centre de masse allié/ennemi) et des distances,
   pas sur une compréhension « flanc gauche / ville / colline / passage à
   découvert » propre à chaque carte. Le point d'action = barycentre des ennemis
   spottés, ce qui est grossier.

3. **Pas de modèle de la valeur d'échange.** Le compagnon ne sait pas si un trade
   est rentable (mon canon vs le sien, mon blindage, reload), seulement des
   heuristiques HP/nombre.

4. **Calibrage des utilités empirique.** Les poids des fonctions d'utilité sont
   réglés à la main d'après quelques parties, pas appris sur données.

5. **Base de replays sous-exploitée.** On en tire des zones de placement, mais pas
   de séquences (itinéraires typiques, timings de rotation, où le jeu bascule).

6. **Classe de char seulement.** Pas de prise en compte du char précis (blindage,
   vue, camo, DPM) ni du line-up de la partie.

7. **Pas d'évaluation quantitative.** On juge « à l'œil » sur les logs ; pas de
   métrique objective de qualité des conseils (ex. rejouer un replay et scorer si
   le conseil aurait aidé).

8. **LLM non central (par choix).** Un LLM pourrait reformuler/expliquer mais ne
   doit jamais piloter la tactique (latence, hallucination, Fair Play).

---

## 9. Questions ouvertes (pour la revue)

- Comment passer d'un raisonnement « barycentres + distances » à une **lecture de
  carte structurée** (flancs, axes, key positions) tout en restant Fair Play et
  léger (pas d'ennemi non spotté) ?
- Comment **apprendre** les poids d'utilité (ou une politique) depuis les 13 000
  replays, plutôt que de les régler à la main — sans sur-apprendre le style des
  joueurs de la base ?
- Quelle **métrique d'évaluation** objective mettre en place pour mesurer si un
  conseil est bon (backtest sur replays : « à cet instant, le conseil X
  correspond-il à ce qu'a fait le top joueur / au résultat ») ?
- Comment **fusionner les familles de règles** redondantes en un message unique et
  cohérent par situation, sans perdre la réactivité (tir reçu) ?
- Vaut-il mieux enrichir le modèle heuristique (features de trade, de timing) ou
  basculer vers un modèle appris (ex. petit réseau / arbre) scoré hors-ligne ?
- Comment exploiter les **séquences** des replays (itinéraires, moments de
  bascule) plutôt que seulement des nuages de points de position ?

---

## 10. Stack technique (résumé)

- Python 3 (compagnon), Python 2.7 (mod, `.pyc` / `.wotmod`).
- Tkinter (overlay, zéro dépendance supplémentaire côté client).
- numpy (décodage replays vectorisé).
- SQLite (historique local).
- Pas de dépendance réseau, pas de service externe, tout local-first.
- 184 tests unitaires (pytest) verts. ~8 600 lignes.
