"""Tests de la règle de placement issue des replays (positioning.replay_zones)."""
from __future__ import annotations

from wot_companion.core.context.battle_context import BattleContext
from wot_companion.core.context.features import FeatureBuilder
from wot_companion.core.rules.base import RuleContext
from wot_companion.core.rules.tactical_positioning import (
    TacticalPositioningRule, _cardinal)
from wot_companion.tactical_knowledge.models import Archetype, PositionCluster
from wot_companion.tactical_knowledge.store import TacticalKnowledgeBase


def _rc(kb, own=(0.0, 0.0), map_id="ruinberg", vclass="medium", t=60.0):
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = t
    ctx.own_pos = own
    ctx.map_id = map_id
    ctx.vehicle_class = vclass
    feats = FeatureBuilder().build(ctx)
    return RuleContext(battle=ctx, features=feats, knowledge=None, tactical_kb=kb)


def _zone(center, map_id="ruinberg", phase="early", arch=Archetype.SNIPER_MEDIUM,
          conf=1.0, pop=0.8):
    return PositionCluster(
        map_id=map_id, spawn="team1", phase=phase,
        vehicle_class=arch.vehicle_class, archetype=arch,
        center=center, radius=20.0, popularity=pop, effectiveness=0.9,
        damage_score=0.9, assist_score=0.0, survival_score=0.7,
        sample_size=30, confidence=conf)


def test_grid_cell_corners():
    from wot_companion.core.maps import grid_cell
    b = (-500, -500, 500, 500)     # minX, minZ, maxX, maxZ
    # Case + sous-case (pavé numérique : 7-8-9 nord, 1-2-3 sud).
    assert grid_cell((-490, 490), b) == "A1-7"    # nord-ouest
    assert grid_cell((490, 490), b) == "A10-9"    # nord-est
    assert grid_cell((-490, -490), b) == "K1-1"   # sud-ouest
    assert grid_cell((490, -490), b) == "K10-3"   # sud-est
    assert grid_cell((300, 300), b, sub=False) == "C9"   # sans sous-case
    assert grid_cell((0, 0), None) is None        # sans bornes -> pas de case


def test_advice_includes_grid_cell_when_bounds_known():
    kb = TacticalKnowledgeBase([_zone(center=(150.0, 150.0))])   # nord-est, <250 m
    ctx = BattleContext(battle_id="b", start_ms=0)
    ctx.elapsed_s = 60
    ctx.own_pos = (0.0, 0.0)
    ctx.map_id = "ruinberg"
    ctx.vehicle_class = "medium"
    ctx.map_bounds = (-500.0, -500.0, 500.0, 500.0)
    rc = RuleContext(battle=ctx, features=FeatureBuilder().build(ctx),
                     knowledge=None, tactical_kb=kb)
    out = TacticalPositioningRule().evaluate(rc)
    assert out and out[0].context["cell"]        # une case est fournie
    assert out[0].context["cell_suffix"].startswith(" en ")


def test_cardinal_directions():
    assert _cardinal(0, 100) == "au nord"
    assert _cardinal(100, 0) == "a l'est"
    assert _cardinal(0, -100) == "au sud"
    assert _cardinal(-100, 0) == "a l'ouest"


def test_suggests_direction_toward_effective_zone():
    kb = TacticalKnowledgeBase([_zone(center=(150.0, 0.0))])   # 150 m à l'est
    rule = TacticalPositioningRule()
    out = rule.evaluate(_rc(kb, own=(0.0, 0.0)))
    assert len(out) == 1
    c = out[0]
    assert c.action == "REPOSITION_TO_ZONE"
    assert c.context["direction"] == "a l'est"
    assert c.context["distance_m"] == 150


def test_silent_when_already_in_zone():
    kb = TacticalKnowledgeBase([_zone(center=(10.0, 0.0))])    # à ~10 m, dans la zone
    rule = TacticalPositioningRule()
    assert rule.evaluate(_rc(kb, own=(0.0, 0.0))) == []


def test_silent_without_base():
    rule = TacticalPositioningRule()
    assert rule.evaluate(_rc(TacticalKnowledgeBase([]), own=(0.0, 0.0))) == []


def test_filters_by_vehicle_class():
    # Zone de scout uniquement ; joueur en medium -> aucune correspondance.
    kb = TacticalKnowledgeBase([_zone(center=(150.0, 0.0), arch=Archetype.ACTIVE_SCOUT)])
    rule = TacticalPositioningRule()
    assert rule.evaluate(_rc(kb, own=(0.0, 0.0), vclass="medium")) == []
    # Le même joueur en light reçoit bien le conseil.
    assert rule.evaluate(_rc(kb, own=(0.0, 0.0), vclass="light"))


def test_silent_in_late_phase():
    kb = TacticalKnowledgeBase([_zone(center=(150.0, 0.0), phase="late")])
    rule = TacticalPositioningRule()
    assert rule.evaluate(_rc(kb, own=(0.0, 0.0), t=600.0)) == []


def test_low_confidence_zone_is_ignored():
    kb = TacticalKnowledgeBase([_zone(center=(150.0, 0.0), conf=0.1)])
    rule = TacticalPositioningRule()
    assert rule.evaluate(_rc(kb, own=(0.0, 0.0))) == []


def test_map_id_canonicalized_at_query():
    # Base en clé canonique "ruinberg" ; live envoie "08_ruinberg" (brut).
    kb = TacticalKnowledgeBase([_zone(center=(150.0, 0.0), map_id="ruinberg")])
    rule = TacticalPositioningRule()
    assert rule.evaluate(_rc(kb, own=(0.0, 0.0), map_id="08_ruinberg"))
