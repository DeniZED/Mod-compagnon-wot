"""Vehicle Tactical Profiles (§6, Étape 3) : « comment ce char préfère combattre ».

Le moteur ne doit plus raisonner uniquement par CLASSE. Ce module fournit un
profil tactique (indices normalisés 0..1) avec une **hiérarchie de fallback**
robuste (§6.3) :

    véhicule exact  →  archétype  →  classe  →  neutre

Chaque résolution porte sa SOURCE et une CONFIANCE (§14) : un profil exact est
plus sûr qu'un repli sur la classe. Les tables par défaut sont réglées à la main
(valeurs plausibles, comparables entre chars), extensibles par un JSON d'exacts
sans toucher au code. 100 % local, pur, testable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .classify import archetype_of, default_class_of
from .models import Archetype, VehicleClass, VehicleTacticalProfile

# Clés d'indices normalisés portées par un profil (hors identité/clip).
_INDEX_KEYS = ("mobility", "armor", "turret_armor", "gun_depression", "alpha",
               "dpm", "view_range", "camouflage", "accuracy", "shell_velocity",
               "hp_role_value")

# Confiance par source de résolution (§14).
_CONFIDENCE = {"exact": 0.9, "archetype": 0.7, "class": 0.5, "default": 0.3}

# Archétype représentatif d'une classe (pour le repli « classe » : le dataclass
# exige un archétype, on prend le plus générique de la classe).
_REPRESENTATIVE = {
    VehicleClass.HEAVY: Archetype.BREAKTHROUGH_HEAVY,
    VehicleClass.MEDIUM: Archetype.FLEXIBLE_MEDIUM,
    VehicleClass.LIGHT: Archetype.COMBAT_LIGHT,
    VehicleClass.TD: Archetype.SNIPER_TD,
    VehicleClass.SPG: Archetype.ARTILLERY,
}


def _p(mobility, armor, turret_armor, gun_depression, alpha, dpm, view_range,
       camouflage, accuracy, shell_velocity, hp_role_value, clip=1):
    """Raccourci pour déclarer un dict d'indices lisible en table."""
    return dict(mobility=mobility, armor=armor, turret_armor=turret_armor,
                gun_depression=gun_depression, alpha=alpha, dpm=dpm,
                view_range=view_range, camouflage=camouflage, accuracy=accuracy,
                shell_velocity=shell_velocity, hp_role_value=hp_role_value, clip=clip)


