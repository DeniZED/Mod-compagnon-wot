"""Advice Arbiter : selectionne AU PLUS un conseil, applique l'anti-spam.

Regle d'arbitrage (section 7.2) : un conseil n'est affiche que si son score
depasse un seuil configurable et qu'aucun conseil de priorite superieure n'est
actif. Le moteur prefere le silence a un conseil faible.

L'horloge utilisee est le temps de bataille (elapsed_s) : le rejeu d'un meme
journal produit exactement les memes decisions (deterministe).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ...settings import AdviceCategory, Settings, Severity
from ..advice import AdviceObject, CandidateAdvice
from ..context.features import BattlePhase, Features
from ..intent import intent_of, strategic_suppresses
from .scorer import Scorer

logger = logging.getLogger("wot_companion.arbiter")

_SEVERITY_RANK = {
    Severity.CRITICAL: 3, Severity.ATTENTION: 2,
    Severity.INFO: 1, Severity.POSITIVE: 0,
}
# Caractere intrusif du moment (penalise le score). Abaisse en milieu/fin de
# partie : c'est justement la que le joueur a besoin de reperes, et l'ancienne
# valeur etouffait tous les conseils sauf le plan initial.
_PHASE_INTRUSION = {BattlePhase.EARLY: 0.1, BattlePhase.MID: 0.22, BattlePhase.LATE: 0.35}


@dataclass
class CooldownState:
    last_global_s: float | None = None
    last_category_s: dict[str, float] = field(default_factory=dict)
    last_rule_s: dict[str, float] = field(default_factory=dict)
    recent: list[tuple[float, str, str, str]] = field(default_factory=list)  # (t, rule, cat, action)
    early_shown: int = 0
    last_positive_s: float | None = None
    # Dernière décision STRATÉGIQUE affichée (intention + instant) : sert de garde
    # de cohérence pour taire les autres familles qui la contrediraient (§11).
    last_strategic_intent: str | None = None
    last_strategic_intent_s: float | None = None

    def reset(self) -> None:
        self.last_global_s = None
        self.last_category_s.clear()
        self.last_rule_s.clear()
        self.recent.clear()
        self.early_shown = 0
        self.last_positive_s = None
        self.last_strategic_intent = None
        self.last_strategic_intent_s = None


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
        # Reaction rapide (tir recu...) : intervalle PROPRE a la regle, qui
        # court-circuite les cooldowns categorie/global pour rester reactif sans
        # bloquer les autres familles de conseils.
        if cand.min_interval_s > 0:
            last_rule = st.last_rule_s.get(cand.rule_id)
            return last_rule is None or now_s - last_rule >= cand.min_interval_s
        # Le cooldown de categorie s'applique TOUJOURS, y compris au critique :
        # il empeche de repeter le meme conseil tant que sa condition persiste
        # (REC-03). Un critique ne contourne que le cooldown GLOBAL et le
        # plafond early game, afin de pouvoir interrompre un conseil mineur.
        # Conseils positifs : desactivables, et espaces par un cooldown dedie
        # (rares par nature, section 11.1) pour rester sinceres et non intrusifs.
        if cand.category is AdviceCategory.POSITIVE:
            if not a.positive_enabled:
                return False
            if (st.last_positive_s is not None
                    and now_s - st.last_positive_s < a.positive_rare_cooldown_s):
                return False
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
        diag: list[str] = []            # trace decisionnelle (diagnostic)
        for cand in candidates:
            if not s.category_enabled(cand.category.value):
                diag.append("%s: categorie desactivee" % cand.rule_id)
                continue
            is_critical = cand.severity is Severity.CRITICAL
            # Personnalite silencieuse : uniquement le critique.
            if s.personality.value == "silencieux" and not is_critical:
                diag.append("%s: mode silencieux" % cand.rule_id)
                continue

            # Cohérence inter-familles (§11) : une décision stratégique récente
            # (décrocher/pousser/cap) fait taire les autres familles dont
            # l'intention la contredirait. La famille STRATEGY reste libre de
            # réviser sa propre décision (elle est l'ancre, pas suppressible).
            if self._contradicts_strategic(cand, now_s):
                diag.append("%s: incoherent avec strat '%s'"
                            % (cand.rule_id, self.state.last_strategic_intent))
                continue

            # Les reactions gerent leur propre cadence (min_interval_s) : on ne
            # leur applique pas la penalite de repetition, sinon elles ne
            # pourraient jamais se repeter sous le feu.
            repetition = 0.0 if cand.min_interval_s > 0 \
                else self._repetition_factor(cand, now_s)
            intrusion = _PHASE_INTRUSION.get(features.phase, 0.3)
            breakdown = self.scorer.score(
                cand, repetition=repetition, intrusion=intrusion,
                session_objective=s.session_objective, player_profile=player_profile,
            )
            total = breakdown.total

            if total < threshold:
                diag.append("%s: score %.1f < seuil %.1f (rep=%.1f)"
                            % (cand.rule_id, total, threshold, repetition))
                continue
            if not self._passes_cooldown(cand, now_s, is_critical):
                diag.append("%s: score %.1f mais cooldown" % (cand.rule_id, total))
                continue
            if (features.phase is BattlePhase.EARLY and not is_critical
                    and self.state.early_shown >= s.anti_spam.max_early_advices):
                diag.append("%s: score %.1f mais plafond early" % (cand.rule_id, total))
                continue
            diag.append("%s: score %.1f ELIGIBLE" % (cand.rule_id, total))

            advice = AdviceObject(
                rule_id=cand.rule_id, category=cand.category.value,
                severity=cand.severity.value, score=total, action=cand.action,
                reason_code=cand.reason_code, template_key=cand.template_key,
                ttl_seconds=cand.ttl_seconds, cooldown_key=cand.cooldown_key,
                fairplay="ALLOW", breakdown=breakdown.as_dict(),
                context=dict(cand.context),
            )
            scored.append((total, _SEVERITY_RANK.get(cand.severity, 1), cand, advice))

        # Diagnostic : quand une regle SURVEILLEE est candidate mais non retenue,
        # trace (throttle) qui a gagne et pourquoi les autres ont ete recales.
        self._log_decision(candidates, scored, diag, now_s)

        if not scored:
            return None

        # Un seul conseil : score le plus eleve, puis priorite de severite,
        # puis rule_id pour un tie-break deterministe (REC-02).
        scored.sort(key=lambda t: (-t[0], -t[1], t[2].rule_id))
        _, _, chosen_cand, chosen = scored[0]
        self._commit(chosen_cand, now_s, features.phase)
        return chosen

    _WATCH = "positioning.replay_zones"
    _diag_last_s: float = -999.0

    def _log_decision(self, candidates, scored, diag, now_s: float) -> None:
        if not logger.isEnabledFor(logging.INFO):
            return
        watched = any(c.rule_id == self._WATCH for c in candidates)
        chosen = scored and min(scored, key=lambda t: (-t[0], -t[1], t[2].rule_id))
        chosen_is_watch = chosen and chosen[2].rule_id == self._WATCH
        # On ne trace que si la regle surveillee perd (sinon bruit), throttle 15 s.
        if not watched or chosen_is_watch:
            return
        if now_s - self._diag_last_s < 15.0:
            return
        self._diag_last_s = now_s
        win = chosen[2].rule_id if chosen else "aucun"
        logger.info("ARBITRE t=%.0f: %s recale. Gagnant=%s | %s",
                    now_s, self._WATCH, win, " ; ".join(diag))

    def _contradicts_strategic(self, cand: CandidateAdvice, now_s: float) -> bool:
        """Vrai si `cand` (hors STRATEGY) contredit une décision stratégique
        encore fraîche — garde de cohérence inter-familles (§11)."""
        st = self.state
        window = self.settings.anti_spam.coherence_window_s
        if window <= 0 or st.last_strategic_intent is None:
            return False
        if cand.category is AdviceCategory.STRATEGY:
            return False           # l'ancre peut réviser sa propre décision
        if st.last_strategic_intent_s is None \
                or now_s - st.last_strategic_intent_s > window:
            return False
        return strategic_suppresses(st.last_strategic_intent, intent_of(cand.action))

    def _commit(self, cand: CandidateAdvice, now_s: float, phase: BattlePhase) -> None:
        st = self.state
        st.last_global_s = now_s
        st.last_category_s[cand.category.value] = now_s
        st.last_rule_s[cand.rule_id] = now_s
        st.recent.append((now_s, cand.rule_id, cand.category.value, cand.action))
        if cand.category is AdviceCategory.POSITIVE:
            st.last_positive_s = now_s
        # Mémorise l'intention stratégique pour le garde de cohérence.
        if cand.category is AdviceCategory.STRATEGY:
            st.last_strategic_intent = intent_of(cand.action)
            st.last_strategic_intent_s = now_s
        if phase is BattlePhase.EARLY and cand.severity is not Severity.CRITICAL:
            st.early_shown += 1

    # Horloge injectee par le moteur avant chaque appel a select().
    _now_s: float = 0.0

    def set_clock(self, now_s: float) -> None:
        self._now_s = now_s
