"""Tests du FairPlayFilter : whitelist, champs bannis, dependances de regles."""
from __future__ import annotations

from wot_companion.core.events import EventType, RawEvent
from wot_companion.core.fairplay import FairPlayClass, FairPlayFilter


def test_forbidden_event_is_blocked():
    f = FairPlayFilter()
    res = f.filter_event(RawEvent("ENEMY_RELOAD", {"seconds": 3.0}))
    assert not res.allowed
    assert res.fairplay_class is FairPlayClass.BLOCK
    assert any(v.kind == "forbidden_event" for v in res.violations)


def test_unknown_event_is_blocked():
    f = FairPlayFilter()
    res = f.filter_event(RawEvent("SOME_RANDOM_EVENT", {"x": 1}))
    assert not res.allowed
    assert any(v.kind == "unknown_event" for v in res.violations)


def test_non_whitelisted_field_is_stripped_not_invented():
    f = FairPlayFilter()
    res = f.filter_event(RawEvent(
        EventType.PLAYER_HP_CHANGED.value,
        {"hp_ratio": 0.5, "enemy_position": "H4"},  # champ interdit injecte
    ))
    assert res.allowed
    assert res.event is not None
    assert "hp_ratio" in res.event.payload
    assert "enemy_position" not in res.event.payload  # retire, jamais remplace
    assert any(v.kind == "forbidden_field" for v in res.violations)


def test_valid_rule_passes_validation():
    f = FairPlayFilter()
    violations = f.validate_rule("hp.preservation", ("PLAYER_HP_CHANGED.hp_ratio",))
    assert violations == []


def test_rule_depending_on_forbidden_field_is_refused():
    f = FairPlayFilter()
    violations = f.validate_rule("bad.rule", ("ENEMY_RELOAD.seconds",))
    assert violations
    assert violations[0].kind == "rule_dependency"


def test_rule_depending_on_unknown_field_is_refused():
    f = FairPlayFilter()
    violations = f.validate_rule("bad.rule2", ("PLAYER_HP_CHANGED.enemy_hp",))
    assert violations


def test_audit_report_tracks_consumed_fields():
    f = FairPlayFilter(audit=True)
    f.filter_event(RawEvent(EventType.MAP_INFO.value, {"map_id": "mines"}))
    f.filter_event(RawEvent("ENEMY_RELOAD", {"seconds": 2}))
    report = f.report.as_dict()
    assert report["allowed_count"] == 1
    assert report["blocked_count"] == 1
    assert "map_id" in report["consumed_fields"][EventType.MAP_INFO.value]
