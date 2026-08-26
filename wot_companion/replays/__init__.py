"""Lecture des replays WoT (.wotreplay) — hors-ligne, local (Moteur V2, Phase A).

L'en-tete d'un .wotreplay est constitue de blocs JSON (metadonnees de debut +
resultats de fin), suivis d'un flux binaire de paquets (positions/mouvements).

Ce module lit les blocs JSON en Python pur (aucune dependance) : il en tire la
verite terrain d'une bataille — char, carte, degats, assist, kills, survie,
resultat. Le decodage du flux binaire (positions dans le temps) est une etape
ulterieure (cf. evido/wotreplay-parser, BSD-3) et n'est PAS requis ici.
"""
from __future__ import annotations

from .parse import ReplaySummary, parse_replay, read_json_blocks

__all__ = ["ReplaySummary", "parse_replay", "read_json_blocks"]
