"""Modèles de la Tactical Knowledge Base V2.

Dataclasses pures (sans I/O, sans dépendance moteur), donc entièrement testables.
Chaque modèle porte sa propre validation légère : on refuse de construire une
connaissance incohérente (score hors [0,1], échantillon négatif, etc.).

Ces types représentent de la connaissance HISTORIQUE. Ils n'expriment jamais une
position ennemie réelle : voir `HistoricalThreatZone` vs le live `KnownLiveEnemy`
(ce dernier vit dans le moteur live, pas ici — séparation Fair Play §39).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, List, Optional, Tuple

XZ = Tuple[float, float]


class VehicleClass(str, Enum):
    HEAVY = "heavy"
    MEDIUM = "medium"
    LIGHT = "light"
    TD = "td"
    SPG = "spg"


class Archetype(str, Enum):
    """Archétypes tactiques (§11). La classe WoT seule est insuffisante : l'archétype
    pilote les poids d'utilité et le style de conseil."""
    # Heavy
    BREAKTHROUGH_HEAVY = "breakthrough_heavy"
    HULL_DOWN_HEAVY = "hull_down_heavy"
    SUPER_HEAVY = "super_heavy"
    SUPPORT_HEAVY = "support_heavy"
    AUTOLOADER_HEAVY = "autoloader_heavy"
    # Medium
    BRAWLER_MEDIUM = "brawler_medium"
    SNIPER_MEDIUM = "sniper_medium"
    SUPPORT_MEDIUM = "support_medium"
    FLEXIBLE_MEDIUM = "flexible_medium"
    AUTOLOADER_MEDIUM = "autoloader_medium"
    FLANKER_MEDIUM = "flanker_medium"
    # Light
    PASSIVE_SCOUT = "passive_scout"
    ACTIVE_SCOUT = "active_scout"
    HYBRID_SCOUT = "hybrid_scout"
    COMBAT_LIGHT = "combat_light"
    # TD
    SNIPER_TD = "sniper_td"
    ASSAULT_TD = "assault_td"
    SUPPORT_TD = "support_td"
    TURRETED_TD = "turreted_td"
    # Autre
    ARTILLERY = "artillery"

    @property
    def can_tank(self) -> bool:
        """Cet archétype peut-il encaisser (jouer le blindage) ?"""
        return self in _ARMORED_ARCHETYPES

    @property
    def vehicle_class(self) -> Optional[VehicleClass]:
        return _ARCHETYPE_CLASS.get(self)


_ARMORED_ARCHETYPES = frozenset({
    Archetype.BREAKTHROUGH_HEAVY, Archetype.HULL_DOWN_HEAVY, Archetype.SUPER_HEAVY,
    Archetype.SUPPORT_HEAVY, Archetype.AUTOLOADER_HEAVY,
    Archetype.BRAWLER_MEDIUM, Archetype.ASSAULT_TD,
})

_ARCHETYPE_CLASS = {
    Archetype.BREAKTHROUGH_HEAVY: VehicleClass.HEAVY,
    Archetype.HULL_DOWN_HEAVY: VehicleClass.HEAVY,
    Archetype.SUPER_HEAVY: VehicleClass.HEAVY,
    Archetype.SUPPORT_HEAVY: VehicleClass.HEAVY,
    Archetype.AUTOLOADER_HEAVY: VehicleClass.HEAVY,
    Archetype.BRAWLER_MEDIUM: VehicleClass.MEDIUM,
    Archetype.SNIPER_MEDIUM: VehicleClass.MEDIUM,
    Archetype.SUPPORT_MEDIUM: VehicleClass.MEDIUM,
    Archetype.FLEXIBLE_MEDIUM: VehicleClass.MEDIUM,
    Archetype.AUTOLOADER_MEDIUM: VehicleClass.MEDIUM,
    Archetype.FLANKER_MEDIUM: VehicleClass.MEDIUM,
    Archetype.PASSIVE_SCOUT: VehicleClass.LIGHT,
    Archetype.ACTIVE_SCOUT: VehicleClass.LIGHT,
    Archetype.HYBRID_SCOUT: VehicleClass.LIGHT,
    Archetype.COMBAT_LIGHT: VehicleClass.LIGHT,
    Archetype.SNIPER_TD: VehicleClass.TD,
    Archetype.ASSAULT_TD: VehicleClass.TD,
    Archetype.SUPPORT_TD: VehicleClass.TD,
    Archetype.TURRETED_TD: VehicleClass.TD,
    Archetype.ARTILLERY: VehicleClass.SPG,
}


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else float(x)


