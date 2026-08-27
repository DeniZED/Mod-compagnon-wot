"""Classement d'un véhicule (tag replay) vers sa CLASSE, pour le clustering.

Le replay ne porte que le tag `nation:code` (ex. `germany:G56_E-100`), jamais la
classe. On la retrouve via une table. Deux sources, dans l'ordre :
  1. la table archétype connue (ARCHETYPE_BY_TAG) — riche mais restreinte ;
  2. une table tag->classe optionnelle fournie par l'utilisateur (JSON), pour
     étendre la couverture sans code.

Un tag non classé renvoie None : le char alimente alors les zones AGNOSTIQUES de
classe (« les gagnants jouent ici »), donc aucune donnée de replay n'est perdue.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from .models import Archetype, VehicleClass

# Table de départ tag -> archétype (l'archétype porte sa classe). Extensible.
ARCHETYPE_BY_TAG: Dict[str, Archetype] = {
    "usa:A179_Black_Rock": Archetype.HULL_DOWN_HEAVY,
    "usa:A83_T110E4": Archetype.ASSAULT_TD,
    "ussr:R132_VNII_100LT": Archetype.ACTIVE_SCOUT,
    "czech:Cz17_Vz_55": Archetype.AUTOLOADER_HEAVY,
    "germany:G185_Leopard_120_Verbessert": Archetype.SNIPER_MEDIUM,
    "germany:G165_Erich_Konzept_I": Archetype.FLEXIBLE_MEDIUM,
    "germany:G56_E-100": Archetype.SUPER_HEAVY,
    "france:F18_Bat_Chatillon25t": Archetype.AUTOLOADER_MEDIUM,
}


def archetype_of(vehicle_type: Optional[str]) -> Optional[Archetype]:
    if not vehicle_type:
        return None
    return ARCHETYPE_BY_TAG.get(vehicle_type)


class VehicleClassifier:
    """Classe un tag en VehicleClass. `extra` = table tag->classe (str) optionnelle."""

    def __init__(self, extra: Optional[Dict[str, str]] = None) -> None:
        self._extra: Dict[str, VehicleClass] = {}
        for tag, klass in (extra or {}).items():
            vc = _as_class(klass)
            if vc is not None:
                self._extra[tag] = vc

    @classmethod
    def from_json(cls, path: str | Path) -> "VehicleClassifier":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        # Accepte {"tag": "heavy", ...} ou {"classes": {"tag": "heavy"}}.
        table = data.get("classes", data) if isinstance(data, dict) else {}
        return cls(table)

    def class_of(self, vehicle_type: Optional[str]) -> Optional[VehicleClass]:
        if not vehicle_type:
            return None
        arch = ARCHETYPE_BY_TAG.get(vehicle_type)
        if arch is not None:
            return arch.vehicle_class
        return self._extra.get(vehicle_type)


def _as_class(value) -> Optional[VehicleClass]:
    try:
        return VehicleClass(str(value).lower())
    except (ValueError, AttributeError):
        return None


_DEFAULT = VehicleClassifier()


def default_class_of(vehicle_type: Optional[str]) -> Optional[VehicleClass]:
    return _DEFAULT.class_of(vehicle_type)
