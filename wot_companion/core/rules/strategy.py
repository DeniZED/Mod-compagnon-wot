"""Règle MACRO : la « vraie logique » de décision (où aller, quoi faire).

Au-dessus du placement statique (`positioning.replay_zones`, « où les bons se
tiennent »), cette règle lit l'ÉTAT de la partie via `SituationAnalyzer`, puis
DÉLÈGUE la décision au scoreur d'actions (`core.actions.score_actions`) : chaque
action candidate (tenir / basculer / pousser / défendre / cap / décrocher) reçoit
une utilité, la meilleure l'emporte. Si c'est TENIR (HOLD), on se tait.

C'est le « cerveau tactique » : plus d'échelle de priorités figée, mais une
valeur attendue par action selon la situation. L'humain garde la décision finale ;
le compagnon ne fait que recommander l'option la mieux notée.

Fair Play : n'exploite que l'écart numérique connu, la position PROPRE, celles des
alliés et des ennemis DÉJÀ spottés. Aucune position d'ennemi non spotté.
"""
from __future__ import annotations

import math

from ...settings import AdviceCategory, Severity
from ..actions import TacticalAction, score_actions
from ..advice import CandidateAdvice
from ..context.features import BattlePhase
from ..maps import grid_cell
from ..strategy import analyze
from .base import Rule, RuleContext

# Marge d'utilité qu'une action doit avoir SUR « tenir » pour valoir un conseil :
# sous ce seuil, l'écart est trop mince pour déranger le joueur.
_HOLD_MARGIN = 0.10
# Distance (m) projetée pour matérialiser un point de repli derrière soi.
_RETREAT_M = 180.0

_DIRS = [
    (0.0, "au nord"), (45.0, "au nord-est"), (90.0, "a l'est"),
    (135.0, "au sud-est"), (180.0, "au sud"), (225.0, "au sud-ouest"),
    (270.0, "a l'ouest"), (315.0, "au nord-ouest"),
]


def _cardinal(dx: float, dz: float) -> str:
    ang = (math.degrees(math.atan2(dx, dz)) + 360.0) % 360.0
    best = min(_DIRS, key=lambda d: min(abs(ang - d[0]), 360.0 - abs(ang - d[0])))
    return best[1]


