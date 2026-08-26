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
    assert condition_for_hp(0.6) == "neuf"      # seuil exact -> encore neuf
    assert condition_for_hp(0.5) == "abime"     # a 50% HP -> char abime
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


class _RecordingSink:
    """Sink minimal qui enregistre les etats recus (mascotte reactive HP)."""
    def __init__(self):
        self.states = []
        self.shown = []

    def show(self, displayed):
        self.shown.append(displayed)

    def clear(self):
        pass

    def notify_state(self, hp_ratio=None):
        self.states.append(hp_ratio)


def test_engine_pushes_live_hp_to_overlay():
    # La mascotte doit pouvoir suivre les HP en direct, meme sans conseil affiche.
    from wot_companion.core.engine import AdviceEngine
    from wot_companion.core.events import EventType, RawEvent

    sink = _RecordingSink()
    engine = AdviceEngine(overlay=sink)
    engine.on_event(RawEvent(EventType.BATTLE_START.value, {"battle_id": "b"}))
    engine.feed(RawEvent(EventType.PLAYER_HP_CHANGED.value, {"hp": 500, "max_hp": 1000}))
    assert sink.states and abs(sink.states[-1] - 0.5) < 1e-6
