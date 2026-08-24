"""Registre des regles MVP V0.1."""
from __future__ import annotations

from .base import Rule
from .endgame import EndgameRule
from .hp_management import HpManagementRule
from .initial_plan import InitialPlanRule
from .retreat import RetreatRule
from .tempo import TempoInitiativeRule


def default_rules() -> list[Rule]:
    """Regles autorisees du MVP, dans un ordre deterministe."""
    return [
        InitialPlanRule(),
        RetreatRule(),
        HpManagementRule(),
        TempoInitiativeRule(),
        EndgameRule(),
    ]
