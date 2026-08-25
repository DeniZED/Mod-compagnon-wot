"""Correspondance etat du compagnon <-> image de la mascotte (char cartoon).

Les etats reprennent la section 4 du cahier des charges (Idle, Analyse, Parle,
Alerte, Validation), condenses en 4 visuels selon la severite du conseil.
Module pur (sans dependance UI) : facilement testable.
"""
from __future__ import annotations

from pathlib import Path

ASSET_DIR = Path(__file__).parent / "assets"

# Severite (AdviceObject.severity) -> etat visuel.
STATE_BY_SEVERITY = {
    "INFO": "idle",
    "ATTENTION": "attention",
    "CRITICAL": "critical",
    "POSITIVE": "positive",
}

# Couleur d'accent de la bulle par etat (code couleur limite : section 4.1).
COLOR_BY_STATE = {
    "idle": "#5b8f3a",       # vert normal
    "attention": "#e0a020",  # ambre attention
    "critical": "#d0402a",   # rouge critique
    "positive": "#3aa35a",   # vert positif
}

VALID_STATES = tuple(COLOR_BY_STATE.keys())


def state_for_severity(severity: str | None) -> str:
    return STATE_BY_SEVERITY.get(severity or "", "idle")


def asset_path(state: str) -> Path:
    if state not in COLOR_BY_STATE:
        state = "idle"
    return ASSET_DIR / f"tank_{state}.png"


def accent_color(state: str) -> str:
    return COLOR_BY_STATE.get(state, COLOR_BY_STATE["idle"])
