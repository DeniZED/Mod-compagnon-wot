"""SituationAnalyzer : lecture MACRO de la partie (la « vraie logique »).

À la différence du placement statique (où les bons se tiennent), ce module
raisonne sur l'ÉTAT de la bataille pour décider quoi faire à cet instant :
faut-il rester, basculer vers le front, se replier/défendre, pousser ?

Entrées : uniquement des données autorisées (Fair Play) — écart numérique connu,
positions PROPRE + alliées + ennemis DÉJÀ spottés, HP, phase, temps restant.
Sortie : un `StrategicPicture` que les règles macro transforment en conseil.

100 % pur (sans I/O, sans Tk) et testable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .maps import grid_cell

XZ = Tuple[float, float]

# Rayons/bornes (mètres) calibrés pour des cartes ~1000 m.
NEAR_M = 200.0            # « proche de moi »
ACTION_FAR_M = 320.0      # au-delà : je suis LOIN du front
WIN_MARGIN = 2            # écart numérique jugé (dé)favorable
LATE_REMAIN_S = 180.0     # fin de partie : bascule cap/défense


def _centroid(points: Sequence[XZ]) -> Optional[XZ]:
    pts = [p for p in points if p is not None]
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _dist(a: Optional[XZ], b: Optional[XZ]) -> Optional[float]:
    if a is None or b is None:
        return None
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _count_near(origin: Optional[XZ], points: Sequence[XZ], radius: float) -> int:
    if origin is None:
        return 0
    n = 0
    for p in points:
        d = _dist(origin, p)
        if d is not None and d <= radius:
            n += 1
    return n


@dataclass
class StrategicPicture:
    momentum: str                         # winning / losing / even / unknown
    balance: Optional[int]                # alliés_vivants - ennemis_vivants
    allies_alive: Optional[int]
    enemies_alive: Optional[int]
    action_point: Optional[XZ]            # où ça se joue (barycentre ennemis spottés)
    action_grid: Optional[str]
    dist_to_action: Optional[float]
    enemies_near_me: int
    allies_near_me: int
    sector_calm: bool                     # plus d'ennemis proches ET loin du front
    hp_ratio: Optional[float]
    healthy: bool                         # assez de HP pour agir offensivement
    phase: str
    remaining_s: Optional[float]
    late: bool
    overextended: bool = False            # surétendu devant l'équipe (features)
    took_damage: bool = False             # a encaissé récemment (features)

    @property
    def action_direction(self) -> Optional[str]:
        return None  # rempli par le contexte appelant si besoin


def analyze(battle, features, bounds=None) -> StrategicPicture:
    own = getattr(battle, "own_pos", None)
    allies = list(getattr(battle, "ally_positions", []) or [])
    enemies = list(getattr(battle, "enemy_positions_spotted", []) or [])
    a_alive = getattr(battle, "allies_alive", None)
    e_alive = getattr(battle, "enemies_alive", None)
    hp = getattr(battle, "hp_ratio", None)
    remaining = getattr(battle, "remaining_s", None)
    bounds = bounds if bounds is not None else getattr(battle, "map_bounds", None)

    balance = None
    if a_alive is not None and e_alive is not None:
        balance = a_alive - e_alive
    momentum = "unknown"
    if balance is not None:
        if balance >= WIN_MARGIN:
            momentum = "winning"
        elif balance <= -WIN_MARGIN:
            momentum = "losing"
        else:
            momentum = "even"

    # Le front = barycentre des ennemis spottés ; à défaut, le gros de l'équipe.
    action_point = _centroid(enemies) or _centroid(allies)
    dist_to_action = _dist(own, action_point)
    enemies_near = _count_near(own, enemies, NEAR_M)
    allies_near = _count_near(own, allies, NEAR_M)
    sector_calm = (enemies_near == 0 and dist_to_action is not None
                   and dist_to_action >= ACTION_FAR_M)

    phase = getattr(features, "phase", None)
    phase_name = getattr(phase, "value", "mid") if phase is not None else "mid"
    late = (phase_name == "late") or (remaining is not None and remaining <= LATE_REMAIN_S)
    healthy = hp is None or hp >= 0.4

    return StrategicPicture(
        momentum=momentum, balance=balance, allies_alive=a_alive, enemies_alive=e_alive,
        action_point=action_point, action_grid=grid_cell(action_point, bounds),
        dist_to_action=dist_to_action, enemies_near_me=enemies_near,
        allies_near_me=allies_near, sector_calm=sector_calm, hp_ratio=hp,
        healthy=healthy, phase=phase_name, remaining_s=remaining, late=late,
        overextended=bool(getattr(features, "overextended", False)),
        took_damage=bool(getattr(features, "took_damage_recently", False)),
    )
