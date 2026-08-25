"""Persistance de la configuration utilisateur (E8 : config persistante).

Sauvegarde/charge le sous-ensemble des reglages exposes a l'utilisateur
(personnalite, intensite, objectif de session, categories, UI) dans un fichier
JSON local. Local-first : rien n'est envoye sur le reseau.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .settings import (
    AdviceCategory, Personality, Settings, UISettings,
)

logger = logging.getLogger("wot_companion.config")

DEFAULT_CONFIG_NAME = "wot_companion_config.json"


def settings_to_config(s: Settings) -> dict[str, Any]:
    """Extrait les preferences utilisateur d'un Settings (pas l'etat interne)."""
    return {
        "personality": s.personality.value,
        "intensity": s.intensity,
        "session_objective": s.session_objective,
        "enabled_categories": sorted(s.enabled_categories),
        "language": s.language,
        "ui": {
            "anchor": s.ui.anchor,
            "max_bubble_chars": s.ui.max_bubble_chars,
            "character_visible": s.ui.character_visible,
            "streamer_mode": s.ui.streamer_mode,
            "text_scale": s.ui.text_scale,
        },
        "wargaming_api_enabled": s.wargaming_api_enabled,
        "llm_enabled": s.llm_enabled,
        "telemetry_enabled": s.telemetry_enabled,
    }


def config_to_settings(cfg: dict[str, Any], base: Settings | None = None) -> Settings:
    """Construit un Settings a partir d'un dict de config (valeurs par defaut
    pour tout ce qui manque). Les cles inconnues ou invalides sont ignorees."""
    s = base or Settings()

    if "personality" in cfg:
        try:
            s.personality = Personality(cfg["personality"])
        except ValueError:
            logger.warning("Personnalite inconnue: %r", cfg["personality"])
    if isinstance(cfg.get("intensity"), (int, float)):
        s.intensity = float(cfg["intensity"])
    if "session_objective" in cfg:
        s.session_objective = cfg["session_objective"] or None
    if isinstance(cfg.get("enabled_categories"), list):
        valid = {c.value for c in AdviceCategory}
        cats = {c for c in cfg["enabled_categories"] if c in valid}
        if cats:
            s.enabled_categories = cats
    if isinstance(cfg.get("language"), str):
        s.language = cfg["language"]

    ui = cfg.get("ui")
    if isinstance(ui, dict):
        s.ui = UISettings(
            anchor=ui.get("anchor", s.ui.anchor),
            max_bubble_chars=int(ui.get("max_bubble_chars", s.ui.max_bubble_chars)),
            character_visible=bool(ui.get("character_visible", s.ui.character_visible)),
            streamer_mode=bool(ui.get("streamer_mode", s.ui.streamer_mode)),
            text_scale=float(ui.get("text_scale", s.ui.text_scale)),
        )

    for flag in ("wargaming_api_enabled", "llm_enabled", "telemetry_enabled"):
        if flag in cfg:
            setattr(s, flag, bool(cfg[flag]))
    return s


def load_settings(path: str | Path, base: Settings | None = None) -> Settings:
    """Charge un Settings depuis le fichier de config. Retourne les valeurs par
    defaut (eventuellement `base`) si le fichier n'existe pas ou est illisible."""
    p = Path(path)
    if not p.exists():
        return base or Settings()
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Config illisible (%s), valeurs par defaut utilisees.", exc)
        return base or Settings()
    return config_to_settings(cfg, base)


def save_settings(s: Settings, path: str | Path) -> None:
    """Enregistre les preferences utilisateur dans le fichier de config."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(settings_to_config(s), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
