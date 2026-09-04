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
from ..maps import canonical_map_id, flank_label, grid_cell
from .base import Rule, RuleContext

logger = logging.getLogger("wot_companion.rules.playbook")

_DIRS = [
    (0.0, "au nord"), (45.0, "au nord-est"), (90.0, "a l'est"),
    (135.0, "au sud-est"), (180.0, "au sud"), (225.0, "au sud-ouest"),
    (270.0, "a l'ouest"), (315.0, "au nord-ouest"),
]
# Probabilité minimale du secteur suivant pour oser un conseil (anti-bruit).
_MIN_PROB = 0.30
# Nombre MINIMAL de références (joueurs distincts) derrière le choix. Sans ça,
# une transition vue par 3 joueurs ressort « 100 % » et donne un conseil
# affirmatif mais non fiable (§14 : faible confiance -> silence). C'est le cas du
# faux « sud-est 100 % » vu en jeu : trop peu de données.
_MIN_SAMPLE = 20
# Sous ce ratio de HP, la survie prime : pas de conseil de bascule playbook.
_SURVIVAL_HP = 0.30
# Distance mini (m) au centre du secteur cible pour juger qu'on n'y est pas.
_MIN_MOVE_M = 60.0


def _cardinal(dx: float, dz: float) -> str:
    ang = (math.degrees(math.atan2(dx, dz)) + 360.0) % 360.0
    best = min(_DIRS, key=lambda d: min(abs(ang - d[0]), 360.0 - abs(ang - d[0])))
    return best[1]


def select_target(resolver, prior, map_id, own_pos, bounds, vehicle_class,
                  min_prob: float = _MIN_PROB, min_sample: int = _MIN_SAMPLE):
    """Cible playbook partagée (règle + radar) : depuis le secteur courant, le
    secteur suivant privilégié par les bons. Retourne (sector, center_monde, prob,
    sample) ou None si rien de FIABLE (prob suffisante ET assez de références).
    `sector` est l'objet Sector cible (pour le côté/la boîte), `center` sa
    position monde (pour direction/case)."""
    if resolver is None or prior is None or not own_pos or not map_id:
        return None
    cmap = canonical_map_id(map_id)
    current = resolver.resolve(cmap, own_pos, bounds)
    if current is None:
        return None
    def _pick(options):
        if not options:
            return None
        t = options[0]
        # Fiabilité : assez fréquent ET assez de références (sinon « 100 % » trompeur).
        if t.sector == current.id or t.prob < min_prob or t.sample < min_sample:
            return None
        return t

    # D'abord la donnée SPÉCIFIQUE à la classe (les lights ne jouent pas comme les
    # lourds) ; si elle est trop maigre, on retombe sur l'agrégat toutes classes.
    top = _pick(prior.next_sector(cmap, current.id, vehicle_class))
    if top is None and vehicle_class is not None:
        top = _pick(prior.next_sector(cmap, current.id, None))
    if top is None:
        return None
    center = resolver.sector_world_center(cmap, top.sector, bounds)
    if center is None:
        return None
    g = resolver.graph(cmap)
    sector = g.sector(top.sector) if g is not None else None
    if sector is None:
        return None
    return sector, center, top.prob, top.sample


class PlaybookRule(Rule):
    id = "playbook.replay_prior"
    category = AdviceCategory.POSITIONING.value
    dependencies = ("POSITIONS.own", "MAP_INFO.map_id", "PLAYER_VEHICLE.class")

    def evaluate(self, rc: RuleContext) -> list[CandidateAdvice]:
        b = rc.battle
        # Fin de partie : la survie/le cap priment, pas la bascule playbook.
        if rc.features.phase is BattlePhase.LATE:
            return []
        hp = getattr(b, "hp_ratio", None)
        if hp is not None and hp < _SURVIVAL_HP:
            return []

        bounds = b.map_bounds
        found = select_target(rc.sector_resolver, rc.replay_prior, b.map_id,
                              b.own_pos, bounds, b.vehicle_class)
        if found is None:
            return []
        sector, target, prob, sample = found
        dx, dz = target[0] - b.own_pos[0], target[1] - b.own_pos[1]

        # Case principale SANS sous-quadrant : le centroïde d'un secteur tombe sur
        # une frontière de grille, la sous-case y est un artefact (toujours « -7 »).
        cell = grid_cell(target, bounds, sub=False)
        opening = rc.features.phase is BattlePhase.EARLY
        pct = int(round(prob * 100))
        if opening:
            # OUVERTURE : on nomme un CÔTÉ absolu (flanc) à privilégier, pas un
            # point proche relatif — plus clair et plus utile en début de partie.
            side = flank_label(*sector.centroid_norm())
            return [CandidateAdvice(
                rule_id=self.id, category=AdviceCategory.POSITIONING,
                action="PLAYBOOK_OPENING", reason_code="REPLAY_PRIOR_OPENING",
                template_key="playbook_opening", severity=Severity.INFO,
                ttl_seconds=8.0, cooldown_key="playbook",
                urgency=0.55, impact=0.7, confidence=min(0.8, 0.4 + prob * 0.4),
                context={"side": side,
                         "cell_suffix": (" (case %s)" % cell) if cell else "",
                         "pct": pct, "sample": sample})]
        # MILIEU DE PARTIE : bascule vers le secteur suivant (direction + case).
        dist = math.hypot(dx, dz)
        if dist < _MIN_MOVE_M:
            return []
        return [CandidateAdvice(
            rule_id=self.id, category=AdviceCategory.POSITIONING,
            action="PLAYBOOK_ROTATE", reason_code="REPLAY_PRIOR_TRANSITION",
            template_key="playbook_rotate", severity=Severity.INFO,
            ttl_seconds=8.0, cooldown_key="playbook",
            urgency=0.5, impact=0.68, confidence=min(0.8, 0.4 + prob * 0.4),
            context={"direction": _cardinal(dx, dz),
                     "cell_suffix": (" en %s" % cell) if cell else "",
                     "distance_m": int(round(dist)), "pct": pct,
                     "sample": sample})]
