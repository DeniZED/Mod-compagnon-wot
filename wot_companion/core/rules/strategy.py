"""Règle MACRO : la « vraie logique » de décision (où aller, quoi faire).

Au-dessus du placement statique (`positioning.replay_zones`, « où les bons se
tiennent »), cette règle lit l'ÉTAT de la partie via `SituationAnalyzer` et décide
l'action stratégique du moment :

  1. Secteur nettoyé + pas en défaveur -> BASCULE vers le front (farm là où ça se joue).
  2. Sous-nombre net (surtout en fin de partie) -> REPLI/DÉFENSE (ne pas se jeter).
  3. Avantage + en forme -> POUSSE avec l'équipe pour conclure.

Fair Play : n'exploite que l'écart numérique connu, la position PROPRE, celles des
alliés et des ennemis DÉJÀ spottés. Aucune position d'ennemi non spotté.
"""
from __future__ import annotations

import math

from ...settings import AdviceCategory, Severity
from ..advice import CandidateAdvice
from ..context.features import BattlePhase
from ..strategy import analyze
from .base import Rule, RuleContext

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

        cand = (self._losing(sp) or self._relocate(sp, b.own_pos)
                or self._pushing(sp, b.own_pos))
        return [cand] if cand else []

    # --- 1. Sous-nombre -> repli / défense (priorité la plus haute) ----------
    def _losing(self, sp) -> CandidateAdvice | None:
        if sp.balance is None or sp.balance > -2:
            return None
        crit = sp.balance <= -3 and sp.late
        return CandidateAdvice(
            rule_id=self.id, category=AdviceCategory.STRATEGY,
            action="FALL_BACK_DEFEND", reason_code="OUTNUMBERED_GAME",
            template_key="strat_defend",
            severity=Severity.ATTENTION if crit else Severity.INFO,
            ttl_seconds=9.0, cooldown_key="strategy",
            urgency=0.7 if crit else 0.55, impact=0.75, confidence=0.75,
            context={"allies": sp.allies_alive, "enemies": sp.enemies_alive,
                     "late": sp.late},
        )

    # --- 2. Secteur calme + pas en défaveur -> bascule vers le front ---------
    def _relocate(self, sp, own) -> CandidateAdvice | None:
        if sp.momentum == "losing" or not sp.sector_calm or not sp.healthy:
            return None
        if sp.action_point is None or sp.dist_to_action is None:
            return None
        dx = sp.action_point[0] - own[0]
        dz = sp.action_point[1] - own[1]
        cell = sp.action_grid
        return CandidateAdvice(
            rule_id=self.id, category=AdviceCategory.STRATEGY,
            action="RELOCATE_TO_ACTION", reason_code="SECTOR_CLEARED",
            template_key="strat_relocate", severity=Severity.INFO,
            ttl_seconds=9.0, cooldown_key="strategy",
            urgency=0.62, impact=0.8, confidence=0.7,
            context={"direction": _cardinal(dx, dz),
                     "cell_suffix": (" (%s)" % cell) if cell else "",
                     "distance_m": int(round(sp.dist_to_action))},
        )

    # --- 3. Avantage + en forme -> pousse pour conclure ----------------------
    def _pushing(self, sp, own) -> CandidateAdvice | None:
        if sp.momentum != "winning" or not sp.healthy:
            return None
        if sp.action_point is None:
            return None
        # Le cas « secteur mort » est traité par _relocate ; ici on est engagé /
        # proche du front avec l'avantage -> presser plutôt que temporiser.
        if sp.sector_calm:
            return None
        dx = sp.action_point[0] - own[0]
        dz = sp.action_point[1] - own[1]
        cell = sp.action_grid
        return CandidateAdvice(
            rule_id=self.id, category=AdviceCategory.STRATEGY,
            action="PUSH_ADVANTAGE", reason_code="NUMERIC_ADVANTAGE",
            template_key="strat_push", severity=Severity.INFO,
            ttl_seconds=9.0, cooldown_key="strategy",
            urgency=0.55, impact=0.72, confidence=0.7,
            context={"allies": sp.allies_alive, "enemies": sp.enemies_alive,
                     "direction": _cardinal(dx, dz),
                     "cell_suffix": (" (%s)" % cell) if cell else ""},
        )
