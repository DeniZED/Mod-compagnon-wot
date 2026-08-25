"""Tests du rapport de session et de la gestion des donnees (GAR-002/003, 8.2)."""
from __future__ import annotations

import json

from wot_companion.profile.store import HistoryStore, BattleRecord
from wot_companion.profile.trends import aggregate_records, group_records
from wot_companion.tools.report import build_report, export_diagnostic


def _rec(i, vehicle, role, damage, survived, hp_early=False):
    return BattleRecord(id=f"b{i}", map_id="ensk", spawn="south", vehicle_id=vehicle,
                        vehicle_role=role, result="victory", damage=damage, assist=300,
                        survived=survived, kills=1, hp_ratio_end=0.5,
                        hp_lost_early=hp_early, started_ms=i * 1000)


def _seed() -> HistoryStore:
    store = HistoryStore(":memory:")
    for i in range(6):
        store.save_battle(_rec(i, "leopard_1", "sniper_medium", 2000 + i * 100,
                               survived=(i % 2 == 0)))
    for i in range(6, 10):
        store.save_battle(_rec(i, "is7", "assault_heavy", 1500, survived=True,
                               hp_early=True))
    return store


def test_aggregate_records():
    store = _seed()
    recs = store.recent_battles(limit=100)
    agg = aggregate_records(recs)
    assert agg["sample_size"] == 10
    assert 0.0 <= agg["survival_rate"] <= 1.0
    assert agg["avg_damage"] > 0


def test_group_records_by_role():
    store = _seed()
    groups = group_records(store.recent_battles(limit=100), "vehicle_role")
    assert set(groups) == {"sniper_medium", "assault_heavy"}
    assert len(groups["sniper_medium"]) == 6


def test_build_report_mentions_vehicles_and_roles():
    store = _seed()
    text = "\n".join(build_report(store))
    assert "leopard_1" in text
    assert "assault_heavy" in text
    assert "Par vehicule" in text
    assert "Profil de coaching" in text


def test_report_empty_history():
    store = HistoryStore(":memory:")
    text = "\n".join(build_report(store))
    assert "Aucune bataille" in text


def test_export_diagnostic_is_non_sensitive(tmp_path):
    store = _seed()
    path = tmp_path / "diag.json"
    export_diagnostic(store, path)
    diag = json.loads(path.read_text(encoding="utf-8"))
    assert diag["total_battles"] == 10
    assert "by_role" in diag and "assault_heavy" in diag["by_role"]
    # Aucune donnee brute/sensible : pas d'ids de bataille ni de tokens.
    blob = path.read_text(encoding="utf-8")
    assert "token" not in blob.lower()
    assert "b0" not in diag  # pas d'ids de bataille exposes a la racine


def test_reset_deletes_all():
    store = _seed()
    assert store.count_battles() == 10
    store.delete_all()
    assert store.count_battles() == 0
