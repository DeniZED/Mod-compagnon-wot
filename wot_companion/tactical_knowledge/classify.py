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


_BUNDLED = Path(__file__).with_name("data") / "vehicle_classes.json"


def _load_bundled_table() -> Dict[str, str]:
    """Table tag->classe livrée avec le paquet (grossit via la capture live du
    roster). Absente/illisible -> vide (on retombe sur ARCHETYPE_BY_TAG)."""
    try:
        if _BUNDLED.is_file():
            data = json.loads(_BUNDLED.read_text(encoding="utf-8"))
            return data.get("classes", data) if isinstance(data, dict) else {}
    except (OSError, ValueError):
        pass
    return {}


_DEFAULT = VehicleClassifier(_load_bundled_table())


def default_class_of(vehicle_type: Optional[str]) -> Optional[VehicleClass]:
    return _DEFAULT.class_of(vehicle_type)


def merge_vehicle_classes(path: str | Path, new_map: Dict[str, str]) -> int:
    """Fusionne des paires tag->classe (capturées en live) dans un fichier JSON.

    N'ajoute que des classes VALIDES et non déjà présentes (la classe d'un char
    est stable). Retourne le nombre de nouvelles entrées écrites. Crée le fichier
    au format {"format":1, "classes": {...}} s'il n'existe pas.
    """
    p = Path(path)
    doc = {"format": 1, "classes": {}}
    if p.is_file():
        try:
            loaded = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                doc["classes"] = dict(loaded.get("classes", loaded))
        except (OSError, ValueError):
            pass
    classes = doc["classes"]
    added = 0
    for tag, klass in (new_map or {}).items():
        if not tag or tag in classes:
            continue
        if _as_class(klass) is None:            # classe invalide -> ignorée
            continue
        classes[tag] = _as_class(klass).value
        added += 1
    if added:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return added


def load_classifier(path: Optional[str] = None) -> VehicleClassifier:
    """Classifieur = table livrée + éventuel fichier utilisateur (prioritaire).
    Sert au build (route/zone) pour étiqueter les chars par classe."""
    table = dict(_load_bundled_table())
    if path and Path(path).is_file():
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            table.update(data.get("classes", data) if isinstance(data, dict) else {})
        except (OSError, ValueError):
            pass
    return VehicleClassifier(table)
