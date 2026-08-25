"""Regle de rotation / conscience numerique (famille "Rotation", section 5.1).

Comble le "trou" de milieu de partie entre le plan initial (early) et la fin de
partie (endgame) : quand un desequilibre numerique CLAIR apparait alors que la
partie n'est pas encore dans sa phase finale, on invite a exploiter l'avantage
(bascule/pression coordonnee) ou a se replier vers l'axe fort (si en retard).

Ne depend que de TEAM_COUNT (nombre de chars vivants par camp) : donnee
observable a l'ecran, autorisee. Fallback sûr si la donnee manque.
"""
from __future__ import annotations

from ...settings import AdviceCategory, Severity
from ..advice import CandidateAdvice
from ..context.features import BattlePhase
from .base import Rule, RuleContext

# Un desequilibre est juge "significatif" a partir de 2 chars d'ecart : en dessous
# c'est du bruit tactique normal (echanges), au-dessus l'axe fort devient decisif.
MEANINGFUL_GAP = 2


class NumericAwarenessRule(Rule):
    id = "rotation.numeric.mid"
    category = AdviceCategory.ROTATION.value
    dependencies = ("TEAM_COUNT.allies_alive", "TEAM_COUNT.enemies_alive")

    def evaluate(self, rc: RuleContext) -> list[CandidateAdvice]:
        f = rc.features
        # Reserve au milieu de partie : early = plan initial, late = endgame.
        if f.phase is not BattlePhase.MID:
            return []
        # La fin de partie anticipee (peu de chars) est deja couverte par endgame.
        if f.endgame_few_left:
            return []
        # Fallback sûr : sans equilibre numerique connu, pas de conseil (BAT-010).
        if f.numeric_balance is None:
            return []

        gap = f.numeric_balance
        if abs(gap) < MEANINGFUL_GAP:
            return []

        # Ne pas pousser a l'attaque si le joueur est deja bas (coherence regle HP).
        low_hp = f.hp_ratio is not None and f.hp_ratio < 0.4

        if gap > 0 and not low_hp:
            action, reason, key, sev = (
                "EXPLOIT_ADVANTAGE", "MID_NUMERIC_ADVANTAGE",
                "rotation_advantage", Severity.INFO)
            urgency, impact, conf = 0.5, 0.6, 0.85
        elif gap < 0:
            action, reason, key, sev = (
                "REGROUP_STRONG_SIDE", "MID_NUMERIC_DISADVANTAGE",
                "rotation_disadvantage", Severity.ATTENTION)
            urgency, impact, conf = 0.6, 0.65, 0.85
        else:
            # gap > 0 mais HP bas : on ne conseille pas de pousser -> silence.
            return []

        return [CandidateAdvice(
            rule_id=self.id,
            category=AdviceCategory.ROTATION,
            action=action,
            reason_code=reason,
            template_key=key,
            severity=sev,
            ttl_seconds=7.0,
            cooldown_key="rotation",
            urgency=urgency,
            impact=impact,
            confidence=conf,
            context={
                "allies_alive": rc.battle.allies_alive,
                "enemies_alive": rc.battle.enemies_alive,
                "gap": abs(gap),
            },
        )]
