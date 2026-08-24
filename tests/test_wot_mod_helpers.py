"""Tests des helpers PURS du mod WoT (normalisation carte/char, _first).

Les hooks de jeu ne sont pas testables hors client, mais la logique de parsing
qui transforme les donnees brutes du client en identifiants du moteur, si.
Le module s'importe sans WoT (BigWorld n'est importe que dans les fonctions).
"""
from __future__ import annotations

import importlib

mod = importlib.import_module("wot_companion.game_adapter.wot_mod.mod_wotcompanion")


class _Type:
    def __init__(self, name, tags):
        self.name = name
        self.tags = set(tags)


class _Descr:
    def __init__(self, name, tags):
        self.type = _Type(name, tags)


def test_normalize_map_known_and_path_and_unknown():
    assert mod._normalize_map("05_prohorovka") == "prokhorovka"
    assert mod._normalize_map("spaces/05_prohorovka") == "prokhorovka"
    assert mod._normalize_map("himmelsdorf") == "himmelsdorf"
    assert mod._normalize_map("99_unknown_map") == "99_unknown_map"  # fallback brut
    assert mod._normalize_map(None) is None


def test_normalize_vehicle_known():
    vid, klass = mod._normalize_vehicle(_Descr("germany:G65_Leopard1", {"mediumTank"}))
    assert vid == "leopard_1"
    assert klass == "medium"


def test_normalize_vehicle_known_by_short_and_heavy():
    vid, klass = mod._normalize_vehicle(_Descr("ussr:R99_IS-7", {"heavyTank"}))
    assert vid == "is7"
    assert klass == "heavy"


def test_normalize_vehicle_unknown_falls_back_to_raw_name():
    vid, klass = mod._normalize_vehicle(_Descr("usa:A99_Foo_Bar", {"AT-SPG"}))
    assert vid == "a99_foo_bar"  # nom brut normalise
    assert klass == "td"


def test_class_from_tags():
    assert mod._class_from_tags({"lightTank"}) == "light"
    assert mod._class_from_tags({"SPG"}) == "spg"
    assert mod._class_from_tags({"unknown"}) is None


def test_first_returns_first_non_none_without_raising():
    def boom():
        raise RuntimeError("nope")
    assert mod._first(boom, lambda: None, lambda: 42) == 42
    assert mod._first(boom, lambda: None) is None
