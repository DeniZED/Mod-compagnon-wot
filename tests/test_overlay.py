"""Tests de la logique de mascotte (matrice condition x expression).

L'UI Tk elle-meme n'est pas testee ici (pas d'affichage en CI), mais toute la
logique pure (choix de condition/expression, resolution vers un asset existant,
presence des 12 fichiers) l'est.
"""
from __future__ import annotations

from wot_companion.ui.mascot import (
    CONDITIONS, EXPRESSIONS, accent_color, all_asset_paths, asset_path,
    condition_for_hp, expression_for, resolve,
)


def test_condition_follows_hp():
    assert condition_for_hp(None) == "neuf"     # inconnu -> neuf
    assert condition_for_hp(0.9) == "neuf"
    assert condition_for_hp(0.5) == "neuf"
    assert condition_for_hp(0.3) == "abime"


def test_expression_by_advice():
    assert expression_for("RETREAT", "CRITICAL") == "worried"
    assert expression_for("HP", "CRITICAL") == "worried"
    assert expression_for("POSITIVE", "POSITIVE") == "positive"
    assert expression_for("HP", "ATTENTION", "PLAY_SAFE") == "grumpy"
    assert expression_for("HP", "ATTENTION", "PRESERVE_HP") == "alert"
    assert expression_for("TEMPO", "INFO") == "determined"
    assert expression_for("INITIAL_PLAN", "INFO", "ROLE_REMINDER") == "idea"
    assert expression_for("INITIAL_PLAN", "INFO", "OPEN_PRUDENT") == "idle"


def test_all_twelve_assets_exist():
    paths = all_asset_paths()
    assert len(paths) == 12
    for p in paths:
        assert p.exists() and p.stat().st_size > 0, p


def test_resolve_always_points_to_an_existing_asset():
    # Meme les combos sans image dediee doivent retomber sur un fichier existant.
    for c in CONDITIONS:
        for e in EXPRESSIONS:
            p = asset_path(c, e)
            assert p.exists(), f"{c}/{e} -> {p.name} manquant"


def test_missing_combos_use_fallback():
    assert resolve("neuf", "worried") == ("neuf", "alert")
    assert resolve("neuf", "grumpy") == ("neuf", "idle")
    assert resolve("abime", "worried") == ("abime", "worried")  # existe


def test_accent_color_by_severity():
    assert accent_color("CRITICAL").startswith("#")
    assert accent_color("INFO") != accent_color("CRITICAL")


def test_tk_overlay_module_imports_without_display():
    from wot_companion.ui import tk_overlay
    assert hasattr(tk_overlay, "TkOverlay")
    assert isinstance(tk_overlay.is_available(), bool)
