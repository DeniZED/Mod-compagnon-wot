"""Regle de placement issue des REPLAYS (Tactical Knowledge Base).

Contrairement a `positioning.spatial` (reactif : menace/isolement lus sur la
minimap live), cette regle est PROACTIVE : elle compare la position du joueur aux
zones ou les MEILLEURS joueurs performent sur cette carte, a cette phase, avec ce
type de char (base bâtie hors-ligne depuis des replays).

Fair Play : la base est de la connaissance HISTORIQUE agregee (jamais une position
ennemie reelle). La regle lit seulement la position PROPRE du joueur (POSITIONS.own)
et des metadonnees visibles (carte, classe de char, phase).

Elle suggere une DIRECTION vers la zone de reference la plus pertinente quand le
joueur n'y est pas deja. Elle n'ordonne jamais : elle informe (« les bons jouent
plutot par la »).
"""
from __future__ import annotations

import logging
import math

from ...settings import AdviceCategory, Severity
from ..advice import CandidateAdvice
from ..context.features import BattlePhase
from ..maps import canonical_map_id
from .base import Rule, RuleContext

logger = logging.getLogger("wot_companion.rules.replay_zones")

# Distance min. (m) au centre d'une zone pour juger que le joueur n'y est PAS.
_AWAY_FACTOR = 1.8
# Confiance minimale d'une zone pour oser un conseil (anti-bruit statistique).
_MIN_CONFIDENCE = 0.3
# Portee de recherche autour du joueur.
_SEARCH_RADIUS_M = 250.0

_PHASE_KEY = {
    BattlePhase.EARLY: "early",
    BattlePhase.MID: "mid",
    BattlePhase.LATE: "late",
}

# Vecteur (dx, dz) -> direction cardinale FR. +x = est, +z = nord (repere WoT).
_DIRS = [
    (0.0, "au nord"), (45.0, "au nord-est"), (90.0, "a l'est"),
    (135.0, "au sud-est"), (180.0, "au sud"), (225.0, "au sud-ouest"),
    (270.0, "a l'ouest"), (315.0, "au nord-ouest"),
]


def _fmt(pos) -> str:
    return "(%.0f,%.0f)" % (pos[0], pos[1]) if pos else "?"


def _cardinal(dx: float, dz: float) -> str:
    ang = (math.degrees(math.atan2(dx, dz)) + 360.0) % 360.0
    best = min(_DIRS, key=lambda d: min(abs(ang - d[0]), 360.0 - abs(ang - d[0])))
    return best[1]


class TacticalPositioningRule(Rule):
    id = "positioning.replay_zones"
    category = AdviceCategory.POSITIONING.value
    dependencies = ("POSITIONS.own", "MAP_INFO.map_id", "PLAYER_VEHICLE.class")

    def evaluate(self, rc: RuleContext) -> list[CandidateAdvice]:
        kb = rc.tactical_kb
        b = rc.battle
        if kb is None or not getattr(kb, "clusters", None):
            self._diag(rc, "base_absente_ou_vide")
            return []                          # pas de base chargee -> silence
        if b.own_pos is None or not b.map_id:
            self._diag(rc, "sans_position_ou_carte own=%s map=%s"
                       % (b.own_pos is not None, b.map_id))
            return []
        phase_key = _PHASE_KEY.get(rc.features.phase)
        if phase_key is None or rc.features.phase is BattlePhase.LATE:
            self._diag(rc, "phase_late")
            return []                          # fin de partie : la survie prime

        cmap = canonical_map_id(b.map_id)
        vclass = self._vehicle_class(b.vehicle_class)
        near = kb.nearest_clusters(
            cmap, b.own_pos, phase=phase_key, vehicle_class=vclass,
            max_dist=_SEARCH_RADIUS_M, limit=1,
        )
        if not near:
            self._diag(rc, "aucune_zone map=%s(%s) classe=%s phase=%s pos=%s"
                       % (cmap, b.map_id, vclass, phase_key, _fmt(b.own_pos)))
            return []
        zone = near[0]
        if zone.confidence < _MIN_CONFIDENCE:
            self._diag(rc, "zone_peu_fiable conf=%.2f (min %.2f) map=%s"
                       % (zone.confidence, _MIN_CONFIDENCE, cmap))
            return []

        dx = zone.center[0] - b.own_pos[0]
        dz = zone.center[1] - b.own_pos[1]
        dist = math.hypot(dx, dz)
        # Deja dans la zone de reference : rien a conseiller (evite le bruit).
        if dist <= zone.radius * _AWAY_FACTOR:
            self._diag(rc, "deja_dans_la_zone dist=%.0f<=%.0f map=%s"
                       % (dist, zone.radius * _AWAY_FACTOR, cmap))
            return []
        logger.info("CANDIDAT zone map=%s classe=%s dir vers (%.0f,%.0f) dist=%.0fm "
                    "conf=%.2f pop=%.2f n=%d", cmap, vclass, zone.center[0],
                    zone.center[1], dist, zone.confidence, zone.popularity,
                    zone.sample_size)

        direction = _cardinal(dx, dz)
        # Confiance du conseil : bornee par la confiance statistique de la zone.
        confidence = min(0.8, 0.45 + zone.confidence * 0.4)
        # Léger relèvement : reste SOUS les alertes réactives (HP bas, repli,
        # sous-nombre) pour ne jamais les court-circuiter, mais passe au-dessus des
        # conseils faibles et du seuil, afin d'apparaître dans les temps calmes.
        return [CandidateAdvice(
            rule_id=self.id, category=AdviceCategory.POSITIONING,
            action="REPOSITION_TO_ZONE", reason_code="REPLAY_EFFECTIVE_ZONE",
            template_key="pos_replay_zone", severity=Severity.INFO,
            ttl_seconds=8.0, cooldown_key="positioning_replay",
            urgency=0.5, impact=0.65, confidence=confidence,
            context={
                "direction": direction,
                "distance_m": int(round(dist)),
                "popularity_pct": int(round(zone.popularity * 100)),
                "sample": zone.sample_size,
            },
        )]

    def __init__(self) -> None:
        self._diag_last_s = -999.0
        self._diag_last_msg = ""

    def _diag(self, rc: RuleContext, msg: str) -> None:
        """Trace throttlee (~15 s ou au changement) : pourquoi la regle se tait."""
        t = rc.battle.elapsed_s
        if msg != self._diag_last_msg or t - self._diag_last_s >= 15.0:
            logger.info("SILENCE: %s", msg)
            self._diag_last_s = t
            self._diag_last_msg = msg

    @staticmethod
    def _vehicle_class(raw):
        """Convertit la classe live (str) en VehicleClass, ou None si inconnue."""
        if not raw:
            return None
        from ...tactical_knowledge.models import VehicleClass
        try:
            return VehicleClass(str(raw).lower())
        except ValueError:
            return None
