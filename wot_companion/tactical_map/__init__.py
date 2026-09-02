"""Tactical Map Model : représentation tactique explicite du terrain (§5).

Paquet ISOLÉ et purement additif. Il donne une sémantique au terrain (ville,
crête, corridor lourd, ligne de sniper, route de repli…) là où le moteur ne
raisonnait qu'en barycentres et distances.

Fair Play : un `Sector` est de la GÉOGRAPHIE statique de carte, jamais une
position ennemie. Local-first, 100 % déterministe et testable.
"""
from __future__ import annotations

from .models import MapEdge, MapGraph, Sector, SectorType
from .resolver import SectorResolver

__all__ = ["MapEdge", "MapGraph", "Sector", "SectorType", "SectorResolver"]
