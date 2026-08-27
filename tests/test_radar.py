"""Tests du cœur radar (projection monde->pixels + état). Sans Tk."""
from __future__ import annotations

from wot_companion.ui.radar import (
    RadarProjection, RadarZone, bbox, build_radar_state)


def test_projection_north_is_up():
    p = RadarProjection(-500, 500, -500, 500, width=200, height=200, pad=0)
    cx, cz = p.to_px((0.0, 0.0))
    assert 95 <= cx <= 105 and 95 <= cz <= 105          # centre au milieu
    # z croissant (nord) -> py plus PETIT (vers le haut)
    _, py_north = p.to_px((0.0, 400.0))
    _, py_south = p.to_px((0.0, -400.0))
    assert py_north < py_south
    # x croissant (est) -> px plus GRAND (vers la droite)
    px_east, _ = p.to_px((400.0, 0.0))
    px_west, _ = p.to_px((-400.0, 0.0))
    assert px_east > px_west


def test_projection_keeps_square_aspect():
    # Emprise non carrée : la projection recadre en carré (pas de déformation).
    p = RadarProjection(-100, 100, -500, 500, width=200, height=200, pad=0)
    # un pas de 100 m en x et en z doit couvrir le meme nb de pixels
    x0 = p.to_px((0.0, 0.0))[0]
    x1 = p.to_px((100.0, 0.0))[0]
    z0 = p.to_px((0.0, 0.0))[1]
    z1 = p.to_px((0.0, 100.0))[1]
    assert abs((x1 - x0)) == abs((z1 - z0))


def test_bbox_and_fallback():
    assert bbox([]) == (-500.0, 500.0, -500.0, 500.0)
    assert bbox([(10, 20), (30, -5)]) == (10, 30, -5, 20)


def test_build_state_route_and_fairplay_fields():
    st = build_radar_state(
        extent=(-500, 500, -500, 500), own=(0.0, 0.0),
        allies=[(10, 10)], enemies_spotted=[(50, 50)],
        good_zones=[RadarZone(center=(100, 200), radius=20, kind="good")],
    )
    assert st.own == (0.0, 0.0)
    assert st.route == [(0.0, 0.0), (100, 200)]         # own -> 1re zone
    d = st.as_dict()
    assert d["enemies"] == [[50, 50]] and d["zones"][0]["kind"] == "good"


def test_build_state_no_route_without_own_or_zone():
    st = build_radar_state(extent=(-1, 1, -1, 1), own=None, allies=[],
                           enemies_spotted=[], good_zones=[])
    assert st.route == [] and st.own is None


def test_map_extent_from_base():
    from wot_companion.tactical_knowledge.models import (
        PositionCluster, VehicleClass)
    from wot_companion.tactical_knowledge.store import TacticalKnowledgeBase

    def z(cx, cz):
        return PositionCluster(map_id="m", spawn="team1", phase="mid",
                               vehicle_class=VehicleClass.HEAVY, center=(cx, cz),
                               radius=20.0, confidence=0.5)
    kb = TacticalKnowledgeBase([z(-100, -50), z(200, 300)])
    assert kb.map_extent("m") == (-100, 200, -50, 300)
    assert kb.map_extent("absente") is None
