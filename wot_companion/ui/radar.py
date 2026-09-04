"""Radar tactique : projection monde -> pixels + état à afficher.

Cœur PUR (sans Tk, sans I/O) donc testable. Le rendu graphique (tk_overlay)
consomme un `RadarState` déjà calculé.

Repère WoT : +x = est, +z = nord. Sur le radar, le nord est EN HAUT (py décroît
quand z croît). Tout ce qui est montré est soit la position PROPRE du joueur,
soit des alliés / ennemis DÉJÀ spottés (feed minimap, Fair Play), soit des zones
HISTORIQUES conseillées (jamais une présence ennemie réelle).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

XZ = Tuple[float, float]


@dataclass
class RadarProjection:
    """Convertit des coordonnées monde (x, z) en pixels d'un canvas W×H.

    Mapping 1:1 EXACT sur l'emprise (xmin..xmax, zmin..zmax) — comme la minimap du
    jeu qui remplit son carré avec les bornes de l'arène. Chaque axe est mis à
    l'échelle indépendamment (pas de marge, pas de re-carrage) pour que les
    marqueurs tombent au même endroit que sur la minimap. `pad` (>0) sert au mode
    panneau autonome ; il vaut 0 en mode overlay pour coller pile à la minimap.
    """
    xmin: float
    xmax: float
    zmin: float
    zmax: float
    width: int
    height: int
    pad: int = 0

    def __post_init__(self) -> None:
        self._sx = max(self.xmax - self.xmin, 1e-6)
        self._sz = max(self.zmax - self.zmin, 1e-6)

    def to_px(self, pos: XZ) -> Tuple[int, int]:
        x, z = pos
        inner_w = self.width - 2 * self.pad
        inner_h = self.height - 2 * self.pad
        px = self.pad + (x - self.xmin) / self._sx * inner_w
        pz = self.pad + (self.zmax - z) / self._sz * inner_h    # nord en haut
        return int(round(px)), int(round(pz))


@dataclass
class RadarZone:
    center: XZ
    radius: float
    kind: str = "good"          # good (conseillée) | danger (menace historique)
    label: str = ""


@dataclass
class RadarState:
    """Instantané à dessiner. Sérialisable (dict) pour passer au thread UI."""
    extent: Tuple[float, float, float, float]     # xmin, xmax, zmin, zmax
    own: Optional[XZ] = None
    allies: List[XZ] = field(default_factory=list)
    enemies: List[XZ] = field(default_factory=list)   # SPOTTÉS uniquement
    zones: List[RadarZone] = field(default_factory=list)
    route: List[XZ] = field(default_factory=list)     # own -> zone conseillée
    # Régions à ENTOURER (secteur/side conseillé) : (xmin, zmin, xmax, zmax) monde.
    highlights: List[Tuple[float, float, float, float]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "extent": list(self.extent),
            "own": list(self.own) if self.own else None,
            "allies": [list(a) for a in self.allies],
            "enemies": [list(e) for e in self.enemies],
            "zones": [{"center": list(z.center), "radius": z.radius,
                       "kind": z.kind, "label": z.label} for z in self.zones],
            "route": [list(p) for p in self.route],
            "highlights": [list(h) for h in self.highlights],
        }


def bbox(points: Sequence[XZ], fallback: float = 500.0
         ) -> Tuple[float, float, float, float]:
    """Emprise (xmin,xmax,zmin,zmax) d'un nuage de points, ou ±fallback si vide."""
    pts = [p for p in points if p is not None]
    if not pts:
        return (-fallback, fallback, -fallback, fallback)
    xs = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    return (min(xs), max(xs), min(zs), max(zs))


def build_radar_state(
    *,
    extent: Tuple[float, float, float, float],
    own: Optional[XZ],
    allies: Sequence[XZ],
    enemies_spotted: Sequence[XZ],
    good_zones: Sequence[RadarZone],
    danger_zones: Sequence[RadarZone] = (),
    highlights: Sequence[Tuple[float, float, float, float]] = (),
) -> RadarState:
    """Assemble l'état radar. La route relie la position propre à la 1re zone.
    `highlights` : régions monde (xmin,zmin,xmax,zmax) à entourer sur la minimap."""
    zones = list(good_zones) + list(danger_zones)
    route: List[XZ] = []
    if own is not None and good_zones:
        route = [tuple(own), tuple(good_zones[0].center)]
    return RadarState(
        extent=extent, own=(tuple(own) if own else None),
        allies=[tuple(a) for a in allies],
        enemies=[tuple(e) for e in enemies_spotted],
        zones=zones, route=route, highlights=[tuple(h) for h in highlights],
    )
