"""Tests de la persistance + requête de la Tactical Knowledge Base."""
from __future__ import annotations

from wot_companion.tactical_knowledge.models import Archetype, PositionCluster
from wot_companion.tactical_knowledge.store import (
    TacticalKnowledgeBase, load_clusters, save_clusters)


def _cluster(map_id="m", center=(100.0, 200.0), phase="early",
             arch=Archetype.HULL_DOWN_HEAVY, eff=0.8, conf=1.0):
    return PositionCluster(
        map_id=map_id, spawn="team1", phase=phase, archetype=arch,
        center=center, radius=20.0, popularity=0.5, effectiveness=eff,
        damage_score=eff, assist_score=0.0, survival_score=0.6,
        sample_size=10, confidence=conf)


def test_save_load_roundtrip(tmp_path):
    clusters = [_cluster(), _cluster(center=(300.0, 400.0), arch=Archetype.ACTIVE_SCOUT)]
    p = tmp_path / "tk.json"
    save_clusters(str(p), clusters)
    back = load_clusters(str(p))
    assert len(back) == 2
    assert back[0].center == (100.0, 200.0)
    assert back[0].archetype == Archetype.HULL_DOWN_HEAVY
    assert back[1].archetype == Archetype.ACTIVE_SCOUT


def test_nearest_filters_by_map_and_distance():
    tk = TacticalKnowledgeBase([
        _cluster(map_id="a", center=(100.0, 100.0)),
        _cluster(map_id="a", center=(1000.0, 1000.0)),   # trop loin
        _cluster(map_id="b", center=(105.0, 105.0)),     # autre carte
    ])
    near = tk.nearest_clusters("a", (110.0, 110.0), max_dist=120.0)
    assert len(near) == 1 and near[0].center == (100.0, 100.0)


def test_nearest_filters_by_phase_and_archetype():
    tk = TacticalKnowledgeBase([
        _cluster(center=(100.0, 100.0), phase="early", arch=Archetype.HULL_DOWN_HEAVY),
        _cluster(center=(105.0, 105.0), phase="late", arch=Archetype.HULL_DOWN_HEAVY),
        _cluster(center=(102.0, 102.0), phase="early", arch=Archetype.ACTIVE_SCOUT),
    ])
    near = tk.nearest_clusters("m", (100.0, 100.0), phase="early",
                               archetype=Archetype.HULL_DOWN_HEAVY)
    assert len(near) == 1 and near[0].phase == "early"
    assert near[0].archetype == Archetype.HULL_DOWN_HEAVY


def test_nearest_ranks_effective_and_confident_first():
    tk = TacticalKnowledgeBase([
        _cluster(center=(100.0, 100.0), eff=0.3, conf=1.0),
        _cluster(center=(101.0, 101.0), eff=0.9, conf=1.0),   # meilleur
        _cluster(center=(102.0, 102.0), eff=0.9, conf=0.2),   # peu de data
    ])
    near = tk.nearest_clusters("m", (100.0, 100.0), limit=3)
    assert near[0].effectiveness == 0.9 and near[0].confidence == 1.0


def test_app_loads_kb_from_settings(tmp_path):
    from wot_companion.app import CompanionApp
    from wot_companion.settings import Settings
    p = tmp_path / "tk.json"
    save_clusters(str(p), [_cluster(), _cluster(center=(300.0, 400.0))])
    app = CompanionApp(settings=Settings(tactical_kb_path=str(p)))
    assert len(app.engine.tactical_kb.clusters) == 2
    app.close()


def test_app_without_kb_path_is_empty():
    from wot_companion.app import CompanionApp
    app = CompanionApp()
    assert app.engine.tactical_kb.clusters == []
    app.close()


def test_app_missing_kb_file_starts_empty(tmp_path):
    from wot_companion.app import CompanionApp
    from wot_companion.settings import Settings
    app = CompanionApp(settings=Settings(tactical_kb_path=str(tmp_path / "absent.json")))
    assert app.engine.tactical_kb.clusters == []
    app.close()
