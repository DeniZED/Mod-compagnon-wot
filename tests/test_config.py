"""Tests de la persistance de configuration (E8)."""
from __future__ import annotations

from wot_companion.config import (
    load_settings, save_settings, settings_to_config, config_to_settings,
)
from wot_companion.settings import Personality, Settings


def test_roundtrip_preserves_preferences(tmp_path):
    s = Settings(personality=Personality.COMMANDANT, intensity=1.3,
                 session_objective="survie")
    s.ui.streamer_mode = True
    s.ui.max_bubble_chars = 100
    path = tmp_path / "cfg.json"
    save_settings(s, path)

    loaded = load_settings(path)
    assert loaded.personality is Personality.COMMANDANT
    assert loaded.intensity == 1.3
    assert loaded.session_objective == "survie"
    assert loaded.ui.streamer_mode is True
    assert loaded.ui.max_bubble_chars == 100


def test_tactical_kb_path_persisted(tmp_path):
    path = tmp_path / "cfg.json"
    save_settings(Settings(tactical_kb_path="C:/wot/tk_base.json"), path)
    assert load_settings(path).tactical_kb_path == "C:/wot/tk_base.json"
    # chaine vide -> None (desactivation)
    save_settings(Settings(tactical_kb_path=None), path)
    assert load_settings(path).tactical_kb_path is None


def test_missing_file_returns_defaults(tmp_path):
    s = load_settings(tmp_path / "absent.json")
    assert s.personality is Personality.COACH


def test_invalid_values_are_ignored(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text('{"personality": "inconnu", "intensity": "abc", '
                    '"enabled_categories": ["BOGUS"]}', encoding="utf-8")
    s = load_settings(path)
    assert s.personality is Personality.COACH  # valeur invalide ignoree
    # enabled_categories invalide -> on garde le defaut (toutes les categories)
    assert len(s.enabled_categories) > 1


def test_corrupt_json_falls_back(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text("{ not json", encoding="utf-8")
    s = load_settings(path)
    assert isinstance(s, Settings)
