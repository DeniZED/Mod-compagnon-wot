"""Tests du Replay Prior (§ étape 8) : ouverture + transition, fallback classe."""
from __future__ import annotations

from wot_companion.tactical_knowledge.models import RouteCluster, VehicleClass
from wot_companion.tactical_knowledge.replay_prior import ReplayPrior, build_priors


def _route(sectors, spawn="team1", vclass=VehicleClass.MEDIUM, phase="early",
           samples=10, perf=0.6, map_id="prokhorovka"):
    return RouteCluster(map_id=map_id, spawn=spawn, vehicle_class=vclass,
                        phase=phase, sectors=sectors, sample_size=samples,
                        performance=perf)


def test_opening_ranks_dominant_first_destination():
    # sectors[0] = spawn (north_base) ; l'ouverture est la 1re DESTINATION.
    routes = [
        _route(["north_base", "west_field", "center_rail"], samples=30),
        _route(["north_base", "west_field", "east_hill"], samples=20),
        _route(["north_base", "east_hill"], samples=5),
    ]
    p = build_priors(routes)
    op = p.opening("prokhorovka", "team1", VehicleClass.MEDIUM, "early")
    assert op[0].sector == "west_field"          # 50 vs 5 échantillons
    assert op[0].sector != "north_base"          # jamais le secteur de spawn
    assert op[0].prob > 0.8
    assert abs(sum(s.prob for s in op) - 1.0) < 1e-6


def test_transition_from_sector():
    routes = [
        _route(["west_field", "center_rail"], samples=25),
        _route(["west_field", "center_rail"], samples=25),
        _route(["west_field", "east_hill"], samples=10),
    ]
    p = build_priors(routes)
    nxt = p.next_sector("prokhorovka", "west_field", VehicleClass.MEDIUM)
    assert nxt[0].sector == "center_rail"
    assert nxt[0].prob > nxt[1].prob


def test_class_fallback_to_agnostic():
    # Prior construit pour medium ; requête light -> repli agnostique (*).
    routes = [_route(["north_base", "west_field", "center_rail"],
                     vclass=VehicleClass.MEDIUM, samples=15)]
    p = build_priors(routes)
    op = p.opening("prokhorovka", "team1", VehicleClass.LIGHT, "early")
    assert op and op[0].sector == "west_field"   # via l'agrégat toutes classes


def test_unknown_query_returns_empty():
    p = build_priors([_route(["west_field", "center_rail"])])
    assert p.opening("unknown", "team1", VehicleClass.MEDIUM) == []
    assert p.next_sector("unknown", "x") == []


def test_prior_roundtrip(tmp_path):
    routes = [_route(["west_field", "center_rail"], samples=20),
              _route(["west_field", "east_hill"], samples=10)]
    p = build_priors(routes)
    fp = tmp_path / "priors.json"
    p.save(fp)
    back = ReplayPrior.load(fp)
    a = p.opening("prokhorovka", "team1", VehicleClass.MEDIUM)
    b = back.opening("prokhorovka", "team1", VehicleClass.MEDIUM)
    assert [s.sector for s in a] == [s.sector for s in b]
    assert abs(a[0].prob - b[0].prob) < 1e-3      # sauvegarde arrondie à 4 déc.


def test_empty_sectors_ignored():
    p = build_priors([_route([]),
                      _route(["north_base", "west_field", "center_rail"])])
    op = p.opening("prokhorovka", "team1", VehicleClass.MEDIUM)
    assert op and op[0].sector == "west_field"
