"""Contrat des regles tactiques.

Chaque regle DECLARE ses dependances de donnees (section 10.1). Le moteur refuse
au chargement toute regle dependant d'un champ non whiteliste : une regle ne peut
donc pas, par construction, consommer une donnee interdite.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..advice import CandidateAdvice
from ..context.battle_context import BattleContext
from ..context.features import Features


@dataclass
class RuleContext:
    """Tout ce qu'une regle recoit pour s'evaluer (aucun acces exterieur)."""
    battle: BattleContext
    features: Features
    knowledge: object          # KnowledgeBase (evite l'import circulaire)
    session_objective: str | None = None
    player_profile: dict | None = None
    tactical_kb: object | None = None   # TacticalKnowledgeBase (zones issues des replays)


class Rule(ABC):
    """Regle deterministe : memes entrees => memes candidats."""

    #: identifiant stable, versionne (ex: "tempo.inactivity.early").
    id: str = "abstract.rule"
    #: categorie de conseil (settings.AdviceCategory).
    category: str = ""
    #: dependances de donnees, format "EVENT_TYPE.field" ou "EVENT_TYPE".
    dependencies: tuple[str, ...] = ()
    #: si True, la regle peut etre evaluee une seule fois (ex: plan initial).
    once_per_battle: bool = False

    @abstractmethod
    def evaluate(self, rc: RuleContext) -> list[CandidateAdvice]:
        """Retourne 0..n candidats. Ne DOIT rien produire si une donnee requise
        est absente (fallback sûr, BAT-010)."""
        raise NotImplementedError
