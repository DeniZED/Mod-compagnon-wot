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


def test_projection_maps_bounds_1to1_to_canvas():
    # Mapping EXACT : les coins de l'emprise tombent aux coins du canvas (comme
    # la minimap qui remplit son carré avec les bornes). Pas de marge.
    p = RadarProjection(-500, 500, -500, 500, width=200, height=200, pad=0)
    assert p.to_px((-500, 500)) == (0, 0)          # NO -> haut-gauche
    assert p.to_px((500, -500)) == (200, 200)      # SE -> bas-droite
    assert p.to_px((0, 0)) == (100, 100)           # centre


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


def test_app_clears_radar_on_garage():
    from wot_companion.app import CompanionApp
    from wot_companion.core.events import RawEvent, EventType

    class FO:
        def __init__(self): self.radar_cleared = False
        def notify_state(self, **k): pass
        def notify_radar(self, st): pass
        def clear_radar(self): self.radar_cleared = True
        def show(self, *a): pass
        def show_garage(self, t): pass
        def clear(self): pass

    ov = FO()
    app = CompanionApp(overlay=ov)
    app._handle(RawEvent(EventType.BATTLE_START.value, {"battle_id": "b"}, 0, "b"))
    app._handle(RawEvent(EventType.BATTLE_END.value, {"battle_id": "b"}, 0, "b"))
    assert ov.radar_cleared is True
    app.close()


def test_engine_stops_advising_when_player_dead():
    from wot_companion.core.engine import AdviceEngine
    from wot_companion.core.events import RawEvent, EventType
    eng = AdviceEngine()
    eng.on_event(RawEvent(EventType.BATTLE_START.value, {"battle_id": "b"}, 0, "b"))
    eng.on_event(RawEvent(EventType.CLOCK_TICK.value, {"elapsed_s": 100}, 0, "b"))
    eng.on_event(RawEvent(EventType.PLAYER_HP_CHANGED.value, {"hp": 0, "max_hp": 2000}, 0, "b"))
    assert eng.evaluate() is None
    assert eng._dead is True