class MacroStrategyRule(Rule):
    id = "strategy.macro"
    category = AdviceCategory.STRATEGY.value
    dependencies = (
        "POSITIONS.own", "POSITIONS.allies", "POSITIONS.enemies_spotted",
        "TEAM_COUNT.allies_alive", "TEAM_COUNT.enemies_alive",
    )

    def evaluate(self, rc: RuleContext) -> list[CandidateAdvice]:
        b = rc.battle
        if b.own_pos is None:
            return []
        # Pas de macro en tout début : la règle de plan/placement gère l'ouverture.
        if rc.features.phase is BattlePhase.EARLY:
            return []

        sp = analyze(b, rc.features, b.map_bounds)
        ranked = score_actions(sp)
        if not ranked:
            return []

        best = ranked[0]
        hold_u = next((s.utility for s in ranked
                       if s.action is TacticalAction.HOLD), 0.0)
        # TENIR (silence) l'emporte, ou l'écart est trop mince -> on ne dit rien.
        if best.action is TacticalAction.HOLD or best.utility - hold_u < _HOLD_MARGIN:
            return []

        cand = self._build(best, sp, b.own_pos, b.map_bounds)
        return [cand] if cand else []

    # --- Traduction d'une action notée en conseil concret -------------------- #
    def _build(self, scored, sp, own, bounds) -> CandidateAdvice | None:
        act = scored.action
        u = scored.utility
        builders = {
            TacticalAction.RELOCATE: self._advice_relocate,
            TacticalAction.PUSH: self._advice_push,
            TacticalAction.FALL_BACK: self._advice_fall_back,
            TacticalAction.DISENGAGE: self._advice_disengage,
            TacticalAction.GO_CAP: self._advice_cap,
        }
        fn = builders.get(act)
        return fn(sp, own, bounds, u) if fn else None

    # Direction + cellule vers le POINT D'ACTION (front) : basculer / pousser.
    def _toward_action(self, sp, own):
        if sp.action_point is None:
            return None, ""
        dx = sp.action_point[0] - own[0]
        dz = sp.action_point[1] - own[1]
        cell = sp.action_grid
        return _cardinal(dx, dz), (" (%s)" % cell) if cell else ""

    # Direction + cellule d'un point de repli DERRIÈRE soi (dos au front).
    def _away_from_action(self, sp, own, bounds):
        if sp.action_point is None:
            return "vers l'arriere", ""
        dx = own[0] - sp.action_point[0]
        dz = own[1] - sp.action_point[1]
        norm = math.hypot(dx, dz)
        direction = _cardinal(dx, dz)
        if norm <= 1e-6:
            return direction, ""
        ux, uz = dx / norm, dz / norm
        retreat = (own[0] + ux * _RETREAT_M, own[1] + uz * _RETREAT_M)
        cell = grid_cell(retreat, bounds)
        return direction, (" (%s)" % cell) if cell else ""

    def _advice_relocate(self, sp, own, bounds, u) -> CandidateAdvice:
        direction, cell_suffix = self._toward_action(sp, own)
        return CandidateAdvice(
            rule_id=self.id, category=AdviceCategory.STRATEGY,
            action="RELOCATE_TO_ACTION", reason_code="SECTOR_CLEARED",
            template_key="strat_relocate", severity=Severity.INFO,
            ttl_seconds=9.0, cooldown_key="strategy",
            urgency=0.5 + u * 0.2, impact=0.8, confidence=0.7,
            context={"direction": direction, "cell_suffix": cell_suffix,
                     "distance_m": int(round(sp.dist_to_action or 0))},
        )

    def _advice_push(self, sp, own, bounds, u) -> CandidateAdvice:
        direction, cell_suffix = self._toward_action(sp, own)
        return CandidateAdvice(
            rule_id=self.id, category=AdviceCategory.STRATEGY,
            action="PUSH_ADVANTAGE", reason_code="NUMERIC_ADVANTAGE",
            template_key="strat_push", severity=Severity.INFO,
            ttl_seconds=9.0, cooldown_key="strategy",
            urgency=0.5 + u * 0.2, impact=0.75, confidence=0.7,
            context={"allies": sp.allies_alive, "enemies": sp.enemies_alive,
                     "direction": direction, "cell_suffix": cell_suffix},
        )

    def _advice_fall_back(self, sp, own, bounds, u) -> CandidateAdvice:
        crit = sp.balance is not None and sp.balance <= -3 and sp.late
        return CandidateAdvice(
            rule_id=self.id, category=AdviceCategory.STRATEGY,
            action="FALL_BACK_DEFEND", reason_code="OUTNUMBERED_GAME",
            template_key="strat_defend",
            severity=Severity.ATTENTION if crit else Severity.INFO,
            ttl_seconds=9.0, cooldown_key="strategy",
            urgency=0.55 + u * 0.25, impact=0.75, confidence=0.75,
            context={"allies": sp.allies_alive, "enemies": sp.enemies_alive,
                     "late": sp.late},
        )

    def _advice_disengage(self, sp, own, bounds, u) -> CandidateAdvice:
        direction, cell_suffix = self._away_from_action(sp, own, bounds)
        return CandidateAdvice(
            rule_id=self.id, category=AdviceCategory.STRATEGY,
            action="DISENGAGE_NOW", reason_code="LOW_HP_EXPOSED",
            template_key="strat_disengage", severity=Severity.ATTENTION,
            ttl_seconds=8.0, cooldown_key="strategy",
            urgency=0.7 + u * 0.3, impact=0.85, confidence=0.7,
            context={"direction": direction, "cell_suffix": cell_suffix,
                     "hp_pct": int(round((sp.hp_ratio or 0) * 100))},
        )

    def _advice_cap(self, sp, own, bounds, u) -> CandidateAdvice:
        return CandidateAdvice(
            rule_id=self.id, category=AdviceCategory.STRATEGY,
            action="GO_CAP", reason_code="CLOSE_ON_CAP",
            template_key="strat_cap", severity=Severity.ATTENTION,
            ttl_seconds=9.0, cooldown_key="strategy",
            urgency=0.6 + u * 0.25, impact=0.8, confidence=0.72,
            context={"allies": sp.allies_alive, "enemies": sp.enemies_alive},
        )
