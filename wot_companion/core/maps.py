"""Identifiant de carte canonique — pont entre replays et live.

Les replays portent le nom interne brut (`08_ruinberg`, `11_murovanka`), tandis
que le mod live envoie un nom déjà partiellement normalisé (`ruinberg`, ou brut
si inconnu). Pour que la Tactical Knowledge Base (bâtie depuis les replays) se
requête avec la position live, les DEUX côtés doivent produire la même clé.

`canonical_map_id()` est cette clé unique : minuscule, sans préfixe numérique,
alias connus appliqués. Idempotente (déjà canonique -> inchangée).
"""
from __future__ import annotations

import re
from typing import Optional

# Alias de noms internes -> clé canonique stable.
_MAP_ALIASES = {
    "prohorovka": "prokhorovka",
    "hills": "mines",              # Mines = "10_hills" en interne
}

_PREFIX = re.compile(r"^\d+_")     # préfixe "NN_" des noms internes


def canonical_map_id(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    key = str(name).strip().lower().replace("\\", "/")
    key = key.split("/")[-1]           # queue de chemin éventuel
    key = _PREFIX.sub("", key)         # retire "08_", "11_", ...
    return _MAP_ALIASES.get(key, key)


# Lignes de la grille minimap WoT : A..K en SAUTANT le "I" (10 lignes),
# du nord (haut) au sud (bas). Colonnes 1..10, d'ouest (gauche) à est (droite).
_GRID_ROWS = "ABCDEFGHJK"


def flank_label(fx: float, fz: float) -> str:
    """Côté ABSOLU de la carte pour une position normalisée (fx: 0 ouest→1 est ;
    fz: 0 nord→1 sud). Ex. « l'ouest », « le nord-est », « le centre ». Sert à
    nommer clairement un FLANC en ouverture, plutôt qu'un point relatif proche.
    """
    ew = "ouest" if fx < 0.38 else "est" if fx > 0.62 else ""
    ns = "nord" if fz < 0.38 else "sud" if fz > 0.62 else ""
    if ns and ew:
        return "le %s-%s" % (ns, ew)          # le nord-ouest
    if ew:
        return "l'%s" % ew                      # l'ouest / l'est
    if ns:
        return "le %s" % ns                     # le nord / le sud
    return "le centre"


def grid_cell(pos, bounds, cols: int = 10, sub: bool = True) -> Optional[str]:
    """Case de la grille minimap (ex. 'C4', ou 'C4-9' avec la sous-case).

    `bounds` = (minX, minZ, maxX, maxZ), les bornes de l'arène (mêmes que la
    minimap du jeu). Repère WoT : +x est, +z nord ; le nord est en haut, donc la
    ligne A est au z max. Renvoie None si les bornes sont absentes/incohérentes.

    Une case fait ~100×100 m — trop large. Avec `sub`, on ajoute le quadrant en
    notation pavé numérique WoT (7 8 9 au nord, 4 5 6 au centre, 1 2 3 au sud),
    soit une précision ~33 m : 'C4-9' = coin nord-est de C4.
    """
    if not pos or not bounds or len(bounds) != 4:
        return None
    x, z = pos[0], pos[1]
    minx, minz, maxx, maxz = bounds
    if maxx <= minx or maxz <= minz:
        return None
    rows = len(_GRID_ROWS)
    fx = (x - minx) / (maxx - minx)          # 0 (ouest) .. 1 (est)
    fz = (maxz - z) / (maxz - minz)           # 0 (nord/haut) .. 1 (sud/bas)
    ci = min(cols - 1, max(0, int(fx * cols)))
    ri = min(rows - 1, max(0, int(fz * rows)))
    cell = "%s%d" % (_GRID_ROWS[ri], ci + 1)
    if not sub:
        return cell
    # Sous-case : quadrant 3×3 dans la case, en notation pavé numérique.
    sx = min(2, max(0, int((fx * cols - ci) * 3)))          # 0 ouest .. 2 est
    sz = min(2, max(0, int((fz * rows - ri) * 3)))          # 0 nord .. 2 sud
    numpad = (2 - sz) * 3 + sx + 1
    return "%s-%d" % (cell, numpad)
