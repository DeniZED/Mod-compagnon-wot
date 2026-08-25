"""Tests de la logique d'overlay (mascotte). L'UI Tk elle-meme n'est pas testee
ici (pas d'affichage en CI), mais toute la logique pure l'est."""
from __future__ import annotations

from wot_companion.ui.mascot import (
    VALID_STATES, accent_color, asset_path, state_for_severity,
)


def test_severity_maps_to_state():
    assert state_for_severity("INFO") == "idle"
    assert state_for_severity("ATTENTION") == "attention"
    assert state_for_severity("CRITICAL") == "critical"
    assert state_for_severity("POSITIVE") == "positive"
    assert state_for_severity(None) == "idle"       # defaut sûr
    assert state_for_severity("???") == "idle"


def test_every_state_has_an_asset_file():
    for state in VALID_STATES:
        p = asset_path(state)
        assert p.exists(), f"image manquante pour l'etat {state}: {p}"
        assert p.stat().st_size > 0


def test_accent_color_is_hex():
    for state in VALID_STATES:
        c = accent_color(state)
        assert c.startswith("#") and len(c) == 7


def test_tk_overlay_module_imports_without_display():
    # Le module doit s'importer meme sans Tk (import de tkinter differe).
    from wot_companion.ui import tk_overlay
    assert hasattr(tk_overlay, "TkOverlay")
    assert isinstance(tk_overlay.is_available(), bool)
