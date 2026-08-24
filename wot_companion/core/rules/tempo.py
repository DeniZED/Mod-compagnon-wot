"""Regle de tempo (famille "Tempo", section 5.1).

Detecte une fenetre sans contribution alors que l'equilibre numerique le permet,
et invite a prendre l'initiative. Base sur le temps sans degats/assist (propre)
et l'equilibre numerique observable.
"""
from __future__ import annotations

from ...settings import AdviceCategory, Severity
from ..advice import CandidateAdvice
from ..context.features import BattlePhase
from .base import Rule, RuleContext

INACTIVITY_THRESHOLD_S = 75.0


class TempoInitiativeRule(Rule):
    id = "tempo.inactivity.early"
    category = AdviceCategory.TEMPO.value
    dependencies = (
        "PLAYER_DAMAGE_DEALT.total_damage", "PLAYER_ASSIST.total_assist",
        "CLOCK_TICK.elapsed_s",
    )

    def evaluate(self, rc: RuleContext) -> list[CandidateAdvice]:
        f = rc.features
        ctx = rc.battle

        # Fallback sûr : sans donnee de contribution (l'adaptateur ne fournit ni
        # degats ni assist), on ne peut PAS juger l'inactivite -> silence.
        # Evite un faux positif "tu ne contribues pas" quand la donnee manque.
        if not ctx.contribution_seen:
            return []
        # Pas de conseil de tempo en fin de partie : la priorite devient survie.
        if f.phase is BattlePhase.LATE:
            return []
        # Fenetre d'inactivite insuffisante -> silence.
        if f.time_since_contribution_s < INACTIVITY_THRESHOLD_S:
            return []
        # Ne pas pousser a l'initiative si le joueur est en inferiorite numerique.
        if f.numeric_balance is not None and f.numeric_balance < 0:
            return []
        # Ne pas pousser si le joueur est deja bas en HP (coherence avec regle HP).
        if f.hp_ratio is not None and f.hp_ratio < 0.4:
            return []

        over = f.time_since_contribution_s - INACTIVITY_THRESHOLD_S
        urgency = min(1.0, 0.35 + over / 120.0)
        # Confiance : renforcee si on connait l'equilibre numerique.
        confidence = 0.8 if f.numeric_balance is not None else 0.55

        return [CandidateAdvice(
            rule_id=self.id,
            category=AdviceCategory.TEMPO,
            action="TAKE_INITIATIVE",
            reason_code="LOW_CONTRIBUTION_WINDOW",
            template_key="tempo_take_initiative",
            severity=Severity.INFO,
            ttl_seconds=8.0,
            cooldown_key="tempo",
            urgency=urgency,
            impact=0.5,
            confidence=confidence,
            context={"idle_s": round(f.time_since_contribution_s)},
        )]
