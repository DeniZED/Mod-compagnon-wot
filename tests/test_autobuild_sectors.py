"""Tests de l'auto-génération de secteurs depuis les zones (couvre 72 cartes)."""
from __future__ import annotations

from wot_companion.tactical_knowledge.models import PositionCluster, VehicleClass
from wot_companion.tactical_map import SectorResolver, SectorType
from wot_companion.tactical_map.autobuild import (
    build_graph_from_clusters, save_graphs)

_BOUNDS = (-500.0, -500.0, 500.0, 500.0)


def _cluster(x, z, eff=0.6, surv=0.6, assist=0.1, samples=20):
    return PositionCluster(
        map_id="ensk", spawn="team1", phase="mid", vehicle_class=VehicleClass.MEDIUM,
        center=(x, z), radius=20.0, popularity=0.5, effectiveness=eff,
        damage_score=eff, assist_score=assist, survival_score=surv,
        sample_size=samples, confidence=0.8)


def test_builds_grid_graph_from_clusters():
    clusters = [_cluster(-400, 400), _cluster(0, 0), _cluster(400, -400)]
    g = build_graph_from_clusters("ensk", clusters, _BOUNDS, cols=5, rows=5,
                                  min_samples=5)
    assert g is not None
    assert len(g.sectors) == 3          # trois cellules distinctes peuplées
    # Chaque cluster tombe dans une cellule ; résolution cohérente.
    assert g.locate_norm(0.05, 0.05) is not None   # nord-ouest (x=-400,z=400)


def test_cell_below_min_samples_is_omitted():
    g = build_graph_from_clusters("ensk", [_cluster(0, 0, samples=2)], _BOUNDS,
                                  min_samples=5)
    assert g is None                    # support insuffisant -> aucune cellule


def test_high_assist_infers_spotting_zone():
    g = build_graph_from_clusters("ensk", [_cluster(0, 0, assist=0.8, eff=0.3)],
                                  _BOUNDS, min_samples=5)
    sec = next(iter(g.sectors.values()))
    assert sec.sector_type is SectorType.SPOTTING_ZONE
    assert sec.spotting_value > sec.sniper_value


def test_low_survival_high_eff_infers_sniper_line():
    g = build_graph_from_clusters("ensk", [_cluster(0, 0, surv=0.2, eff=0.7,
                                                     assist=0.0)],
                                  _BOUNDS, min_samples=5)
    sec = next(iter(g.sectors.values()))
    assert sec.sector_type is SectorType.SNIPER_LINE
    assert sec.exposure > 0.5


def test_resolver_merge_combined_adds_maps(tmp_path):
    g = build_graph_from_clusters("ensk", [_cluster(-400, 400)], _BOUNDS,
                                  min_samples=5)
    p = tmp_path / "sectors.json"
    save_graphs(p, {"ensk": g})
    r = SectorResolver.from_dir().merge_combined(p)
    assert r.graph("ensk") is not None
    # Résolution live d'une position sur la carte auto.
    sec = r.resolve("ensk", (-400.0, 400.0), _BOUNDS)
    assert sec is not None and sec.map_id == "ensk"


def test_manual_annotation_takes_priority(tmp_path):
    # Un fichier combiné qui prétend redéfinir prokhorovka ne doit PAS écraser
    # l'annotation manuelle (pilote).
    fake = {"format": 1, "maps": {"prokhorovka": {
        "map_id": "prokhorovka",
        "sectors": [{"id": "fake", "type": "open_field",
                     "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]], "tags": []}],
        "edges": []}}}
    import json
    p = tmp_path / "sectors.json"
    p.write_text(json.dumps(fake), encoding="utf-8")
    r = SectorResolver.from_dir().merge_combined(p)
    # La carte manuelle garde ses secteurs d'origine (west_field présent).
    assert "west_field" in r.graph("prokhorovka").sectors
    assert "fake" not in r.graph("prokhorovka").sectors
