"""Profil joueur : historique local (SQLite), metriques et tendances."""
from .store import HistoryStore, BattleRecord
from .trends import (
    TrendAnalyzer, SessionTrends, build_player_profile,
    aggregate_records, group_records,
)

__all__ = [
    "HistoryStore", "BattleRecord", "TrendAnalyzer", "SessionTrends",
    "build_player_profile", "aggregate_records", "group_records",
]
