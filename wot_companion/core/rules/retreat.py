"""Regle de repli (famille "Repli", section 5.1).

Correspond au scenario "Alerte tempo" du cahier des charges : le flanc du joueur
cede alors qu'il conserve la majorite de ses HP -> preparer un repli defensif.
N'utilise que des donnees autorisees : pertes alliees visibles + HP propre.
"""
from __future__ import annotations

from ...settings import AdviceCategory, Severity
from ..advice import CandidateAdvice
from ..context.features import BattlePhase
from .base import Rule, RuleContext


class RetreatRule(Rule):
    id = "retreat.flank_collapse"
    category = AdviceCategory.RETREAT.value
    dependencies = (
        "ALLY_DESTROYED.flank", "PLAYER_HP_CHANGED.hp_ratio", "TEAM_COUNT.allies_alive",
    )

    def evaluate(self, rc: RuleContext) -> list[CandidateAdvice]:
        f = rc.features
        ctx = rc.battle

        if not f.flank_collapsing:
            return []

        # Le repli n'a de sens que si le joueur a encore de quoi se replier.
        if f.hp_ratio is not None and f.hp_ratio < 0.25:
            return []

        # Signal renforce si desavantage numerique observable.
        outnumbered = f.numeric_balance is not None and f.numeric_balance < 0
        urgency = 0.8 if outnumbered else 0.6
        severity = Severity.CRITICAL if outnumbered else Severity.ATTENTION
        confidence = 0.85 if f.numeric_balance is not None else 0.6

        return [CandidateAdvice(
            rule_id=self.id,
            category=AdviceCategory.RETREAT,
            action="PREPARE_RETREAT",
            reason_code="FLANK_COLLAPSE",
            template_key="retreat_flank",
            severity=severity,
            ttl_seconds=9.0,
            cooldown_key="retreat",
            urgency=urgency,
            impact=0.85,
            confidence=confidence,
            context={
                "flank_label": rc.knowledge.flank_label(ctx.map_id, ctx.player_flank),
                "hp_pct": None if f.hp_ratio is None else round(f.hp_ratio * 100),
            },
        )]
