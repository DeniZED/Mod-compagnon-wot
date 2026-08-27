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

import math

from ...settings import AdviceCategory, Severity
from ..advice import CandidateAdvice
from ..context.features import BattlePhase
from ..maps import canonical_map_id
from .base import Rule, RuleContext

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
            return []                          # pas de base chargee -> silence
        if b.own_pos is None or not b.map_id:
            return []
        phase_key = _PHASE_KEY.get(rc.features.phase)
        if phase_key is None or rc.features.phase is BattlePhase.LATE:
            return []                          # fin de partie : la survie prime

        vclass = self._vehicle_class(b.vehicle_class)
        near = kb.nearest_clusters(
            canonical_map_id(b.map_id), b.own_pos,
            phase=phase_key, vehicle_class=vclass,
            max_dist=_SEARCH_RADIUS_M, limit=1,
        )
        if not near:
            return []
        zone = near[0]
        if zone.confidence < _MIN_CONFIDENCE:
            return []

        dx = zone.center[0] - b.own_pos[0]
        dz = zone.center[1] - b.own_pos[1]
        dist = math.hypot(dx, dz)
        # Deja dans la zone de reference : rien a conseiller (evite le bruit).
        if dist <= zone.radius * _AWAY_FACTOR:
            return []

        direction = _cardinal(dx, dz)
        # Confiance du conseil : bornee par la confiance statistique de la zone.
        confidence = min(0.75, 0.4 + zone.confidence * 0.4)
        return [CandidateAdvice(
            rule_id=self.id, category=AdviceCategory.POSITIONING,
            action="REPOSITION_TO_ZONE", reason_code="REPLAY_EFFECTIVE_ZONE",
            template_key="pos_replay_zone", severity=Severity.INFO,
            ttl_seconds=8.0, cooldown_key="positioning_replay",
            urgency=0.45, impact=0.6, confidence=confidence,
            context={
                "direction": direction,
                "distance_m": int(round(dist)),
                "popularity_pct": int(round(zone.popularity * 100)),
                "sample": zone.sample_size,
            },
        )]

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
