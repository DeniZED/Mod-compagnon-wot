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


# Intentions : source unique dans core.intent (partagée avec l'arbitre).
from ..core.intent import (  # noqa: E402,F401
    ADVANCE, CAP, CAUTION, OTHER, RELOCATE, RETREAT,
    intent_of, is_contradiction)
