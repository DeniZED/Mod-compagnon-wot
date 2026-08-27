"""Registre des regles MVP V0.1."""
from __future__ import annotations

from .base import Rule
from .endgame import EndgameRule
from .hp_management import HpManagementRule
from .initial_plan import InitialPlanRule
from .positioning import PositioningRule
from .positive import PositiveReinforcementRule
from .reaction import HitTakenReactionRule
from .retreat import RetreatRule
from .rotation import NumericAwarenessRule
from .tactical_positioning import TacticalPositioningRule
from .tempo import TempoInitiativeRule


def default_rules() -> list[Rule]:
    """Regles autorisees du MVP, dans un ordre deterministe."""
    return [
        InitialPlanRule(),
        RetreatRule(),
        HpManagementRule(),
        TempoInitiativeRule(),
        NumericAwarenessRule(),
        EndgameRule(),
        PositiveReinforcementRule(),
        HitTakenReactionRule(),
        PositioningRule(),
        TacticalPositioningRule(),
    ]
