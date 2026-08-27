"""Tests de l'agrégation replays -> PositionCluster (Tactical Knowledge Base)."""
from __future__ import annotations

from wot_companion.replays.parse import ReplayDataset, ReplaySummary, VehicleResult
from wot_companion.tactical_knowledge.aggregate import build_position_clusters, phase_at
from wot_companion.tactical_knowledge.classify import default_class_of
from wot_companion.tactical_knowledge.models import Archetype, VehicleClass


def test_phase_at_bounds():
    assert phase_at(0) == "early" and phase_at(150) == "early"
    assert phase_at(151) == "mid" and phase_at(480) == "mid"
    assert phase_at(481) == "late"


def test_default_class_known_and_unknown():
    assert default_class_of("usa:A179_Black_Rock") == VehicleClass.HEAVY
    assert default_class_of("inconnu:X") is None       # -> zone agnostique
    assert default_class_of(None) is None


def _dataset(map_id, result, vehicles, trajectories):
    summary = ReplaySummary(
        map_id=map_id, map_label=map_id, vehicle=None, player_name=None,
        battle_type=1, gameplay="ctf", client_version="2.3.1", result=result)
    return ReplayDataset(summary=summary, vehicles=vehicles, trajectories=trajectories)


def _veh(vid, tag, team, dmg, is_player=False, survived=True):
    return VehicleResult(vehicle_id=vid, vehicle_type=tag, team=team,
                         damage=dmg, is_player=is_player, survived=survived)


def test_build_clusters_groups_by_cell_phase_archetype():
    # Un char hull-down qui campe une même zone -> un cluster dense.
    traj = [(float(t), 100.0 + t * 0.1, 200.0) for t in range(0, 60, 5)]  # early, ~stable
    v = _veh(1, "usa:A179_Black_Rock", team=1, dmg=4000)
    ds = _dataset("08_ruinberg", "victory", {1: v}, {1: traj})
    clusters = build_position_clusters([ds], cell_size=50.0, min_samples=3,
                                       performers_per_battle=5)
    assert clusters, "au moins une zone attendue"
    top = clusters[0]
    # map_id canonicalisé (08_ruinberg -> ruinberg) pour coller au live.
    assert top.map_id == "ruinberg" and top.phase == "early"
    assert top.vehicle_class == VehicleClass.HEAVY
    assert top.archetype == Archetype.HULL_DOWN_HEAVY   # métadonnée votée
    assert top.spawn == "team1"
    assert 90 <= top.center[0] <= 130 and top.center[1] == 200.0
    assert top.sample_size >= 3 and 0.0 < top.confidence <= 1.0
    assert top.survival_score == 1.0


def test_unknown_tag_feeds_class_agnostic_zone():
    # Char non classé : plus ignoré. Il alimente une zone AGNOSTIQUE (classe None)
    # -> aucun replay perdu (« les gagnants jouent ici »).
    traj = [(float(t), 100.0, 200.0 + t * 0.1) for t in range(0, 60, 5)]
    v = _veh(9, "mystere:Z", team=1, dmg=5000)
    ds = _dataset("map", "victory", {9: v}, {9: traj})
    clusters = build_position_clusters([ds], min_samples=3)
    assert clusters
    assert all(c.vehicle_class is None for c in clusters)
    assert all(c.archetype is None for c in clusters)


def test_min_samples_filters_sparse_cells():
    v = _veh(1, "usa:A179_Black_Rock", team=1, dmg=4000)
    ds = _dataset("m", "victory", {1: v}, {1: [(0.0, 10.0, 10.0)]})   # 1 point
    assert build_position_clusters([ds], min_samples=3) == []


def test_winners_only_excludes_losing_team():
    # Gagnant = équipe 1 ; un char de l'équipe 2 (perdante) ne doit pas peser.
    win = _veh(1, "usa:A179_Black_Rock", team=1, dmg=4000, is_player=True)
    lose = _veh(2, "germany:G56_E-100", team=2, dmg=6000)
    tr1 = [(float(t), 100.0, 100.0 + t) for t in range(0, 60, 5)]
    tr2 = [(float(t), -300.0, -300.0 - t) for t in range(0, 60, 5)]
    ds = _dataset("m", "victory", {1: win, 2: lose}, {1: tr1, 2: tr2})
    clusters = build_position_clusters([ds], winners_only=True, min_samples=3)
    assert clusters
    assert all(c.spawn == "team1" for c in clusters)
    assert all(c.vehicle_class == VehicleClass.HEAVY for c in clusters)
