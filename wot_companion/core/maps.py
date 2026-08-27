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
