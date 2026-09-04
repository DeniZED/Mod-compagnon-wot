"""Modèles du Tactical Map Model (§5.1, §5.2).

Dataclasses pures, sans I/O ni dépendance moteur. Un `Sector` porte une
sémantique tactique (type + valeurs normalisées) et un polygone en coordonnées
NORMALISÉES `(fx, fz)` — fractions des bornes d'arène, convention identique à
`core.maps.grid_cell` (fx=0 ouest→1 est, fz=0 nord→1 sud). Un `MapGraph`
regroupe les secteurs d'une carte et les arêtes qui les relient.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

FXZ = Tuple[float, float]     # coordonnée normalisée (fx, fz) dans [0,1]


class SectorType(str, Enum):
    """Nature tactique d'un secteur (§5.1)."""
    HEAVY_CORRIDOR = "heavy_corridor"
    MEDIUM_FLANK = "medium_flank"
    RIDGE = "ridge"
    CITY = "city"
    OPEN_FIELD = "open_field"
    SNIPER_LINE = "sniper_line"
    SPOTTING_ZONE = "spotting_zone"
    BASE_DEFENSE = "base_defense"
    TRANSITION = "transition"
    CHOKEPOINT = "chokepoint"
    CROSSING = "crossing"


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else float(x)


@dataclass
class Sector:
    """Un secteur tactique d'une carte (§5.1).

    Le polygone est en coordonnées normalisées ; la résolution live projette la
    position (x,z) sur ces fractions via les bornes d'arène. Les valeurs 0..1
    disent à quel point le secteur convient à tel usage (hull-down, sniping,
    spotting, brawl, rotation, repli) et son exposition/couverture/risque.
    """
    id: str
    map_id: str
    sector_type: SectorType
    polygon: List[FXZ]
    tags: List[str] = field(default_factory=list)
    exposure: float = 0.5        # exposé aux lignes de vue (1 = à découvert)
    cover: float = 0.5           # disponibilité de couverture (1 = beaucoup)
    hull_down_value: float = 0.5
    sniper_value: float = 0.5
    spotting_value: float = 0.5
    brawl_value: float = 0.5
    rotation_value: float = 0.5  # facilité d'en repartir vers un autre secteur
    retreat_value: float = 0.5   # qualité comme route/zone de repli
    risk_level: float = 0.5      # dangerosité globale (1 = très risqué)

    def __post_init__(self) -> None:
        for f in ("exposure", "cover", "hull_down_value", "sniper_value",
                  "spotting_value", "brawl_value", "rotation_value",
                  "retreat_value", "risk_level"):
            setattr(self, f, _clamp01(getattr(self, f)))
        if len(self.polygon) < 3:
            raise ValueError("un secteur exige un polygone d'au moins 3 sommets")
        self.polygon = [(float(x), float(z)) for x, z in self.polygon]

    def centroid_norm(self) -> FXZ:
        """Centroïde (moyenne des sommets) en coordonnées normalisées."""
        n = len(self.polygon)
        return (sum(p[0] for p in self.polygon) / n,
                sum(p[1] for p in self.polygon) / n)

    def contains_norm(self, fx: float, fz: float) -> bool:
        """Point-dans-polygone (ray casting) en coordonnées normalisées."""
        pts = self.polygon
        n = len(pts)
        inside = False
        j = n - 1
        for i in range(n):
            xi, zi = pts[i]
            xj, zj = pts[j]
            if ((zi > fz) != (zj > fz)) and (
                fx < (xj - xi) * (fz - zi) / ((zj - zi) or 1e-12) + xi
            ):
                inside = not inside
            j = i
        return inside


@dataclass
class MapEdge:
    """Arête orientée entre deux secteurs (§5.2)."""
    from_id: str
    to_id: str
    distance: float = 0.5        # 0 (adjacent) .. 1 (traversée longue)
    exposure: float = 0.5        # exposition du trajet (1 = à découvert)
    retreat_possible: bool = True
    rotation_possible: bool = True

    def __post_init__(self) -> None:
        self.distance = _clamp01(self.distance)
        self.exposure = _clamp01(self.exposure)


@dataclass
class MapGraph:
    """Graphe tactique d'une carte : secteurs + arêtes (§5.2)."""
    map_id: str
    sectors: Dict[str, Sector] = field(default_factory=dict)
    edges: List[MapEdge] = field(default_factory=list)

    def add_sector(self, sector: Sector) -> None:
        self.sectors[sector.id] = sector

    def add_edge(self, edge: MapEdge) -> None:
        self.edges.append(edge)

    def sector(self, sector_id: str) -> Optional[Sector]:
        return self.sectors.get(sector_id)

    def neighbors(self, sector_id: str) -> List[Sector]:
        """Secteurs atteignables depuis `sector_id` (arêtes sortantes)."""
        out = []
        for e in self.edges:
            if e.from_id == sector_id and e.to_id in self.sectors:
                out.append(self.sectors[e.to_id])
        return out

    def edge_between(self, from_id: str, to_id: str) -> Optional[MapEdge]:
        for e in self.edges:
            if e.from_id == from_id and e.to_id == to_id:
                return e
        return None

    def locate_norm(self, fx: float, fz: float) -> Optional[Sector]:
        """Premier secteur contenant le point normalisé (fx, fz), ou None."""
        for s in self.sectors.values():
            if s.contains_norm(fx, fz):
                return s
        return None
