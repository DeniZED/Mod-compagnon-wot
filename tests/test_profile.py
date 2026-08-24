"""Tests de l'historique local (SQLite), des tendances et du profil."""
from __future__ import annotations

from wot_companion.core.context.battle_context import BattleContext
from wot_companion.profile.store import HistoryStore, BattleRecord, SCHEMA_VERSION
from wot_companion.profile.trends import TrendAnalyzer, build_player_profile


def _rec(i: int, damage: float, survived: bool, hp_early: bool,
         vehicle="leopard_1") -> BattleRecord:
    return BattleRecord(id=f"b{i}", map_id="mines", spawn="south", vehicle_id=vehicle,
                        vehicle_role="sniper_medium", result="victory", damage=damage,
                        assist=200, survived=survived, kills=1, hp_ratio_end=0.5,
                        hp_lost_early=hp_early, started_ms=i * 1000)


def test_migration_sets_user_version():
    store = HistoryStore(":memory:")
    v = store.conn.execute("PRAGMA user_version").fetchone()[0]
    assert v == SCHEMA_VERSION


def test_record_and_recent():
    store = HistoryStore(":memory:")
    for i in range(3):
        store.save_battle(_rec(i, 1000 + i, True, False))
    assert store.count_battles() == 3
    recent = store.recent_battles(limit=2)
    assert len(recent) == 2
    assert recent[0].id == "b2"  # le plus recent d'abord


def test_delete_all():
    store = HistoryStore(":memory:")
    store.save_battle(_rec(0, 1000, True, False))
    store.add_metric("b0", "dpg", 1000)
    store.delete_all()
    assert store.count_battles() == 0


def test_record_from_context():
    store = HistoryStore(":memory:")
    ctx = BattleContext(battle_id="ctx1", start_ms=0, map_id="mines", spawn="south",
                        vehicle_id="leopard_1", vehicle_role="sniper_medium")
    ctx.elapsed_s = 60
    ctx.hp_ratio = 0.4  # bas et tot -> hp_lost_early
    ctx.total_damage = 1500
    rec = store.record_from_context(ctx)
    assert rec.hp_lost_early is True
    assert store.count_battles() == 1


def test_trends_low_sample_flag():
    store = HistoryStore(":memory:")
    for i in range(3):
        store.save_battle(_rec(i, 2000, True, False))
    t = TrendAnalyzer(store).session_trends(window=10)
    assert t.sample_size == 3
    assert t.low_sample is True  # < MIN_SAMPLE_SIZE
    assert t.avg_damage == 2000


def test_trends_summary_flags_early_hp_loss():
    store = HistoryStore(":memory:")
    for i in range(10):
        store.save_battle(_rec(i, 2500, i % 2 == 0, hp_early=True))
    t = TrendAnalyzer(store).session_trends(window=10)
    lines = TrendAnalyzer(store).summary_lines(t)
    assert any("early" in ln.lower() for ln in lines)


def test_player_profile_has_sample_and_confidence():
    store = HistoryStore(":memory:")
    for i in range(20):
        store.save_battle(_rec(i, 2000, True, hp_early=(i < 8)))
    profile = build_player_profile(store)
    assert profile["sample_size"] == 20
    assert 0.0 <= profile["confidence"] <= 1.0
    assert "hp_preservation" in profile
