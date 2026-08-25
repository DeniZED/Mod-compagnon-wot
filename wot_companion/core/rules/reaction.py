"""Reaction "tir recu" (famille "Reaction", section 5.1).

Rend le compagnon vivant : quand le joueur encaisse des degats (chute de HP
detectee entre deux relevés), il reagit brievement avec un micro-conseil utile
selon la situation (angle ton blindage / decroche si ca fond). Base uniquement
sur les HP propres du joueur (information autorisee).

Cadence : intervalle PROPRE a la regle (min_interval_s), plus court que les
cooldowns de categorie, pour rester reactif sans etouffer les autres conseils
ni spammer a chaque obus.
"""
from __future__ import annotations

from ...settings import AdviceCategory, Severity
from ..advice import CandidateAdvice

from .base import Rule, RuleContext

# Un coup "serieux" (>= 12% de la barre d'un coup) merite un ton plus marque.
HEAVY_HIT_RATIO = 0.12
# Espacement minimal entre deux reactions (s) : responsive mais pas du spam.
REACTION_INTERVAL_S = 9.0


# Variantes de texte pour un coup "standard", pour eviter la repetition a l'ecran.
_HIT_VARIANTS = ("reaction_hit", "reaction_hit2", "reaction_hit3")


class HitTakenReactionRule(Rule):
    id = "reaction.hit_taken"
    category = AdviceCategory.REACTION.value
    dependencies = ("PLAYER_HP_CHANGED.hp_ratio",)

    def __init__(self) -> None:
        self._variant = 0

    def evaluate(self, rc: RuleContext) -> list[CandidateAdvice]:
        f = rc.features
        if not f.took_damage_recently:
            return []

        hp = f.hp_ratio if f.hp_ratio is not None else 1.0
        heavy = f.damage_taken_ratio >= HEAVY_HIT_RATIO

        # Choix du micro-conseil selon l'etat : bas + touche = decrocher ;
        # sinon = jouer le blindage / rester couvert (avec variantes de texte).
        if hp < 0.35:
            action, key, sev = "BREAK_CONTACT", "reaction_hit_low", Severity.ATTENTION
            urgency = 0.7
        elif heavy:
            action, key, sev = "USE_ARMOR", "reaction_hit_heavy", Severity.INFO
            urgency = 0.5
        else:
            key = _HIT_VARIANTS[self._variant % len(_HIT_VARIANTS)]
            self._variant += 1
            action, sev = "USE_ARMOR", Severity.INFO
            urgency = 0.4

        return [CandidateAdvice(
            rule_id=self.id,
            category=AdviceCategory.REACTION,
            action=action,
            reason_code="DAMAGE_TAKEN",
            template_key=key,
            severity=sev,
            ttl_seconds=4.0,
            cooldown_key="reaction",
            min_interval_s=REACTION_INTERVAL_S,
            urgency=urgency,
            impact=0.45,
            confidence=1.0,   # HP propre = signal fiable
            context={"hp_pct": round(hp * 100)},
        )]
