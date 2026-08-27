"""Regle du plan initial (BAT-005). Produit une recommandation de depart.

Depend uniquement de donnees autorisees : carte, spawn, vehicule (rôle), et
composition connue au chargement.
"""
from __future__ import annotations

from ...settings import AdviceCategory, Severity
from ..advice import CandidateAdvice
from .base import Rule, RuleContext


class InitialPlanRule(Rule):
    id = "plan.initial"
    category = AdviceCategory.INITIAL_PLAN.value
    dependencies = (
        "MAP_INFO.map_id", "SPAWN_INFO.spawn", "PLAYER_VEHICLE.vehicle_id",
        "TEAM_COMPOSITION.ally_classes", "TEAM_COMPOSITION.enemy_classes",
    )
    once_per_battle = True

    def evaluate(self, rc: RuleContext) -> list[CandidateAdvice]:
        ctx = rc.battle
        kb = rc.knowledge
        # Fallback sûr : sans carte, aucun plan n'est invente (REC-01).
        if not ctx.map_id:
            return []

        plans = kb.candidate_plans(ctx.map_id, ctx.spawn, ctx.vehicle_role, ctx.composition)
        if not plans:
            # Carte hors des cartes detaillees : on ne fabrique pas de plan de
            # position, mais si le rôle est connu on donne un rappel de rôle
            # generique (utile sur toute carte, sans inventer de contexte carte).
            return self._role_reminder(rc)
        plan, adj_score, reasons = plans[0]

        # Confiance : proportion des signaux de contexte reellement disponibles.
        signals = [
            ctx.spawn is not None,
            ctx.vehicle_role is not None,
            bool(ctx.composition.enemy_classes) or ctx.composition.enemy_count is not None,
        ]
        confidence = sum(1 for s in signals if s) / len(signals)

        # Impact : plans mieux notes = valeur attendue plus elevee (borne 0..1).
        impact = min(1.0, adj_score / 70.0)
        # Urgence faible : c'est un conseil de depart, non une alerte.
        urgency = 0.15

        flank_label = kb.flank_label(ctx.map_id, plan.flank)
        map_info = kb.map_info(ctx.map_id) or {}
        role_info = kb.role_info(ctx.vehicle_role) or {}

        # Suffixes prêts à l'emploi : évitent "Ruinberg None" (spawn absent) et
        # la répétition "champ/foret (champ/foret)" quand l'ancre == le flanc.
        spawn_suffix = (" cote %s" % ctx.spawn) if ctx.spawn else ""
        anchor = plan.anchor
        anchor_suffix = (" (%s)" % anchor) if anchor and anchor != flank_label else ""

        return [CandidateAdvice(
            rule_id=self.id,
            category=AdviceCategory.INITIAL_PLAN,
            action="OPEN_" + (plan.aggression or "neutre").upper(),
            reason_code="INITIAL_PLAN_SELECTED",
            template_key="initial_plan",
            severity=Severity.INFO,
            ttl_seconds=10.0,
            cooldown_key="initial_plan",
            urgency=urgency,
            impact=impact,
            confidence=confidence,
            context={
                "plan_id": plan.plan_id,
                "map_label": map_info.get("label", ctx.map_id),
                "spawn": ctx.spawn,
                "spawn_suffix": spawn_suffix,
                "flank": plan.flank,
                "flank_label": flank_label,
                "anchor": plan.anchor,
                "anchor_suffix": anchor_suffix,
                "aggression": plan.aggression,
                "risk": plan.risk,
                "role_label": role_info.get("label", ctx.vehicle_role),
                "explanation": plan.explanation,
                "reasons": reasons,
            },
        )]

    def _role_reminder(self, rc: RuleContext) -> list[CandidateAdvice]:
        """Conseil d'ouverture generique base sur le rôle (carte non couverte)."""
        ctx = rc.battle
        role_info = rc.knowledge.role_info(ctx.vehicle_role)
        if not role_info or not role_info.get("reminder"):
            return []
        return [CandidateAdvice(
            rule_id=self.id,
            category=AdviceCategory.INITIAL_PLAN,
            action="ROLE_REMINDER",
            reason_code="ROLE_OPENING_REMINDER",
            template_key="initial_role_reminder",
            severity=Severity.INFO,
            ttl_seconds=9.0,
            cooldown_key="initial_plan",
            urgency=0.35,
            impact=0.8,
            confidence=1.0,  # le rôle est un signal fiable (tags du char)
            context={
                "role_label": role_info.get("label", ctx.vehicle_role),
                "role_reminder": role_info.get("reminder"),
            },
        )]
