"""Scorer : convertit les signaux bruts d'un candidat en score pondere.

Composantes et bornes reprises de la section 7.2 :
  Urgence 0-30, Confiance 0-20, Impact 0-25, Contexte joueur 0-10,
  Repetition 0 a -30, Intrusion 0 a -20.
"""
from __future__ import annotations

from ...settings import AdviceCategory, ScoringWeights
from ..advice import CandidateAdvice, ScoreBreakdown

# Axe de progression (player_profile) pertinent par categorie de conseil.
_CATEGORY_TO_AXIS = {
    AdviceCategory.HP.value: "hp_preservation",
    AdviceCategory.TEMPO.value: "aggression_early",
    AdviceCategory.RETREAT.value: "survival",
    AdviceCategory.ROTATION.value: "rotation_frequency",
}

# Objectif de session -> categories renforcees.
_OBJECTIVE_TO_CATEGORIES = {
    "survie": {AdviceCategory.HP.value, AdviceCategory.RETREAT.value},
    "degats": {AdviceCategory.TEMPO.value},
    "assistance": {AdviceCategory.ROTATION.value},
    "discipline_early": {AdviceCategory.HP.value, AdviceCategory.INITIAL_PLAN.value},
}


class Scorer:
    def __init__(self, weights: ScoringWeights | None = None) -> None:
        self.w = weights or ScoringWeights()

    def score(
        self,
        candidate: CandidateAdvice,
        *,
        repetition: float = 0.0,       # 0..1 : proximite avec un conseil recent
        intrusion: float = 0.0,        # 0..1 : caractere intrusif du moment
        session_objective: str | None = None,
        player_profile: dict | None = None,
    ) -> ScoreBreakdown:
        w = self.w
        b = ScoreBreakdown()
        b.urgency = _clamp01(candidate.urgency) * w.urgency_max
        b.confidence = _clamp01(candidate.confidence) * w.confidence_max
        b.impact = _clamp01(candidate.impact) * w.impact_max
        b.player_context = self._player_context(candidate, session_objective, player_profile)
        b.repetition_penalty = -_clamp01(repetition) * w.repetition_penalty_max
        b.intrusion_penalty = -_clamp01(intrusion) * w.intrusion_penalty_max
        return b

    def _player_context(
        self, candidate: CandidateAdvice, objective: str | None, profile: dict | None
    ) -> float:
        cap = self.w.player_context_max
        value = 0.0
        cat = candidate.category.value

        if objective and cat in _OBJECTIVE_TO_CATEGORIES.get(objective, set()):
            value += cap * 0.7

        axis = _CATEGORY_TO_AXIS.get(cat)
        if profile and axis and axis in profile:
            axis_val = profile.get(axis)
            confidence = profile.get("confidence", 0.0)
            # Une faiblesse connue (valeur basse) sur un axe pertinent renforce
            # le conseil, ponderee par la confiance du profil.
            if isinstance(axis_val, (int, float)):
                weakness = max(0.0, 1.0 - float(axis_val))
                value += cap * 0.3 * weakness * float(confidence)

        return min(cap, value)


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x
