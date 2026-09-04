"""Règle PLAYBOOK : « où vont les bons joueurs depuis ici » (Replay Prior live).

Consomme le Tactical Map Model (secteur courant du joueur) et le Replay Prior
de TRANSITION (secteur courant -> secteur suivant privilégié par les forts).
Couvre l'OUVERTURE (depuis le secteur de spawn) comme les rotations de milieu de
partie, sans avoir besoin de connaître l'équipe/spawn côté live : on part du
secteur RÉEL où se trouve le joueur.

Le prior INFORME, il ne décide pas : le conseil n'est émis que si un secteur
suivant se détache nettement, que le joueur n'y est pas déjà, et hors survie
(bas HP). Fair Play : connaissance historique agrégée, position propre uniquement.
"""
from __future__ import annotations

import logging
import math

from ...settings import AdviceCategory, Severity
from ..advice import CandidateAdvice
from ..context.features import BattlePhase
from ..maps import canonical_map_id, grid_cell
from .base import Rule, RuleContext

logger = logging.getLogger("wot_companion.rules.playbook")

_DIRS = [
    (0.0, "au nord"), (45.0, "au nord-est"), (90.0, "a l'est"),
    (135.0, "au sud-est"), (180.0, "au sud"), (225.0, "au sud-ouest"),
    (270.0, "a l'ouest"), (315.0, "au nord-ouest"),
]
# Probabilité minimale du secteur suivant pour oser un conseil (anti-bruit).
_MIN_PROB = 0.30
# Sous ce ratio de HP, la survie prime : pas de conseil de bascule playbook.
_SURVIVAL_HP = 0.30
# Distance mini (m) au centre du secteur cible pour juger qu'on n'y est pas.
_MIN_MOVE_M = 60.0


def _cardinal(dx: float, dz: float) -> str:
    ang = (math.degrees(math.atan2(dx, dz)) + 360.0) % 360.0
    best = min(_DIRS, key=lambda d: min(abs(ang - d[0]), 360.0 - abs(ang - d[0])))
    return best[1]


class PlaybookRule(Rule):
    id = "playbook.replay_prior"
    category = AdviceCategory.POSITIONING.value
    dependencies = ("POSITIONS.own", "MAP_INFO.map_id", "PLAYER_VEHICLE.class")

    def evaluate(self, rc: RuleContext) -> list[CandidateAdvice]:
        resolver = rc.sector_resolver
        prior = rc.replay_prior
        b = rc.battle
        if resolver is None or prior is None or b.own_pos is None or not b.map_id:
            return []
        # Fin de partie : la survie/le cap priment, pas la bascule playbook.
        if rc.features.phase is BattlePhase.LATE:
            return []
        hp = getattr(b, "hp_ratio", None)
        if hp is not None and hp < _SURVIVAL_HP:
            return []

        cmap = canonical_map_id(b.map_id)
        bounds = b.map_bounds
        current = resolver.resolve(cmap, b.own_pos, bounds)
        if current is None:
            return []

        vclass = b.vehicle_class
        options = prior.next_sector(cmap, current.id, vclass)
        if not options:
            return []
        top = options[0]
        # Déjà dans le secteur conseillé, ou signal trop faible -> silence.
        if top.sector == current.id or top.prob < _MIN_PROB:
            return []

        target = resolver.sector_world_center(cmap, top.sector, bounds)
        if target is None:
            return []
        dx, dz = target[0] - b.own_pos[0], target[1] - b.own_pos[1]
        dist = math.hypot(dx, dz)
        if dist < _MIN_MOVE_M:
            return []

        cell = grid_cell(target, bounds)
        opening = rc.features.phase is BattlePhase.EARLY
        return [CandidateAdvice(
            rule_id=self.id, category=AdviceCategory.POSITIONING,
            action="PLAYBOOK_OPENING" if opening else "PLAYBOOK_ROTATE",
            reason_code="REPLAY_PRIOR_TRANSITION",
            template_key="playbook_opening" if opening else "playbook_rotate",
            severity=Severity.INFO, ttl_seconds=8.0, cooldown_key="playbook",
            urgency=0.5, impact=0.68, confidence=min(0.8, 0.4 + top.prob * 0.4),
            context={
                "direction": _cardinal(dx, dz),
                "cell_suffix": (" en %s" % cell) if cell else "",
                "distance_m": int(round(dist)),
                "pct": int(round(top.prob * 100)),
            },
        )]
