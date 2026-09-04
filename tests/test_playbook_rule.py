"""Tests de la règle PLAYBOOK (Replay Prior branché au moteur live)."""
from __future__ import annotations

from wot_companion.core.context.battle_context import BattleContext
from wot_companion.core.context.features import FeatureBuilder
from wot_companion.core.rules.base import RuleContext
from wot_companion.core.rules.playbook import PlaybookRule
from wot_companion.tactical_knowledge.models import RouteCluster, VehicleClass
from wot_companion.tactical_knowledge.replay_prior import build_priors
from wot_companion.tactical_map import SectorResolver

_BOUNDS = (-500.0, -500.0, 500.0, 500.0)


def _prior():
    # Depuis west_field, les bons enchaînent vers east_hill.
    routes = [RouteCluster(map_id="prokhorovka", spawn="team1",
                           vehicle_class=VehicleClass.MEDIUM, phase="mid",
                           sectors=["west_field", "east_hill"], sample_size=40,
                           performance=0.7)]
    return build_priors(routes)


def _rc(own, hp=0.9, t=200.0, prior=None, resolver=None):
    c = BattleContext(battle_id="b", start_ms=0)
    c.elapsed_s = t
    c.own_pos = own
    c.map_id = "prokhorovka"
    c.map_bounds = _BOUNDS
    c.vehicle_class = "medium"
    c.hp_ratio = hp
    return RuleContext(battle=c, features=FeatureBuilder().build(c), knowledge=None,
                       sector_resolver=resolver or SectorResolver.from_dir(),
                       replay_prior=prior if prior is not None else _prior())


def test_advises_next_sector_from_prior():
    # Joueur dans west_field (x=-400) -> conseil de basculer vers east_hill (est).
    out = PlaybookRule().evaluate(_rc((-400.0, 0.0)))
    assert out and out[0].action == "PLAYBOOK_ROTATE"
    assert out[0].context["direction"] == "a l'est"


def test_silent_without_prior_or_resolver():
    rc = _rc((-400.0, 0.0))
    rc.replay_prior = None
    assert PlaybookRule().evaluate(rc) == []
    rc2 = _rc((-400.0, 0.0))
    rc2.sector_resolver = None
    assert PlaybookRule().evaluate(rc2) == []


def test_silent_when_already_in_target_sector():
    # Joueur déjà dans east_hill : pas de transition west->east à conseiller.
    out = PlaybookRule().evaluate(_rc((400.0, 0.0)))
    assert out == []


def test_silent_when_low_hp():
    # Bas HP : la survie prime, pas de bascule playbook.
    assert PlaybookRule().evaluate(_rc((-400.0, 0.0), hp=0.15)) == []


def test_silent_in_late_phase():
    assert PlaybookRule().evaluate(_rc((-400.0, 0.0), t=600.0)) == []


def test_opening_action_in_early_phase():
    out = PlaybookRule().evaluate(_rc((-400.0, 0.0), t=30.0))
    assert out and out[0].action == "PLAYBOOK_OPENING"
