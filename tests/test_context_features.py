"""Tests du BattleContext et du FeatureBuilder."""
from __future__ import annotations

from wot_companion.core.context.battle_context import BattleContext, BattlePhase
from wot_companion.core.context.features import FeatureBuilder
from wot_companion.core.events import EventType, RawEvent


def _ctx() -> BattleContext:
    return BattleContext(battle_id="b", start_ms=0)


def test_hp_ratio_from_hp_and_max():
    ctx = _ctx()
    ctx.apply(RawEvent(EventType.PLAYER_HP_CHANGED.value, {"hp": 500, "max_hp": 2000}))
    assert ctx.hp_ratio == 0.25


def test_phase_transitions_and_hysteresis():
    ctx = _ctx()
    fb = FeatureBuilder()
    ctx.elapsed_s = 10
    assert fb.build(ctx).phase is BattlePhase.EARLY
    ctx.elapsed_s = 200  # au-dela d'EARLY_MAX mais nouvelle phase doit tenir
    f = fb.build(ctx)
    assert f.phase in (BattlePhase.EARLY, BattlePhase.MID)
    ctx.elapsed_s = 220
    assert fb.build(ctx).phase is BattlePhase.MID


def test_numeric_balance_and_outnumbered():
    ctx = _ctx()
    assert ctx.numeric_balance() is None  # fallback: inconnu
    ctx.allies_alive, ctx.enemies_alive = 5, 8
    assert ctx.numeric_balance() == -3
    f = FeatureBuilder().build(ctx)
    assert f.outnumbered_locally is True


def test_flank_collapse_requires_recent_losses():
    ctx = _ctx()
    ctx.player_flank = "town"
    ctx.elapsed_s = 100
    ctx.apply(RawEvent(EventType.ALLY_DESTROYED.value, {"flank": "town"}))
    ctx.apply(RawEvent(EventType.ALLY_DESTROYED.value, {"flank": "town"}))
    assert FeatureBuilder().build(ctx).flank_collapsing is True
    # 90 s plus tard sans nouvelle perte : l'alerte n'est plus active.
    ctx.elapsed_s = 190
    assert FeatureBuilder().build(ctx).flank_collapsing is False


def test_contribution_updates_last_contribution_time():
    ctx = _ctx()
    ctx.elapsed_s = 50
    ctx.apply(RawEvent(EventType.PLAYER_DAMAGE_DEALT.value, {"total_damage": 300}))
    assert ctx.last_contribution_s == 50
    ctx.elapsed_s = 130
    f = FeatureBuilder().build(ctx)
    assert f.time_since_contribution_s == 80
