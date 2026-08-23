"""Advice Arbiter : selectionne AU PLUS un conseil, applique l'anti-spam.

Regle d'arbitrage (section 7.2) : un conseil n'est affiche que si son score
depasse un seuil configurable et qu'aucun conseil de priorite superieure n'est
actif. Le moteur prefere le silence a un conseil faible.

L'horloge utilisee est le temps de bataille (elapsed_s) : le rejeu d'un meme
journal produit exactement les memes decisions (deterministe).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ...settings import AdviceCategory, Settings, Severity
from ..advice import AdviceObject, CandidateAdvice
from ..context.features import BattlePhase, Features
from .scorer import Scorer

_SEVERITY_RANK = {
    Severity.CRITICAL: 3, Severity.ATTENTION: 2,
    Severity.INFO: 1, Severity.POSITIVE: 0,
}
_PHASE_INTRUSION = {BattlePhase.EARLY: 0.1, BattlePhase.MID: 0.35, BattlePhase.LATE: 0.5}


@dataclass
class CooldownState:
    last_global_s: float | None = None
    last_category_s: dict[str, float] = field(default_factory=dict)
    last_rule_s: dict[str, float] = field(default_factory=dict)
    recent: list[tuple[float, str, str, str]] = field(default_factory=list)  # (t, rule, cat, action)
    early_shown: int = 0
    last_positive_s: float | None = None

    def reset(self) -> None:
        self.last_global_s = None
        self.last_category_s.clear()
        self.last_rule_s.clear()
        self.recent.clear()
        self.early_shown = 0
        self.last_positive_s = None


class AdviceArbiter:
    def __init__(self, settings: Settings, scorer: Scorer | None = None) -> None:
        self.settings = settings
        self.scorer = scorer or Scorer(settings.scoring)
        self.state = CooldownState()

    def reset(self) -> None:
        self.state.reset()

    def _repetition_factor(self, cand: CandidateAdvice, now_s: float) -> float:
        window = self.settings.anti_spam.category_cooldown_s * 1.5
        factor = 0.0
        for t, rule_id, cat, action in self.state.recent:
            if now_s - t > window:
                continue
            if rule_id == cand.rule_id and action == cand.action:
                return 1.0  # quasi-identique : penalite maximale (duplicate)
            if cat == cand.category.value:
                factor = max(factor, 0.5)
        return factor

    def _passes_cooldown(self, cand: CandidateAdvice, now_s: float, is_critical: bool) -> bool:
        a = self.settings.anti_spam
        st = self.state
        # Le cooldown de categorie s'applique TOUJOURS, y compris au critique :
        # il empeche de repeter le meme conseil tant que sa condition persiste
        # (REC-03). Un critique ne contourne que le cooldown GLOBAL et le
        # plafond early game, afin de pouvoir interrompre un conseil mineur.
        last_cat = st.last_category_s.get(cand.category.value)
        if last_cat is not None and now_s - last_cat < a.category_cooldown_s:
            return False
        if is_critical:
            return True
        if st.last_global_s is not None and now_s - st.last_global_s < a.global_cooldown_s:
            return False
        return True

    def select(
        self,
        candidates: list[CandidateAdvice],
        *,
        features: Features,
        player_profile: dict | None = None,
    ) -> AdviceObject | None:
        if not candidates:
            return None

        # Horloge = temps de bataille, injecte par le moteur via set_clock().
        now_s = self._now_s
        threshold = self.settings.effective_score_threshold()
        s = self.settings

        scored: list[tuple[float, int, CandidateAdvice, AdviceObject]] = []
        for cand in candidates:
            if not s.category_enabled(cand.category.value):
                continue
            is_critical = cand.severity is Severity.CRITICAL
            # Personnalite silencieuse : uniquement le critique.
            if s.personality.value == "silencieux" and not is_critical:
                continue

            repetition = self._repetition_factor(cand, now_s)
            intrusion = _PHASE_INTRUSION.get(features.phase, 0.3)
            breakdown = self.scorer.score(
                cand, repetition=repetition, intrusion=intrusion,
                session_objective=s.session_objective, player_profile=player_profile,
            )
            total = breakdown.total

            if total < threshold:
                continue
            if not self._passes_cooldown(cand, now_s, is_critical):
                continue
            if (features.phase is BattlePhase.EARLY and not is_critical
                    and self.state.early_shown >= s.anti_spam.max_early_advices):
                continue

            advice = AdviceObject(
                rule_id=cand.rule_id, category=cand.category.value,
                severity=cand.severity.value, score=total, action=cand.action,
                reason_code=cand.reason_code, template_key=cand.template_key,
                ttl_seconds=cand.ttl_seconds, cooldown_key=cand.cooldown_key,
                fairplay="ALLOW", breakdown=breakdown.as_dict(),
                context=dict(cand.context),
            )
            scored.append((total, _SEVERITY_RANK.get(cand.severity, 1), cand, advice))

        if not scored:
            return None

        # Un seul conseil : score le plus eleve, puis priorite de severite,
        # puis rule_id pour un tie-break deterministe (REC-02).
        scored.sort(key=lambda t: (-t[0], -t[1], t[2].rule_id))
        _, _, chosen_cand, chosen = scored[0]
        self._commit(chosen_cand, now_s, features.phase)
        return chosen

    def _commit(self, cand: CandidateAdvice, now_s: float, phase: BattlePhase) -> None:
        st = self.state
        st.last_global_s = now_s
        st.last_category_s[cand.category.value] = now_s
        st.last_rule_s[cand.rule_id] = now_s
        st.recent.append((now_s, cand.rule_id, cand.category.value, cand.action))
        if cand.category is AdviceCategory.POSITIVE:
            st.last_positive_s = now_s
        if phase is BattlePhase.EARLY and cand.severity is not Severity.CRITICAL:
            st.early_shown += 1

    # Horloge injectee par le moteur avant chaque appel a select().
    _now_s: float = 0.0

    def set_clock(self, now_s: float) -> None:
        self._now_s = now_s
