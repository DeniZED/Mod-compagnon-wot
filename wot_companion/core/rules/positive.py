"""Regle de renforcement positif (famille "Positif", section 5.1).

Le compagnon n'est pas qu'un donneur d'alertes : de temps en temps, il souligne
ce qui va bien. Ici, uniquement sur des faits OBSERVABLES et honnetes : le joueur
a survecu la phase d'ouverture en gardant ses HP. Aucun jugement invente sur la
performance (les degats ne sont pas disponibles en direct).

Rare par construction : le cooldown positif dedie (anti-spam) espace ces messages
pour qu'ils gardent de la valeur.
"""
from __future__ import annotations

from ...settings import AdviceCategory, Severity
from ..advice import CandidateAdvice
from ..context.features import BattlePhase

from .base import Rule, RuleContext

# HP juges "sains" : le joueur a bien gere son char (coherent avec le seuil abime).
HEALTHY_HP = 0.6


class PositiveReinforcementRule(Rule):
    id = "positive.healthy_midgame"
    category = AdviceCategory.POSITIVE.value
    dependencies = ("PLAYER_HP_CHANGED.hp_ratio", "CLOCK_TICK.elapsed_s")

    def evaluate(self, rc: RuleContext) -> list[CandidateAdvice]:
        f = rc.features
        # Uniquement une fois sorti de l'ouverture : un compliment trop tot n'a
        # pas de sens (rien ne s'est encore joue).
        if f.phase is BattlePhase.EARLY:
            return []
        # Fait observable requis : HP connus et sains.
        if f.hp_ratio is None or f.hp_ratio < HEALTHY_HP:
            return []
        # Ne pas feliciter si l'equipe est en nette difficulte numerique : le ton
        # serait a cote de la plaque.
        if f.numeric_balance is not None and f.numeric_balance <= -2:
            return []

        return [CandidateAdvice(
            rule_id=self.id,
            category=AdviceCategory.POSITIVE,
            action="ENCOURAGE_HP",
            reason_code="HEALTHY_MIDGAME",
            template_key="positive_healthy",
            severity=Severity.POSITIVE,
            ttl_seconds=5.0,
            cooldown_key="positive",
            urgency=0.35,
            impact=0.55,
            confidence=1.0,   # HP propre = signal fiable
            context={"hp_pct": round(f.hp_ratio * 100)},
        )]
