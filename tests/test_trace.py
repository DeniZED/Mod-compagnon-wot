"""Tests de la trace tactique legere (V2 §34) : schema v2, store, recorder."""
from __future__ import annotations

from wot_companion.core.context.battle_context import BattleContext
from wot_companion.core.context.features import FeatureBuilder
from wot_companion.profile.store import BattleState, HistoryStore
from wot_companion.profile.trace import BattleTraceRecorder


def test_migration_to_v2_creates_states_table():
    store = HistoryStore(":memory:")
    v = store.conn.execute("PRAGMA user_version").fetchone()[0]
    assert v == 2
    # la table existe et est interrogeable
    assert store.count_states() == 0


def test_record_and_read_states():
    store = HistoryStore(":memory:")
    store.record_state("b1", BattleState(
        t_s=10.0, x=100.0, z=-50.0, hp_ratio=0.9, damage=0, assist=0,
        allies_near=3, enemies_near=1, phase="early"))
    store.record_state("b1", BattleState(
        t_s=15.0, x=120.0, z=-40.0, hp_ratio=0.8, damage=250, assist=0,
        allies_near=2, enemies_near=2, phase="early"))
    states = store.battle_states("b1")
    assert len(states) == 2
    assert states[0].t_s == 10.0 and states[1].damage == 250
    assert store.count_states("b1") == 2


def _ctx_at(t, own=(100.0, 200.0), hp=0.8):
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = t
    ctx.own_pos = own
    ctx.hp_ratio = hp
    return ctx


def test_recorder_samples_at_interval():
    store = HistoryStore(":memory:")
    rec = BattleTraceRecorder(store, interval_s=5.0)
    fb = FeatureBuilder()
    # t=0 : premier point ; t=2 : trop tot ; t=6 : nouveau point
    assert rec.maybe_record(_ctx_at(0), fb.build(_ctx_at(0))) is True
    assert rec.maybe_record(_ctx_at(2), fb.build(_ctx_at(2))) is False
    assert rec.maybe_record(_ctx_at(6), fb.build(_ctx_at(6))) is True
    assert store.count_states("b") == 2


def test_recorder_stores_position_and_phase():
    store = HistoryStore(":memory:")
    rec = BattleTraceRecorder(store, interval_s=5.0)
    ctx = _ctx_at(300, own=(412.0, 718.0), hp=0.6)
    rec.maybe_record(ctx, FeatureBuilder().build(ctx))
    s = store.battle_states("b")[0]
    assert s.x == 412.0 and s.z == 718.0
    assert s.phase == "mid"          # 300 s -> phase MID


def test_recorder_resets_between_battles():
    store = HistoryStore(":memory:")
    rec = BattleTraceRecorder(store, interval_s=5.0)
    c1 = _ctx_at(50); c1.battle_id = "A"
    c2 = _ctx_at(1); c2.battle_id = "B"
    assert rec.maybe_record(c1, None) is True
    # nouvelle bataille : le premier point passe meme si t plus petit
    assert rec.maybe_record(c2, None) is True
    assert store.count_states("A") == 1 and store.count_states("B") == 1
