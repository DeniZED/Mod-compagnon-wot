"""Tests des modèles de la Tactical Knowledge Base V2 (dataclasses pures)."""
from __future__ import annotations

import pytest

from wot_companion.tactical_knowledge import (
    Archetype, VehicleClass, VehicleTacticalProfile,
    PositionCluster, RouteCluster, HistoricalThreatZone,
)


def test_archetype_class_and_can_tank():
    assert Archetype.SNIPER_MEDIUM.vehicle_class is VehicleClass.MEDIUM
    assert Archetype.BREAKTHROUGH_HEAVY.can_tank is True
    assert Archetype.SNIPER_MEDIUM.can_tank is False   # fragile
    assert Archetype.PASSIVE_SCOUT.can_tank is False


def test_all_archetypes_have_a_class():
    for a in Archetype:
        assert a.vehicle_class is not None, a


def test_vehicle_profile_clamps_indices():
    p = VehicleTacticalProfile(
        vehicle_id="leopard_1", vehicle_class=VehicleClass.MEDIUM,
        archetype=Archetype.SNIPER_MEDIUM, mobility=1.4, armor=-0.2, clip=1)
    assert p.mobility == 1.0 and p.armor == 0.0     # bornés à [0,1]
    assert p.is_autoloader is False


def test_autoloader_flag():
    p = VehicleTacticalProfile(
        vehicle_id="e50m", vehicle_class=VehicleClass.MEDIUM,
        archetype=Archetype.AUTOLOADER_MEDIUM, clip=4)
    assert p.is_autoloader is True


def test_invalid_clip_rejected():
    with pytest.raises(ValueError):
        VehicleTacticalProfile(vehicle_id="x", vehicle_class=VehicleClass.HEAVY,
                               archetype=Archetype.SUPER_HEAVY, clip=0)


def test_position_cluster_validation():
    c = PositionCluster(
        map_id="prokhorovka", spawn="south", phase="early",
        archetype=Archetype.SNIPER_MEDIUM, center=(400, 720), radius=40,
        popularity=0.62, damage_score=1.5, survival_score=0.71,
        sample_size=120, confidence=0.9)
    assert c.damage_score == 1.0        # borné
    with pytest.raises(ValueError):
        PositionCluster(map_id="m", spawn="s", phase="early",
                        archetype=Archetype.SNIPER_MEDIUM, center=(0, 0),
                        radius=-1)


def test_route_cluster_validation():
    r = RouteCluster(
        map_id="prokhorovka", spawn="south", archetype=Archetype.FLANKER_MEDIUM,
        waypoints=[(100, 100), (300, 200), (500, 400)], usage_rate=0.4,
        sample_size=50, confidence=0.8)
    assert len(r.waypoints) == 3
    with pytest.raises(ValueError):
        RouteCluster(map_id="m", spawn="s", archetype=Archetype.FLANKER_MEDIUM,
                     sample_size=-1)


def test_historical_threat_zone_is_not_a_live_enemy():
    """Garantie Fair Play : le type historique porte un marqueur distinct et ne
    partage AUCUN champ de position ennemie live."""
    z = HistoricalThreatZone(
        map_id="prokhorovka", spawn="south", phase="mid", center=(600, 300),
        radius=60, threat_class=VehicleClass.TD, frequency=0.55, sample_size=200)
    assert z.KIND == "HISTORICAL_THREAT_ZONE"
    # Aucun champ "vehicle_id"/"is_spotted"/"live" : c'est un prior, pas une présence.
    assert not hasattr(z, "vehicle_id")
    assert not hasattr(z, "is_spotted")
