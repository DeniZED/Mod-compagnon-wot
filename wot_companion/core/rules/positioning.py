"""Regles de placement (famille "Positioning").

Exploitent le feed minimap (Fair Play) : position du joueur, de ses allies, et
des ennemis DEJA SPOTTES. Aucune position d'ennemi non spotte n'est lue.

Trois situations, par priorite decroissante :
  1. Menace locale : plusieurs ennemis spottes proches et pas assez d'allies ->
     tu es en sous-nombre LOCAL, temporise/replie.
  2. Surextension : tu es nettement devant le gros de ton equipe -> temporise.
  3. Isolement : aucun allie a portee de soutien -> regroupe-toi.

Une seule regle produit au plus un candidat (la situation la plus prioritaire),
pour ne pas saturer.
"""
from __future__ import annotations

from ...settings import AdviceCategory, Severity
from ..advice import CandidateAdvice
from ..context.features import BattlePhase

from .base import Rule, RuleContext


class PositioningRule(Rule):
    id = "positioning.spatial"
    category = AdviceCategory.POSITIONING.value
    dependencies = ("POSITIONS.own", "POSITIONS.allies", "POSITIONS.enemies_spotted")

    def evaluate(self, rc: RuleContext) -> list[CandidateAdvice]:
        f = rc.features
        # Fallback sûr : sans position propre, aucune donnee spatiale -> silence.
        if f.nearest_ally_dist is None and not f.enemies_spotted_near:
            return []
        # Pas de conseil de placement en toute fin de partie (survie prime, endgame gere).
        if f.phase is BattlePhase.LATE:
            return []

        cand = self._threat(f) or self._overextended(f) or self._isolated(f)
        return [cand] if cand else []

    def _threat(self, f) -> CandidateAdvice | None:
        # Sous-nombre LOCAL : au moins 2 ennemis spottes proches et strictement
        # plus d'ennemis proches que d'allies de soutien.
        if f.enemies_spotted_near >= 2 and f.enemies_spotted_near > f.allies_near:
            crit = f.enemies_spotted_near >= 3 and f.allies_near == 0
            return CandidateAdvice(
                rule_id=self.id, category=AdviceCategory.POSITIONING,
                action="LOCAL_OUTNUMBERED", reason_code="LOCAL_THREAT",
                template_key="pos_local_threat",
                severity=Severity.CRITICAL if crit else Severity.ATTENTION,
                ttl_seconds=7.0, cooldown_key="positioning",
                urgency=0.85 if crit else 0.7, impact=0.8, confidence=0.9,
                context={"enemies": f.enemies_spotted_near, "allies": f.allies_near},
            )
        return None

    def _overextended(self, f) -> CandidateAdvice | None:
        if f.overextended:
            return CandidateAdvice(
                rule_id=self.id, category=AdviceCategory.POSITIONING,
                action="FALL_BACK_TEMPO", reason_code="OVEREXTENDED",
                template_key="pos_overextended", severity=Severity.ATTENTION,
                ttl_seconds=7.0, cooldown_key="positioning",
                urgency=0.6, impact=0.7, confidence=0.8,
                context={},
            )
        return None

    def _isolated(self, f) -> CandidateAdvice | None:
        if f.isolated:
            return CandidateAdvice(
                rule_id=self.id, category=AdviceCategory.POSITIONING,
                action="REGROUP", reason_code="ISOLATED",
                template_key="pos_isolated", severity=Severity.ATTENTION,
                ttl_seconds=7.0, cooldown_key="positioning",
                urgency=0.55, impact=0.65, confidence=0.8,
                context={"nearest_ally_m": round(f.nearest_ally_dist)
                         if f.nearest_ally_dist is not None else None},
            )
        return None
