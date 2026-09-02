"""Tests du Replay Backtester (§15, §16) : runner, métriques, golden scenarios."""
from __future__ import annotations

from pathlib import Path

from wot_companion.backtest import (
    ScenarioTimeline, StateTick, compute_metrics, intent_of,
    load_golden_dir, run_golden, run_timeline)
from wot_companion.backtest.runner import AdviceRecord

_GOLDEN_DIR = Path(__file__).with_name("golden_scenarios")


# ---- Mapping intention -----------------------------------------------------
def test_intent_mapping():
    assert intent_of("PUSH_ADVANTAGE") == "ADVANCE"
    assert intent_of("DISENGAGE_NOW") == "RETREAT"
    assert intent_of("FALL_BACK_DEFEND") == "RETREAT"
    assert intent_of("REGROUP_STRONG_AXIS") == "RETREAT"
    assert intent_of("RELOCATE_TO_ACTION") == "RELOCATE"
    assert intent_of("REPOSITION_TO_ZONE") == "RELOCATE"
    assert intent_of("GO_CAP") == "CAP"
    assert intent_of(None) == "OTHER"


# ---- Runner ----------------------------------------------------------------
def test_runner_produces_one_record_per_tick():
    tl = ScenarioTimeline(
        map_id="prokhorovka", bounds=(-500, -500, 500, 500), vehicle_class="medium",
        ticks=[StateTick(t=200, own=(0, 0), hp_ratio=0.9, allies_alive=7, enemies_alive=7),
               StateTick(t=210, own=(0, 0), hp_ratio=0.9, allies_alive=7, enemies_alive=7)])
    recs = run_timeline(tl)
    assert len(recs) == 2
    assert all(isinstance(r, AdviceRecord) for r in recs)


def test_runner_low_hp_triggers_retreat_intent():
    tl = ScenarioTimeline(
        map_id="prokhorovka", bounds=(-500, -500, 500, 500), vehicle_class="medium",
        ticks=[StateTick(t=300, own=(0, 0), allies=[(200, 0)],
                         enemies_spotted=[(40, 0)], hp_ratio=0.12,
                         allies_alive=6, enemies_alive=6)])
    recs = run_timeline(tl)
    shown = [r for r in recs if not r.silent]
    assert shown and intent_of(shown[-1].action) == "RETREAT"


# ---- Métriques -------------------------------------------------------------
def _rec(t, action, silent=False, score=50.0, rule="r"):
    return AdviceRecord(t, None if silent else rule, action, "STRATEGY", score,
                        "INFO", action or "", silent)


def test_metrics_silence_and_counts():
    recs = [_rec(1, None, silent=True), _rec(2, "PUSH_ADVANTAGE"),
            _rec(3, None, silent=True), _rec(4, "GO_CAP")]
    m = compute_metrics(recs)
    assert m.ticks == 4
    assert m.advice_count == 2
    assert m.silence_rate == 0.5


def test_metrics_detects_contradiction():
    recs = [_rec(1, "PUSH_ADVANTAGE"), _rec(2, "FALL_BACK_DEFEND")]
    m = compute_metrics(recs)
    assert m.contradiction_rate > 0


def test_metrics_detects_action_flip():
    recs = [_rec(1, "PUSH_ADVANTAGE"), _rec(2, "FALL_BACK_DEFEND"),
            _rec(3, "PUSH_ADVANTAGE")]
    m = compute_metrics(recs)
    assert m.action_flip_rate > 0


def test_metrics_no_contradiction_when_consistent():
    recs = [_rec(1, "PUSH_ADVANTAGE"), _rec(2, "PUSH_ADVANTAGE")]
    m = compute_metrics(recs)
    assert m.contradiction_rate == 0
    assert m.repeat_rate > 0


# ---- Golden scenarios ------------------------------------------------------
def test_golden_dir_loads():
    scenarios = load_golden_dir(_GOLDEN_DIR)
    names = {s.name for s in scenarios}
    assert "low_hp_disengage_006" in names
    assert "strong_local_push_007" in names
    assert len(scenarios) >= 5


def test_all_golden_scenarios_pass():
    scenarios = load_golden_dir(_GOLDEN_DIR)
    results = [run_golden(s) for s in scenarios]
    failed = [(r.name, r.reason) for r in results if not r.passed]
    assert not failed, "Golden scenarios en échec: %s" % failed
