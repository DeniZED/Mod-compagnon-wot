"""Regle de gestion des HP (famille "Gestion HP", section 5.1).

Conserver les HP ou accepter un trade selon la phase. Depend uniquement des HP
propres du joueur : information autorisee.
"""
from __future__ import annotations

from ...settings import AdviceCategory, Severity
from ..advice import CandidateAdvice
from ..context.features import BattlePhase
from .base import Rule, RuleContext

# Seuils de HP juges "trop bas trop tot" par phase.
EARLY_LOW_HP = 0.60
MID_LOW_HP = 0.35


class HpManagementRule(Rule):
    id = "hp.preservation"
    category = AdviceCategory.HP.value
    dependencies = ("PLAYER_HP_CHANGED.hp_ratio",)

    def evaluate(self, rc: RuleContext) -> list[CandidateAdvice]:
        f = rc.features
        # Fallback sûr : sans HP connu, pas de conseil (BAT-010).
        if f.hp_ratio is None:
            return []

        if f.phase is BattlePhase.EARLY and f.hp_ratio < EARLY_LOW_HP:
            deficit = (EARLY_LOW_HP - f.hp_ratio) / EARLY_LOW_HP
            severity = Severity.ATTENTION if f.hp_ratio >= 0.35 else Severity.CRITICAL
            return [CandidateAdvice(
                rule_id=self.id,
                category=AdviceCategory.HP,
                action="PRESERVE_HP",
                reason_code="EARLY_HP_LOSS",
                template_key="hp_preserve_early",
                severity=severity,
                ttl_seconds=7.0,
                cooldown_key="hp",
                urgency=min(1.0, 0.4 + deficit),
                impact=0.7,
                confidence=1.0,  # HP propre = signal fiable
                context={"hp_pct": round(f.hp_ratio * 100)},
            )]

        if f.phase is BattlePhase.MID and f.hp_ratio < MID_LOW_HP:
            return [CandidateAdvice(
                rule_id=self.id,
                category=AdviceCategory.HP,
                action="PLAY_SAFE",
                reason_code="MID_HP_LOW",
                template_key="hp_play_safe",
                severity=Severity.ATTENTION,
                ttl_seconds=7.0,
                cooldown_key="hp",
                urgency=0.5,
                impact=0.6,
                confidence=1.0,
                context={"hp_pct": round(f.hp_ratio * 100)},
            )]

        return []
