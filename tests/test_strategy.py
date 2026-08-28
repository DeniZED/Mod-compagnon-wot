"""Tests du moteur MACRO : SituationAnalyzer + règle stratégique."""
from __future__ import annotations

from wot_companion.core.context.battle_context import BattleContext
from wot_companion.core.context.features import FeatureBuilder
from wot_companion.core.rules.base import RuleContext
from wot_companion.core.rules.strategy import MacroStrategyRule
from wot_companion.core.strategy import analyze


def _ctx(t=300.0, own=(0.0, 0.0), allies=None, enemies=None,
         a_alive=None, e_alive=None, hp=0.9, bounds=(-500, -500, 500, 500)):
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = t
    ctx.own_pos = own
    ctx.ally_positions = list(allies or [])
    ctx.enemy_positions_spotted = list(enemies or [])
    ctx.allies_alive = a_alive
    ctx.enemies_alive = e_alive
    ctx.hp_ratio = hp
    ctx.map_bounds = bounds
    return ctx


def _pic(ctx):
    return analyze(ctx, FeatureBuilder().build(ctx), ctx.map_bounds)


def _eval(ctx):
    return MacroStrategyRule().evaluate(
        RuleContext(battle=ctx, features=FeatureBuilder().build(ctx), knowledge=None))


# ---- SituationAnalyzer -----------------------------------------------------
def test_momentum_from_balance():
    assert _pic(_ctx(a_alive=8, e_alive=5)).momentum == "winning"
    assert _pic(_ctx(a_alive=4, e_alive=8)).momentum == "losing"
    assert _pic(_ctx(a_alive=7, e_alive=7)).momentum == "even"
    assert _pic(_ctx()).momentum == "unknown"


def test_action_point_is_enemy_centroid_with_grid():
    sp = _pic(_ctx(own=(-400, -400), enemies=[(300, 300), (340, 260)]))
    assert sp.action_point == (320.0, 280.0)
    assert sp.action_grid is not None            # case fournie (bornes connues)
    assert sp.dist_to_action and sp.dist_to_action > 320


def test_sector_calm_when_no_enemies_near_and_far_from_front():
    sp = _pic(_ctx(own=(-400, -400), enemies=[(350, 350)]))
    assert sp.sector_calm is True
    sp2 = _pic(_ctx(own=(340, 340), enemies=[(350, 350)]))   # au contact
    assert sp2.sector_calm is False


# ---- Règle macro -----------------------------------------------------------
def test_relocate_when_sector_cleared_and_not_losing():
    # Secteur nettoyé (aucun ennemi proche), front à l'opposé, sain, égalité.
    ctx = _ctx(own=(-400, -400), enemies=[(350, 350)], a_alive=6, e_alive=6)
    out = _eval(ctx)
    assert out and out[0].action == "RELOCATE_TO_ACTION"
    assert out[0].context["direction"] == "au nord-est"


def test_defend_when_outnumbered():
    ctx = _ctx(own=(0, 0), enemies=[(50, 50)], a_alive=3, e_alive=7)
    out = _eval(ctx)
    assert out and out[0].action == "FALL_BACK_DEFEND"
    assert out[0].context["enemies"] == 7


def test_push_when_advantage_and_engaged_near_front():
    # Avantage ET proche du front (secteur non calme) -> presser.
    ctx = _ctx(own=(300, 300), enemies=[(350, 350)], a_alive=8, e_alive=4)
    out = _eval(ctx)
    assert out and out[0].action == "PUSH_ADVANTAGE"


def test_no_macro_in_early_phase():
    ctx = _ctx(t=30.0, own=(-400, -400), enemies=[(350, 350)], a_alive=8, e_alive=4)
    assert _eval(ctx) == []


def test_losing_takes_priority_over_relocate():
    # Secteur calme MAIS on perd -> on ne dit pas de traverser, on défend.
    ctx = _ctx(own=(-400, -400), enemies=[(350, 350)], a_alive=3, e_alive=8)
    out = _eval(ctx)
    assert out and out[0].action == "FALL_BACK_DEFEND"
