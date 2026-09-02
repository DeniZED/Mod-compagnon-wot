"""Tests du Replay Route Mining (§9) : extraction d'itinéraires par secteurs."""
from __future__ import annotations

from wot_companion.replays.parse import ReplayDataset, ReplaySummary, VehicleResult
from wot_companion.tactical_knowledge.route_mining import (
    build_route_clusters, load_routes, save_routes)
from wot_companion.tactical_map import SectorResolver

_BOUNDS = {"prokhorovka": (-500.0, -500.0, 500.0, 500.0)}


def _summary(map_id="prokhorovka"):
    return ReplaySummary(map_id=map_id, map_label=map_id, vehicle=None,
                         player_name=None, battle_type=None, gameplay=None,
                         client_version=None, result="victory")


def _veh(vid, tag="germany:G185_Leopard_120_Verbessert", team=1, dmg=3000,
         survived=True):
    return VehicleResult(vehicle_id=vid, vehicle_type=tag, team=team, damage=dmg,
                         survived=survived)


def _dataset(traj_by_vid, vehs, map_id="prokhorovka"):
    return ReplayDataset(summary=_summary(map_id),
                         vehicles={v.vehicle_id: v for v in vehs},
                         trajectories=traj_by_vid)


# Trajectoire ouest -> centre -> est sur Prokhorovka (bounds ~ -500..500).
# west_field: fx<0.30 (x<-200) ; center_rail: 0.30-0.62 ; east_hill: fx>0.62 (x>120).
def _west_to_east(t0=10.0):
    return [(t0, -400.0, 0.0), (t0 + 20, -350.0, 0.0),   # west_field
            (t0 + 40, 0.0, 0.0), (t0 + 60, 50.0, 0.0),   # center_rail
            (t0 + 80, 300.0, 0.0), (t0 + 100, 350.0, 0.0)]  # east_hill


def test_mines_dominant_route_across_sectors():
    r = SectorResolver.from_dir()
    # Trois chars suivent le même itinéraire ouest->centre->est.
    datasets = []
    for i in range(3):
        vid = 100 + i
        datasets.append(_dataset({vid: _west_to_east()}, [_veh(vid)]))
    routes = build_route_clusters(datasets, r, bounds_by_map=_BOUNDS, min_vehicles=2, performers_per_battle=1)
    assert routes, "au moins une route extraite"
    top = routes[0]
    assert top.sectors == ["west_field", "center_rail", "east_hill"]
    assert top.sample_size == 3
    assert top.map_id == "prokhorovka"
    assert len(top.waypoints) == 3


def test_rare_route_pruned_by_min_vehicles():
    r = SectorResolver.from_dir()
    ds = [_dataset({1: _west_to_east()}, [_veh(1)])]      # un seul char
    routes = build_route_clusters(ds, r, bounds_by_map=_BOUNDS, min_vehicles=2, performers_per_battle=1)
    assert routes == []


def test_unannotated_map_yields_no_routes():
    r = SectorResolver.from_dir()
    ds = [_dataset({1: _west_to_east(), 2: _west_to_east()},
                   [_veh(1), _veh(2)], map_id="unknown_map")]
    routes = build_route_clusters(ds, r, bounds_by_map=_BOUNDS, min_vehicles=1, performers_per_battle=2)
    assert routes == []


def test_consecutive_duplicates_collapsed():
    r = SectorResolver.from_dir()
    # Beaucoup de points dans west_field puis east : la séquence reste 2 secteurs.
    traj = [(10.0, -400.0, 0.0), (12.0, -390.0, 0.0), (14.0, -380.0, 0.0),
            (60.0, 300.0, 0.0), (62.0, 310.0, 0.0)]
    ds = [_dataset({i: traj}, [_veh(i)]) for i in range(2)]
    routes = build_route_clusters(ds, r, bounds_by_map=_BOUNDS, min_vehicles=2, performers_per_battle=1)
    assert routes and routes[0].sectors == ["west_field", "east_hill"]


def test_usage_rate_reflects_share():
    r = SectorResolver.from_dir()
    # 3 chars ouest->est, 1 char ouest->centre seulement (route plus courte).
    datasets = [_dataset({i: _west_to_east()}, [_veh(i)]) for i in range(3)]
    short = [(10.0, -400.0, 0.0), (30.0, 0.0, 0.0)]     # west -> center
    datasets.append(_dataset({9: short}, [_veh(9)]))
    routes = build_route_clusters(datasets, r, bounds_by_map=_BOUNDS, min_vehicles=1, performers_per_battle=1)
    by_sig = {tuple(rt.sectors): rt for rt in routes}
    main = by_sig[("west_field", "center_rail", "east_hill")]
    assert main.usage_rate == 0.75          # 3 sur 4 chars (team1)


def test_route_store_roundtrip(tmp_path):
    r = SectorResolver.from_dir()
    datasets = [_dataset({i: _west_to_east()}, [_veh(i)]) for i in range(3)]
    routes = build_route_clusters(datasets, r, bounds_by_map=_BOUNDS, min_vehicles=2, performers_per_battle=1)
    p = tmp_path / "routes.json"
    save_routes(p, routes)
    back = load_routes(p)
    assert len(back) == len(routes)
    assert back[0].sectors == routes[0].sectors
    assert back[0].sample_size == routes[0].sample_size
