"""Tests du scoreur d'ACTIONS tactiques (core.actions.score_actions).

On construit un `StrategicPicture` minimal à la main pour isoler la décision
d'utilité de la lecture de partie, et on vérifie quelle action l'emporte selon
la situation (le « cerveau tactique »).
"""
from __future__ import annotations

from wot_companion.core.actions import TacticalAction, score_actions
from wot_companion.core.strategy import StrategicPicture


def _sp(**kw):
    base = dict(
        momentum="even", balance=0, allies_alive=6, enemies_alive=6,
        action_point=(0.0, 0.0), action_grid=None, dist_to_action=100.0,
        enemies_near_me=1, allies_near_me=1, sector_calm=False, hp_ratio=0.9,
        healthy=True, phase="mid", remaining_s=300.0, late=False,
        overextended=False, took_damage=False,
    )
    base.update(kw)
    return StrategicPicture(**base)


def _best(sp):
    return score_actions(sp)[0].action


def _util(sp, action):
    return next(s.utility for s in score_actions(sp) if s.action is action)


def test_scores_are_bounded_and_ranked():
    ranked = score_actions(_sp())
    assert len(ranked) == len(TacticalAction)
    assert all(0.0 <= s.utility <= 1.0 for s in ranked)
    assert [s.utility for s in ranked] == sorted(
        (s.utility for s in ranked), reverse=True)


def test_low_hp_and_took_damage_triggers_disengage():
    sp = _sp(hp_ratio=0.2, enemies_near_me=2, took_damage=True)
    assert _best(sp) is TacticalAction.DISENGAGE


def test_outnumbered_triggers_fall_back():
    sp = _sp(momentum="losing", balance=-4, allies_alive=3, enemies_alive=7,
             sector_calm=False)
    assert _best(sp) is TacticalAction.FALL_BACK


def test_cleared_sector_and_winning_triggers_relocate():
    sp = _sp(momentum="winning", balance=3, allies_alive=8, enemies_alive=5,
             sector_calm=True, enemies_near_me=0, dist_to_action=400.0)
    assert _best(sp) is TacticalAction.RELOCATE


def test_even_and_engaged_holds_silent():
    # Situation équilibrée, au contact, en forme : tenir doit gagner (silence).
    sp = _sp(momentum="even", balance=0, sector_calm=False, enemies_near_me=1)
    assert _best(sp) is TacticalAction.HOLD


def test_advantage_engaged_triggers_push():
    sp = _sp(momentum="winning", balance=4, allies_alive=8, enemies_alive=4,
             sector_calm=False, enemies_near_me=1)
    assert _best(sp) is TacticalAction.PUSH


def test_endgame_ahead_few_enemies_triggers_cap():
    sp = _sp(momentum="even", balance=1, allies_alive=3, enemies_alive=2,
             late=True, phase="late", sector_calm=False, enemies_near_me=0,
             dist_to_action=250.0)
    assert _best(sp) is TacticalAction.GO_CAP


def test_healthy_hold_beats_disengage():
    # HP corrects, non surétendu : jamais de décrochage panique.
    sp = _sp(hp_ratio=0.8, enemies_near_me=1, took_damage=False)
    assert _util(sp, TacticalAction.DISENGAGE) == 0.0


def test_calm_sector_penalises_hold():
    engaged = _util(_sp(sector_calm=False), TacticalAction.HOLD)
    calm = _util(_sp(sector_calm=True, enemies_near_me=0), TacticalAction.HOLD)
    assert calm < engaged


def test_overextension_lowers_hold():
    normal = _util(_sp(overextended=False), TacticalAction.HOLD)
    over = _util(_sp(overextended=True), TacticalAction.HOLD)
    assert over < normal
