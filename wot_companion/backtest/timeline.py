"""Timeline d'états de bataille pour le backtest + mapping action → intention.

Un `StateTick` est un instantané Fair Play de la partie à un instant t. Une
`ScenarioTimeline` en est une suite ordonnée, avec les métadonnées statiques
(carte, bornes, char). Le runner la rejoue dans le moteur.

`intent_of()` réduit une action de conseil à une INTENTION grossière (avancer /
reculer / basculer / cap…), ce qui permet de détecter contradictions et flips
sans dépendre du libellé exact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

XZ = Tuple[float, float]


@dataclass
class StateTick:
    t: float
    own: Optional[XZ] = None
    allies: List[XZ] = field(default_factory=list)
    enemies_spotted: List[XZ] = field(default_factory=list)
    hp_ratio: Optional[float] = None
    allies_alive: Optional[int] = None
    enemies_alive: Optional[int] = None
    remaining_s: Optional[float] = None


@dataclass
class ScenarioTimeline:
    map_id: Optional[str] = None
    bounds: Optional[Tuple[float, float, float, float]] = None
    vehicle_class: Optional[str] = None
    vehicle_id: Optional[str] = None
    spawn: Optional[str] = None
    ticks: List[StateTick] = field(default_factory=list)


# --- Intentions grossières -------------------------------------------------- #
ADVANCE = "ADVANCE"
RETREAT = "RETREAT"
RELOCATE = "RELOCATE"
CAP = "CAP"
CAUTION = "CAUTION"
OTHER = "OTHER"

# Intentions OPPOSÉES : leur cohabitation rapprochée = contradiction.
_OPPOSED = {(ADVANCE, RETREAT), (RETREAT, ADVANCE)}


def intent_of(action: Optional[str]) -> str:
    """Réduit un libellé d'action à une intention tactique grossière."""
    if not action:
        return OTHER
    a = action.upper()
    if a.startswith("PUSH") or "INITIATIVE" in a:
        return ADVANCE
    if "DISENGAGE" in a or "FALL_BACK" in a or "RETREAT" in a \
            or "REGROUP" in a or "OUTNUMBERED" in a:
        return RETREAT
    if "RELOCATE" in a or "REPOSITION" in a or a.startswith("OPEN") \
            or "DIRECTION" in a:
        return RELOCATE
    if "CAP" in a:
        return CAP
    if "SAFE" in a or "PRESERVE" in a:
        return CAUTION
    return OTHER


def is_contradiction(intent_a: str, intent_b: str) -> bool:
    return (intent_a, intent_b) in _OPPOSED
