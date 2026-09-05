"""Tests de la classification pluggable (table livrée + merge + load)."""
from __future__ import annotations

from wot_companion.tactical_knowledge.classify import (
    default_class_of, load_classifier, merge_vehicle_classes)
from wot_companion.tactical_knowledge.models import VehicleClass


# ---- Table livrée (amorce) -------------------------------------------------
def test_bundled_table_classifies_replay_tanks():
    # Chars présents dans les replays fournis -> classes connues (amorce livrée).
    assert default_class_of("china:Ch71_WZ_219") is VehicleClass.TD
    assert default_class_of("japan:J53_Ho_Ri_Shugo") is VehicleClass.TD


def test_archetype_table_still_wins():
    # Un tag connu de ARCHETYPE_BY_TAG reste classé (héritage).
    assert default_class_of("germany:G56_E-100") is VehicleClass.HEAVY


def test_unknown_tag_is_none():
    assert default_class_of("unknown:Whatever") is None


# ---- Merge (capture live -> fichier) ---------------------------------------
def test_merge_adds_new_valid_classes(tmp_path):
    p = tmp_path / "vc.json"
    added = merge_vehicle_classes(p, {"ussr:R99_Obj_777": "heavy",
                                      "usa:A99_Scout": "light"})
    assert added == 2
    clf = load_classifier(str(p))
    assert clf.class_of("ussr:R99_Obj_777") is VehicleClass.HEAVY
    assert clf.class_of("usa:A99_Scout") is VehicleClass.LIGHT


def test_merge_is_idempotent_and_skips_invalid(tmp_path):
    p = tmp_path / "vc.json"
    assert merge_vehicle_classes(p, {"a:b": "medium"}) == 1
    # Déjà présent -> non recompté ; classe invalide -> ignorée.
    assert merge_vehicle_classes(p, {"a:b": "medium", "c:d": "spatial_bogus"}) == 0


def test_load_classifier_merges_external_over_bundled(tmp_path):
    p = tmp_path / "vc.json"
    merge_vehicle_classes(p, {"china:Ch99_New": "medium"})
    clf = load_classifier(str(p))
    # Externe + amorce livrée disponibles ensemble.
    assert clf.class_of("china:Ch99_New") is VehicleClass.MEDIUM
    assert clf.class_of("china:Ch71_WZ_219") is VehicleClass.TD