# Profils par ARCHÉTYPE (§6.1). Valeurs 0..1 comparables entre chars.
ARCHETYPE_PROFILES: Dict[Archetype, dict] = {
    # Heavy
    Archetype.BREAKTHROUGH_HEAVY: _p(0.50, 0.85, 0.70, 0.40, 0.70, 0.60, 0.40, 0.15, 0.50, 0.50, 0.80),
    Archetype.HULL_DOWN_HEAVY:    _p(0.45, 0.60, 0.90, 0.85, 0.65, 0.60, 0.50, 0.15, 0.65, 0.55, 0.60),
    Archetype.SUPER_HEAVY:        _p(0.25, 0.95, 0.80, 0.35, 0.85, 0.55, 0.35, 0.10, 0.45, 0.45, 0.85),
    Archetype.SUPPORT_HEAVY:      _p(0.50, 0.55, 0.60, 0.60, 0.60, 0.70, 0.50, 0.20, 0.70, 0.60, 0.50),
    Archetype.AUTOLOADER_HEAVY:   _p(0.60, 0.60, 0.60, 0.40, 0.70, 0.55, 0.45, 0.15, 0.55, 0.55, 0.60, clip=3),
    # Medium
    Archetype.BRAWLER_MEDIUM:     _p(0.70, 0.55, 0.65, 0.60, 0.60, 0.65, 0.55, 0.30, 0.60, 0.60, 0.55),
    Archetype.SNIPER_MEDIUM:      _p(0.70, 0.30, 0.40, 0.70, 0.50, 0.65, 0.70, 0.40, 0.85, 0.80, 0.35),
    Archetype.SUPPORT_MEDIUM:     _p(0.70, 0.35, 0.50, 0.65, 0.50, 0.70, 0.65, 0.40, 0.75, 0.70, 0.40),
    Archetype.FLEXIBLE_MEDIUM:    _p(0.75, 0.40, 0.50, 0.60, 0.55, 0.65, 0.65, 0.40, 0.70, 0.70, 0.45),
    Archetype.AUTOLOADER_MEDIUM:  _p(0.80, 0.35, 0.45, 0.50, 0.60, 0.50, 0.60, 0.40, 0.60, 0.65, 0.45, clip=4),
    Archetype.FLANKER_MEDIUM:     _p(0.85, 0.30, 0.45, 0.55, 0.50, 0.70, 0.65, 0.45, 0.60, 0.65, 0.40),
    # Light
    Archetype.PASSIVE_SCOUT:      _p(0.80, 0.20, 0.30, 0.50, 0.35, 0.55, 0.85, 0.85, 0.60, 0.60, 0.30),
    Archetype.ACTIVE_SCOUT:       _p(0.95, 0.20, 0.35, 0.50, 0.35, 0.55, 0.90, 0.60, 0.55, 0.60, 0.30),
    Archetype.HYBRID_SCOUT:       _p(0.90, 0.25, 0.40, 0.55, 0.40, 0.60, 0.80, 0.60, 0.60, 0.65, 0.35),
    Archetype.COMBAT_LIGHT:       _p(0.90, 0.30, 0.45, 0.50, 0.45, 0.65, 0.75, 0.50, 0.60, 0.65, 0.40),
    # TD
    Archetype.SNIPER_TD:          _p(0.40, 0.35, 0.20, 0.50, 0.80, 0.70, 0.55, 0.70, 0.90, 0.85, 0.35),
    Archetype.ASSAULT_TD:         _p(0.35, 0.80, 0.20, 0.30, 0.85, 0.65, 0.45, 0.40, 0.60, 0.60, 0.70),
    Archetype.SUPPORT_TD:         _p(0.50, 0.40, 0.30, 0.50, 0.70, 0.70, 0.55, 0.60, 0.80, 0.75, 0.40),
    Archetype.TURRETED_TD:        _p(0.55, 0.40, 0.50, 0.55, 0.75, 0.65, 0.55, 0.50, 0.80, 0.75, 0.45),
    # Artillery
    Archetype.ARTILLERY:          _p(0.35, 0.15, 0.20, 0.30, 0.90, 0.30, 0.40, 0.40, 0.40, 0.20, 0.40),
}

# Profils par CLASSE (§6.3, repli plus grossier).
CLASS_PROFILES: Dict[VehicleClass, dict] = {
    VehicleClass.HEAVY:  _p(0.45, 0.75, 0.65, 0.50, 0.70, 0.60, 0.40, 0.15, 0.55, 0.50, 0.70),
    VehicleClass.MEDIUM: _p(0.72, 0.40, 0.50, 0.60, 0.55, 0.65, 0.65, 0.40, 0.70, 0.68, 0.45),
    VehicleClass.LIGHT:  _p(0.90, 0.22, 0.35, 0.50, 0.38, 0.57, 0.85, 0.65, 0.58, 0.62, 0.32),
    VehicleClass.TD:     _p(0.42, 0.45, 0.25, 0.45, 0.80, 0.68, 0.50, 0.60, 0.82, 0.78, 0.45),
    VehicleClass.SPG:    _p(0.35, 0.15, 0.25, 0.30, 0.90, 0.30, 0.40, 0.40, 0.40, 0.20, 0.40),
}

# Profil neutre absolu (tout inconnu).
_NEUTRAL = _p(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5)


@dataclass
class ProfileResolution:
    """Résultat d'une résolution : le profil, sa source et la confiance associée."""
    profile: VehicleTacticalProfile
    source: str                 # "exact" | "archetype" | "class" | "default"
    confidence: float