@dataclass
class VehicleTacticalProfile:
    """Comment un véhicule PRÉFÈRE combattre (§12). Statique, source Tankopedia +
    tag archétype. Les indices normalisés (0..1) évitent de recopier Tankopedia et
    servent directement au scoring d'ajustement char↔position."""
    vehicle_id: str
    vehicle_class: VehicleClass
    archetype: Archetype
    # Indices normalisés 0..1 (comparables entre chars).
    mobility: float = 0.5
    armor: float = 0.5
    turret_armor: float = 0.5
    gun_depression: float = 0.5
    alpha: float = 0.5
    dpm: float = 0.5
    view_range: float = 0.5
    camouflage: float = 0.5
    accuracy: float = 0.5
    shell_velocity: float = 0.5
    # Cadence : 0 = mono-coup ; >0 = barillet.
    clip: int = 1
    hp_role_value: float = 0.5   # à quel point les HP sont une ressource offensive

    def __post_init__(self) -> None:
        for f in ("mobility", "armor", "turret_armor", "gun_depression", "alpha",
                  "dpm", "view_range", "camouflage", "accuracy", "shell_velocity",
                  "hp_role_value"):
            setattr(self, f, _clamp01(getattr(self, f)))
        if self.clip < 1:
            raise ValueError("clip doit être >= 1")

    @property
    def is_autoloader(self) -> bool:
        return self.clip > 1


@dataclass
class PositionCluster:
    """Zone statistiquement efficace pour un char/archétype (§9). Agrégée depuis
    des replays. Jamais une position ennemie réelle."""
    map_id: str
    spawn: str
    phase: str
    archetype: Archetype
    center: XZ
    radius: float
    popularity: float = 0.0      # fréquence chez les bons joueurs
    effectiveness: float = 0.0
    damage_score: float = 0.0
    assist_score: float = 0.0
    survival_score: float = 0.0
    sample_size: int = 0
    confidence: float = 0.0
    vehicle_id: Optional[str] = None   # cluster spécifique à un char, sinon archétype

    def __post_init__(self) -> None:
        if self.radius < 0:
            raise ValueError("radius négatif")
        if self.sample_size < 0:
            raise ValueError("sample_size négatif")
        for f in ("popularity", "effectiveness", "damage_score", "assist_score",
                  "survival_score", "confidence"):
            setattr(self, f, _clamp01(getattr(self, f)))


@dataclass
class RouteCluster:
    """Trajet fréquent des bons joueurs (§23) : suite ordonnée de zones."""
    map_id: str
    spawn: str
    archetype: Archetype
    waypoints: List[XZ] = field(default_factory=list)
    usage_rate: float = 0.0
    performance: float = 0.0
    survival: float = 0.0
    damage: float = 0.0
    assist: float = 0.0
    sample_size: int = 0
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if self.sample_size < 0:
            raise ValueError("sample_size négatif")
        for f in ("usage_rate", "performance", "survival", "damage", "assist",
                  "confidence"):
            setattr(self, f, _clamp01(getattr(self, f)))


@dataclass(frozen=True)
class HistoricalThreatZone:
    """Zone HISTORIQUEMENT tenue par un type de char (§38/§39).

    C'est un PRIOR statistique, pas une présence. Type volontairement DISTINCT de
    tout type de position ennemie live : le moteur ne pourra jamais confondre
    « cette crête est souvent tenue par des TD » avec « un TD est ici maintenant »."""
    map_id: str
    spawn: str
    phase: str
    center: XZ
    radius: float
    threat_class: VehicleClass     # type de char qui tient souvent la zone
    frequency: float = 0.0         # fréquence historique 0..1
    sample_size: int = 0

    #: marqueur explicite du concept (jamais KNOWN_LIVE_ENEMY). ClassVar => hors __init__.
    KIND: ClassVar[str] = "HISTORICAL_THREAT_ZONE"
