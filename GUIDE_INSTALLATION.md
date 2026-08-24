# Guide d'installation — WoT Companion (mod POC)

Guide complet, du téléchargement depuis GitHub jusqu'à la récupération du log de
validation. Prévu pour **Windows** (le PC de jeu). Aucune connaissance technique
requise : suis les étapes dans l'ordre.

> **But de ce premier test** : vérifier que le compagnon reçoit bien tes vraies
> données de jeu, puis me renvoyer un petit fichier de log pour que j'ajuste ce
> qui doit l'être.

---

## Étape 0 — Installer Python (une seule fois)

1. Va sur **https://www.python.org/downloads/** et clique sur le gros bouton
   *Download Python 3.x*.
2. Lance l'installeur. **Coche impérativement la case « Add python.exe to PATH »**
   en bas de la première fenêtre, puis clique *Install Now*.
3. Pour vérifier : ouvre le menu Démarrer, tape **PowerShell**, ouvre-le, et
   tape :
   ```powershell
   python --version
   ```
   Tu dois voir `Python 3.x.x`. Si tu vois une erreur, essaie `py --version`
   (et utilise `py` au lieu de `python` dans toute la suite).

---

## Étape 1 — Récupérer le projet depuis GitHub

**Option simple (sans rien installer d'autre) :**

1. Télécharge le dossier ZIP de la bonne branche via ce lien direct :
   **https://github.com/DeniZED/Mod-compagnon-wot/archive/refs/heads/claude/projet-a-realiser-gduj4y.zip**
2. Ouvre le fichier `.zip` téléchargé, puis **extrais** son contenu quelque part
   de simple, par exemple `C:\wot-companion\`.
3. Tu obtiens un dossier nommé
   `Mod-compagnon-wot-claude-projet-a-realiser-gduj4y`. C'est le dossier du
   projet.

**Option avec git** (si tu as git installé) :
```powershell
git clone -b claude/projet-a-realiser-gduj4y https://github.com/DeniZED/Mod-compagnon-wot.git
```

---

## Étape 2 — Ouvrir un terminal DANS le dossier du projet

1. Ouvre le dossier du projet dans l'Explorateur Windows (celui qui contient les
   fichiers `README.md` et `pyproject.toml`).
2. Clique dans la **barre d'adresse** de l'Explorateur, efface tout, tape
   **`powershell`** et appuie sur *Entrée*. Une fenêtre PowerShell s'ouvre,
   déjà placée dans le bon dossier.

> Garde cette fenêtre : toutes les commandes suivantes s'y tapent.

---

## Étape 3 — Test à blanc, SANS le jeu (fortement recommandé)

Ça prouve que tout le logiciel marche avant de toucher à WoT.

1. Dans ta fenêtre PowerShell, lance le compagnon :
   ```powershell
   python -m wot_companion.tools.live
   ```
   Il affiche « en écoute sur 127.0.0.1:47800 … En attente de la source ».
2. Ouvre une **2ᵉ** fenêtre PowerShell dans le même dossier (répète l'étape 2),
   et lance l'injecteur :
   ```powershell
   python -m wot_companion.tools.inject --scenarios
   ```
3. Regarde la 1ʳᵉ fenêtre : des conseils doivent s'afficher (plan initial,
   repli…). ✅ Si oui, tout le cœur fonctionne.
4. Ferme l'injecteur, et arrête le compagnon avec **Ctrl + C**.

---

## Étape 4 — Construire le mod (.wotmod)

Dans la fenêtre PowerShell du projet :
```powershell
python -m wot_companion.game_adapter.wot_mod.build_wotmod
```
Cela crée le fichier :
```
wot_companion\game_adapter\wot_mod\dist\com.wotcompanion.bridge_0.1.0.wotmod
```
C'est **ce fichier** qu'on installe dans le jeu.

---

## Étape 5 — Trouver le dossier de World of Tanks et sa version

1. Ouvre **Wargaming Game Center**, sélectionne *World of Tanks*, clique sur la
   roue crantée ⚙ → *Ouvrir le dossier du jeu* (ou va au dossier d'installation,
   souvent `C:\Games\World_of_Tanks_EU\`).
2. Note le **numéro de version** du jeu (affiché dans Game Center, ou en bas de
   l'écran de connexion du jeu), par exemple `1.27.0.0`.
3. Dans le dossier du jeu, ouvre le sous-dossier **`mods`**, puis le sous-dossier
   portant **exactement** ce numéro de version, ex. `mods\1.27.0.0\`.
   - Si le dossier `mods` ou le dossier de version n'existe pas, **crée-le**
     (le nom doit correspondre au numéro de version, au chiffre près).

---

## Étape 6 — Installer le mod

Copie le fichier construit à l'étape 4 :
```
...\wot_companion\game_adapter\wot_mod\dist\com.wotcompanion.bridge_0.1.0.wotmod
```
dans le dossier de version du jeu :
```
<Dossier World of Tanks>\mods\<version>\
```

---

## Étape 7 — Lancer et jouer

1. **D'abord** le compagnon (dans la fenêtre PowerShell du projet) :
   ```powershell
   python -m wot_companion.tools.live
   ```
   Laisse-le ouvert.
   - Si Windows affiche une alerte de pare-feu, **autorise** (le compagnon
     écoute uniquement en local, 127.0.0.1).
2. **Ensuite** lance World of Tanks normalement.
3. **Entre dans une bataille** (n'importe laquelle suffit, même en attendant au
   spawn). Le mod se connecte au compagnon et lui envoie le contexte.

---

## Étape 8 — Récupérer le log et me l'envoyer

Le mod écrit un rapport de découverte à **deux endroits** :

- Le fichier dédié **`wot_companion_discovery.log`**, dans le dossier de travail
  du jeu (généralement le dossier d'installation de WoT).
- `python.log`, ici :
  `%APPDATA%\Wargaming.net\WorldOfTanks\python.log`
  (colle ce chemin dans la barre d'adresse de l'Explorateur pour l'ouvrir).

Ouvre le fichier, repère le bloc encadré par :
```
===== DISCOVERY (start) ... =====
...
=====================================
```
et **copie-colle ce bloc dans notre conversation**. Avec ça, j'ajuste les points
de lecture du mod pour ta version exacte de WoT.

---

## En cas de souci

| Symptôme | Solution |
|----------|----------|
| `python n'est pas reconnu` | Réinstalle Python en cochant « Add to PATH » (étape 0), ou utilise `py` au lieu de `python`. |
| Le compagnon reste « En attente… » pendant une bataille | Vérifie que le `.wotmod` est bien dans `mods\<version exacte>\` ; que le compagnon a été lancé **avant** d'entrer en bataille ; cherche des lignes `[WoTCompanion]` dans `python.log`. |
| Pas de dossier `mods` | Crée-le, avec un sous-dossier au nom exact de la version du jeu. |
| Rien ne s'affiche au test à blanc (étape 3) | Vérifie que les deux fenêtres sont dans le dossier du projet et que Python 3.10+ est bien installé. |
| Après une mise à jour de WoT | Déplace le `.wotmod` dans le nouveau dossier `mods\<nouvelle version>\`. |

---

## Sécurité & Fair Play

Le mod **ne lit et n'envoie que des informations normalement disponibles au
joueur** (ta bataille, ton char, la carte, tes HP, le temps, les comptes de
véhicules). Il ne lit aucune donnée ennemie cachée et n'automatise rien. Tout
tourne **en local** sur ton PC. Détails dans
[`FAIR_PLAY_MATRIX.md`](FAIR_PLAY_MATRIX.md).

Pour **désinstaller** : supprime le fichier `.wotmod` du dossier `mods\<version>\`.
Aucune autre trace n'est laissée dans le jeu.
