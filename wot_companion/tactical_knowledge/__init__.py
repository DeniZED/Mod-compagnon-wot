"""Tactical Knowledge Base (Moteur Tactique V2).

Couche de connaissance HISTORIQUE et STATISTIQUE, indépendante du live. Elle ne
contient jamais d'information sur la bataille en cours : uniquement des priors
appris hors-ligne (profils de char, positions/routes efficaces agrégées depuis
des replays).

REGLE FAIR PLAY (§39 du cahier V2) : une donnée d'ici est un `HistoricalThreatZone`
ou un profil, JAMAIS un `KnownLiveEnemy`. Les deux ne partagent aucun type.
"""
from __future__ import annotations

from .models import (
    Archetype, VehicleClass, VehicleTacticalProfile,
    PositionCluster, RouteCluster, HistoricalThreatZone,
)

__all__ = [
    "Archetype", "VehicleClass", "VehicleTacticalProfile",
    "PositionCluster", "RouteCluster", "HistoricalThreatZone",
]
