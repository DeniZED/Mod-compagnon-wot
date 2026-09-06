"""Tests des rôles de jeu (tag->rôle) : chargement, merge, requête par rôle."""
from __future__ import annotations

from wot_companion.tactical_knowledge.models import PositionCluster, VehicleClass
from wot_companion.tactical_knowledge.roles import (
    load_role_table, merge_vehicle_roles, role_of)
from wot_companion.tactical_knowledge.store import TacticalKnowledgeBase


# ---- Table de rôles --------------------------------------------------------
def test_role_of_and_invalid_ignored():
    table = {"germany:G55_E-75": "assault_heavy", "x:y": "bogus_role"}
    # role_of ne renvoie que des rôles valides.
    assert role_of("germany:G55_E-75", table) == "assault_heavy"
    assert role_of("x:y", table) is None            # rôle invalide -> None
    assert role_of("unknown", table) is None
    assert role_of(None, table) is None


def test_merge_and_load_roundtrip(tmp_path):
    p = tmp_path / "vehicle_roles.json"
    added = merge_vehicle_roles(p, {"a:b": "sniper_medium",
                                    "c:d": "scout",
                                    "e:f": "not_a_role"})   # invalide ignoré
    assert added == 2
    table = load_role_table(str(p))
    assert table.get("a:b") == "sniper_medium"
    assert table.get("c:d") == "scout"
    assert "e:f" not in table
    # Idempotent : re-merge des mêmes -> 0 ajout.
    assert merge_vehicle_roles(p, {"a:b": "sniper_medium"}) == 0


def test_load_reads_roles_section_of_classes_file(tmp_path):
    # Accepte aussi la section "roles" d'un fichier combiné.
    p = tmp_path / "vc.json"
    p.write_text('{"classes": {"a:b": "heavy"}, "roles": {"a:b": "support_heavy"}}',
                 encoding="utf-8")
    assert load_role_table(str(p)).get("a:b") == "support_heavy"


# ---- Requête KB par rôle ---------------------------------------------------
def _z(center, role, pop=0.6):
    return PositionCluster(
        map_id="a", spawn="team1", phase="mid", vehicle_class=VehicleClass.HEAVY,
        role=role, center=center, radius=20.0, popularity=pop, effectiveness=0.8,
        damage_score=0.8, assist_score=0.0, survival_score=0.6,
        sample_size=30, confidence=1.0)


def test_role_filter_prefers_same_role_excludes_other():
    tk = TacticalKnowledgeBase([
        _z((100.0, 100.0), "assault_heavy"),
        _z((110.0, 100.0), "support_heavy"),
    ])
    # Un lourd d'ASSAUT ne doit pas se voir proposer le spot d'un lourd de SOUTIEN.
    near = tk.nearest_clusters("a", (105.0, 100.0), phase="mid",
                               vehicle_class=VehicleClass.HEAVY,
                               role="assault_heavy", max_dist=200.0, limit=5)
    roles = {c.role for c in near}
    assert roles == {"assault_heavy"}


def test_role_agnostic_zone_is_fallback():
    tk = TacticalKnowledgeBase([_z((100.0, 100.0), None)])   # zone sans rôle
    near = tk.nearest_clusters("a", (105.0, 100.0), phase="mid",
                               vehicle_class=VehicleClass.HEAVY,
                               role="assault_heavy", max_dist=200.0, limit=5)
    assert len(near) == 1                     # rôle-agnostique : repli accepté


def test_no_role_requested_keeps_all():
    tk = TacticalKnowledgeBase([
        _z((100.0, 100.0), "assault_heavy"),
        _z((110.0, 100.0), "support_heavy"),
    ])
    near = tk.nearest_clusters("a", (105.0, 100.0), phase="mid",
                               vehicle_class=VehicleClass.HEAVY, max_dist=200.0,
                               limit=5)
    assert len(near) == 2                     # sans rôle demandé : pas de filtrage
