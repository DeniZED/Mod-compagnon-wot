"""Tests du SituationState (§10) : consolidation carte + véhicule + local."""
from __future__ import annotations

from wot_companion.core.context.battle_context import BattleContext
from wot_companion.core.context.features import FeatureBuilder
from wot_companion.core.situation import build_situation
from wot_companion.tactical_knowledge.models import Archetype, VehicleClass
from wot_companion.tactical_map import SectorResolver


def _ctx(own=(0.0, 0.0), allies=None, enemies=None, a_alive=None, e_alive=None,
         hp=0.9, vclass="medium", vid=None, map_id="prokhorovka",
         bounds=(-500.0, -500.0, 500.0, 500.0), t=200.0):
    c = BattleContext(battle_id="b", start_ms=0)
    c.elapsed_s = t
    c.own_pos = own
    c.ally_positions = list(allies or [])
    c.enemy_positions_spotted = list(enemies or [])
    c.allies_alive = a_alive
    c.enemies_alive = e_alive
    c.hp_ratio = hp
    c.vehicle_class = vclass
    c.vehicle_id = vid
    c.map_id = map_id
    c.map_bounds = bounds
    return c


def _sit(ctx, sector_resolver=None):
    return build_situation(ctx, FeatureBuilder().build(ctx),
                           sector_resolver=sector_resolver)


# ---- Consolidation de base -------------------------------------------------
def test_basic_fields_populated():
    st = _sit(_ctx(a_alive=8, e_alive=6))
    assert st.battle_phase == "mid"
    assert st.global_alive_delta == 2
    assert st.player_hp_ratio == 0.9
    assert st.vehicle_class is VehicleClass.MEDIUM


def test_vehicle_profile_resolved_via_fallback():
    st = _sit(_ctx(vclass="light"))
    assert st.vehicle_profile is not None
    assert st.profile_source == "class"
    assert st.vehicle_profile.view_range > 0.7


def test_known_tag_gives_archetype_profile():
    st = _sit(_ctx(vid="germany:G56_E-100", vclass="heavy"))
    assert st.profile_source == "archetype"
    assert st.vehicle_archetype is Archetype.SUPER_HEAVY


# ---- Force locale (§7) -----------------------------------------------------
def test_local_strength_positive_when_allies_dominate():
    st = _sit(_ctx(own=(0, 0), allies=[(30, 0), (40, 0)], enemies=[(60, 0)],
                   a_alive=6, e_alive=6))
    assert st.local_allies == 2
    assert st.local_visible_enemies == 1
    assert st.local_strength_delta > 0


def test_local_strength_none_without_local_read():
    st = _sit(_ctx(own=(0, 0), allies=[], enemies=[]))
    assert st.local_strength_delta is None


def test_enemy_hp_unavailable_stays_none():
    # Contrainte de données assumée : HP adverses absents du feed.
    st = _sit(_ctx(enemies=[(30, 0)]))
    assert st.local_visible_enemy_hp is None
    assert st.local_ally_hp is None


# ---- Secteur (Tactical Map Model) ------------------------------------------
def test_sector_attached_when_resolver_and_annotated_map():
    r = SectorResolver.from_dir()
    # x=-400 sur Prokhorovka -> champ ouest (sniper line).
    st = _sit(_ctx(own=(-400.0, 0.0), map_id="prokhorovka"), sector_resolver=r)
    assert st.player_sector_id == "west_field"
    assert st.exposure is not None and st.exposure > 0.7


def test_sector_absent_on_unannotated_map_falls_back():
    r = SectorResolver.from_dir()
    st = _sit(_ctx(own=(0.0, 0.0), map_id="unknown_map"), sector_resolver=r)
    assert st.player_sector_id is None
    assert "player_sector" in st.missing
    # Le reste de la lecture reste valide (aucune carte cassée).
    assert st.vehicle_profile is not None


def test_no_resolver_leaves_sector_none():
    st = _sit(_ctx(own=(-400.0, 0.0)))
    assert st.player_sector_id is None


# ---- Confiance -------------------------------------------------------------
def test_confidence_higher_with_sector_and_data():
    r = SectorResolver.from_dir()
    with_sector = _sit(_ctx(own=(-400.0, 0.0), a_alive=8, e_alive=6,
                            vid="germany:G56_E-100", vclass="heavy"),
                       sector_resolver=r)
    without = _sit(_ctx(own=None, map_id="unknown_map", vclass="heavy"))
    assert with_sector.tactical_confidence > without.tactical_confidence


def test_sector_status_reflects_local_pressure():
    st = _sit(_ctx(own=(0, 0), enemies=[(30, 0), (40, 0)]))
    assert st.sector_status == "pressured"
    calm = _sit(_ctx(own=(0, 0), enemies=[]))
    assert calm.sector_status in ("calm", "exposed")
