"""Regle de fin de partie (famille "Fin de partie", section 5.1).

Peu de chars restants -> priorite survie / vision / cap / focus. Simple en V0.1.
"""
from __future__ import annotations

from ...settings import AdviceCategory, Severity
from ..advice import CandidateAdvice
from ..context.features import BattlePhase
from .base import Rule, RuleContext


class EndgameRule(Rule):
    id = "endgame.few_left"
    category = AdviceCategory.ENDGAME.value
    dependencies = ("TEAM_COUNT.allies_alive", "TEAM_COUNT.enemies_alive")

    def evaluate(self, rc: RuleContext) -> list[CandidateAdvice]:
        f = rc.features
        if not f.endgame_few_left:
            return []
        if f.numeric_balance is None:
            return []

        if f.numeric_balance > 0:
            action, reason, key, sev = (
                "PRESS_FOCUS", "ENDGAME_ADVANTAGE", "endgame_advantage", Severity.INFO)
            urgency, impact = 0.55, 0.7
        elif f.numeric_balance < 0:
            action, reason, key, sev = (
                "PLAY_SURVIVAL", "ENDGAME_DISADVANTAGE", "endgame_survival", Severity.ATTENTION)
            urgency, impact = 0.65, 0.75
        else:
            action, reason, key, sev = (
                "PLAY_VISION_CAP", "ENDGAME_EVEN", "endgame_even", Severity.INFO)
            urgency, impact = 0.5, 0.6

        return [CandidateAdvice(
            rule_id=self.id,
            category=AdviceCategory.ENDGAME,
            action=action,
            reason_code=reason,
            template_key=key,
            severity=sev,
            ttl_seconds=8.0,
            cooldown_key="endgame",
            urgency=urgency,
            impact=impact,
            confidence=0.85,
            context={
                "allies_alive": rc.battle.allies_alive,
                "enemies_alive": rc.battle.enemies_alive,
            },
        )]
