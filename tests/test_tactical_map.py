"""Tests du Tactical Map Model (Sector, MapGraph, SectorResolver).

Le paquet est isolé et non branché au moteur : ces tests valident la brique
seule (résolution position -> secteur, fallback, graphe, chargement JSON pilote).
"""
from __future__ import annotations

from wot_companion.tactical_map import (
    MapEdge, MapGraph, Sector, SectorResolver, SectorType)


def _square(id_, x0, z0, x1, z1, **vals):
    return Sector(
        id=id_, map_id="test", sector_type=SectorType.OPEN_FIELD,
        polygon=[(x0, z0), (x1, z0), (x1, z1), (x0, z1)], **vals)


# ---- Sector : géométrie ----------------------------------------------------
def test_point_in_polygon():
    s = _square("a", 0.0, 0.0, 0.5, 0.5)
    assert s.contains_norm(0.25, 0.25) is True
    assert s.contains_norm(0.75, 0.25) is False
    assert s.contains_norm(0.6, 0.6) is False


def test_values_are_clamped():
    s = _square("a", 0.0, 0.0, 1.0, 1.0, risk_level=1.7, cover=-0.3)
    assert s.risk_level == 1.0
    assert s.cover == 0.0


def test_polygon_needs_three_vertices():
    import pytest
    with pytest.raises(ValueError):
        Sector(id="x", map_id="m", sector_type=SectorType.CITY,
               polygon=[(0.0, 0.0), (1.0, 1.0)])


# ---- MapGraph --------------------------------------------------------------
def test_graph_neighbors_and_edges():
    g = MapGraph(map_id="test")
    g.add_sector(_square("west", 0.0, 0.0, 0.5, 1.0))
    g.add_sector(_square("east", 0.5, 0.0, 1.0, 1.0))
    g.add_edge(MapEdge(from_id="west", to_id="east", distance=0.4))
    assert [s.id for s in g.neighbors("west")] == ["east"]
    assert g.neighbors("east") == []
    assert g.edge_between("west", "east").distance == 0.4
    assert g.edge_between("east", "west") is None


def test_graph_locate():
    g = MapGraph(map_id="test")
    g.add_sector(_square("west", 0.0, 0.0, 0.5, 1.0))
    g.add_sector(_square("east", 0.5, 0.0, 1.0, 1.0))
    assert g.locate_norm(0.1, 0.5).id == "west"
    assert g.locate_norm(0.9, 0.5).id == "east"


# ---- SectorResolver : normalisation + fallback -----------------------------
def _resolver_one_map():
    g = MapGraph(map_id="prokhorovka")
    g.add_sector(_square("west", 0.0, 0.0, 0.5, 1.0))
    g.add_sector(_square("east", 0.5, 0.0, 1.0, 1.0))
    return SectorResolver({"prokhorovka": g})


def test_resolve_projects_world_to_sector():
    r = _resolver_one_map()
    bounds = (-500.0, -500.0, 500.0, 500.0)   # minX,minZ,maxX,maxZ
    # x=-400 (ouest) -> fx~0.1 -> secteur ouest.
    assert r.resolve("prokhorovka", (-400.0, 0.0), bounds).id == "west"
    # x=+400 (est) -> fx~0.9 -> secteur est.
    assert r.resolve("prokhorovka", (400.0, 0.0), bounds).id == "east"


def test_resolve_uses_canonical_map_id():
    r = _resolver_one_map()
    bounds = (-500.0, -500.0, 500.0, 500.0)
    # Nom live brut avec préfixe numérique -> canonicalisé.
    assert r.resolve("00_prokhorovka", (-400.0, 0.0), bounds).id == "west"


def test_resolve_fallback_unknown_map():
    r = _resolver_one_map()
    bounds = (-500.0, -500.0, 500.0, 500.0)
    assert r.resolve("unknown_map", (0.0, 0.0), bounds) is None


def test_resolve_fallback_without_bounds():
    r = _resolver_one_map()
    assert r.resolve("prokhorovka", (0.0, 0.0), None) is None
    assert r.resolve("prokhorovka", (0.0, 0.0), (0, 0, 0, 0)) is None


# ---- Chargement des annotations pilotes livrées ----------------------------
def test_pilot_maps_load_from_data_dir():
    r = SectorResolver.from_dir()
    assert r.graph("prokhorovka") is not None
    assert r.graph("ruinberg") is not None
    # Chaque carte pilote a des secteurs cohérents.
    prok = r.graph("prokhorovka")
    assert "west_field" in prok.sectors
    assert prok.sectors["west_field"].sector_type is SectorType.SNIPER_LINE


def test_pilot_ruinberg_city_is_brawl_zone():
    r = SectorResolver.from_dir()
    city = r.graph("ruinberg").sectors["city_east"]
    assert city.sector_type is SectorType.CITY
    assert city.brawl_value > city.sniper_value       # ville = corps-à-corps
    assert city.cover > city.exposure                 # beaucoup de couverture


def test_pilot_prokhorovka_west_is_open():
    r = SectorResolver.from_dir()
    west = r.graph("prokhorovka").sectors["west_field"]
    assert west.exposure > 0.7                         # champ très exposé
    assert west.sniper_value > west.brawl_value