def coerce_class(value) -> Optional[VehicleClass]:
    """str/enum -> VehicleClass, ou None si non reconnu."""
    if value is None:
        return None
    if isinstance(value, VehicleClass):
        return value
    try:
        return VehicleClass(str(value).lower())
    except ValueError:
        return None


def _profile(vehicle_id, vclass: VehicleClass, arch: Archetype, indices: dict) -> VehicleTacticalProfile:
    kwargs = {k: indices[k] for k in _INDEX_KEYS}
    return VehicleTacticalProfile(
        vehicle_id=vehicle_id or (arch.value if arch else vclass.value),
        vehicle_class=vclass, archetype=arch, clip=indices.get("clip", 1), **kwargs)


class VehicleProfileResolver:
    """Résout un profil tactique avec fallback exact→archétype→classe→neutre."""

    def __init__(self, exact: Optional[Dict[str, VehicleTacticalProfile]] = None) -> None:
        self._exact: Dict[str, VehicleTacticalProfile] = dict(exact or {})

    @classmethod
    def from_json(cls, path: str | Path) -> "VehicleProfileResolver":
        """Charge des profils EXACTS (overrides) depuis un JSON {tag: {indices}}."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        table = data.get("profiles", data) if isinstance(data, dict) else {}
        exact: Dict[str, VehicleTacticalProfile] = {}
        for tag, d in table.items():
            vc = coerce_class(d.get("vehicle_class")) or default_class_of(tag)
            arch = archetype_of(tag)
            if arch is None and vc is not None:
                arch = _REPRESENTATIVE.get(vc)
            if vc is None or arch is None:
                continue
            indices = {**_NEUTRAL, **{k: float(v) for k, v in d.items() if k in _INDEX_KEYS}}
            indices["clip"] = int(d.get("clip", 1))
            exact[tag] = _profile(tag, vc, arch, indices)
        return cls(exact)

    def resolve(self, vehicle_id=None, vehicle_class=None,
                archetype: Optional[Archetype] = None) -> ProfileResolution:
        """Profil tactique le plus spécifique disponible + source + confiance.

        `vehicle_id` = tag replay/live (ex. 'germany:G56_E-100') ; `vehicle_class`
        = classe live (str/enum) ; `archetype` = archétype connu (optionnel).
        """
        # 1) Profil EXACT (override JSON) par tag.
        if vehicle_id and vehicle_id in self._exact:
            return ProfileResolution(self._exact[vehicle_id], "exact", _CONFIDENCE["exact"])

        # 2) ARCHÉTYPE (fourni, ou déduit du tag).
        arch = archetype or archetype_of(vehicle_id)
        if arch is not None and arch in ARCHETYPE_PROFILES:
            vc = arch.vehicle_class or coerce_class(vehicle_class) or VehicleClass.MEDIUM
            return ProfileResolution(
                _profile(vehicle_id, vc, arch, ARCHETYPE_PROFILES[arch]),
                "archetype", _CONFIDENCE["archetype"])

        # 3) CLASSE (live, ou déduite du tag).
        vc = coerce_class(vehicle_class) or default_class_of(vehicle_id)
        if vc is not None and vc in CLASS_PROFILES:
            rep = _REPRESENTATIVE[vc]
            return ProfileResolution(
                _profile(vehicle_id, vc, rep, CLASS_PROFILES[vc]),
                "class", _CONFIDENCE["class"])

        # 4) NEUTRE absolu.
        return ProfileResolution(
            _profile(vehicle_id, VehicleClass.MEDIUM, Archetype.FLEXIBLE_MEDIUM, _NEUTRAL),
            "default", _CONFIDENCE["default"])


_DEFAULT_RESOLVER = VehicleProfileResolver()


def resolve_profile(vehicle_id=None, vehicle_class=None,
                    archetype: Optional[Archetype] = None) -> ProfileResolution:
    """Résolution via le résolveur par défaut (sans overrides exacts)."""
    return _DEFAULT_RESOLVER.resolve(vehicle_id, vehicle_class, archetype)
