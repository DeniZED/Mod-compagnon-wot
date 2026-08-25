"""Mascotte cartoon : matrice CONDITION x EXPRESSION (12 visuels).

- CONDITION suit l'etat du char du joueur : `neuf` (HP eleves) ou `abime` (HP bas).
- EXPRESSION suit le type de conseil : confiant, rire, determine, idee, alerte,
  grincheux, inquiet (etats section 4 du cahier des charges).

Module pur (sans dependance UI), donc facilement testable.
"""
from __future__ import annotations

from pathlib import Path

ASSET_DIR = Path(__file__).parent / "assets"

CONDITIONS = ("neuf", "abime")
EXPRESSIONS = ("idle", "positive", "determined", "idea", "alert", "grumpy", "worried")

# Combos reellement fournis en image (les 12 assets).
_AVAILABLE = {
    ("neuf", "idle"), ("neuf", "positive"), ("neuf", "determined"),
    ("neuf", "idea"), ("neuf", "alert"),
    ("abime", "idle"), ("abime", "positive"), ("abime", "determined"),
    ("abime", "idea"), ("abime", "alert"), ("abime", "grumpy"), ("abime", "worried"),
}
# Repli quand un combo n'a pas d'image dediee.
_FALLBACK = {
    ("neuf", "grumpy"): ("neuf", "idle"),
    ("neuf", "worried"): ("neuf", "alert"),
}

# Seuil HP en dessous duquel la mascotte passe en condition "abime".
DAMAGED_HP_RATIO = 0.5

# Couleur d'accent de la bulle selon la severite (code couleur limite, 4.1).
_ACCENT_BY_SEVERITY = {
    "INFO": "#5b8f3a", "ATTENTION": "#e0a020",
    "CRITICAL": "#d0402a", "POSITIVE": "#3aa35a",
}


def condition_for_hp(hp_ratio: float | None) -> str:
    """Char neuf si HP inconnus ou eleves, abime si bas."""
    if hp_ratio is None:
        return "neuf"
    return "neuf" if hp_ratio >= DAMAGED_HP_RATIO else "abime"


def expression_for(category: str | None, severity: str | None,
                   action: str | None = None) -> str:
    """Choisit l'expression a partir du conseil (categorie/severite/action)."""
    cat = (category or "").upper()
    sev = (severity or "").upper()

    if sev == "CRITICAL" or cat == "RETREAT":
        return "worried"
    if sev == "POSITIVE" or cat == "POSITIVE":
        return "positive"
    if cat == "HP" and (action or "") == "PLAY_SAFE":
        return "grumpy"
    if sev == "ATTENTION":
        return "alert"
    if cat in ("TEMPO", "ENDGAME", "ROTATION"):
        return "determined"
    if cat == "INITIAL_PLAN":
        return "idea" if (action or "") == "ROLE_REMINDER" else "idle"
    return "idle"


def resolve(condition: str, expression: str) -> tuple[str, str]:
    """Ramene un combo a un combo disponible (via repli si necessaire)."""
    if condition not in CONDITIONS:
        condition = "neuf"
    if expression not in EXPRESSIONS:
        expression = "idle"
    key = (condition, expression)
    if key in _AVAILABLE:
        return key
    if key in _FALLBACK:
        return _FALLBACK[key]
    return (condition, "idle")


def asset_path(condition: str, expression: str) -> Path:
    c, e = resolve(condition, expression)
    return ASSET_DIR / f"tank_{c}_{e}.png"


def all_asset_paths() -> list[Path]:
    return [ASSET_DIR / f"tank_{c}_{e}.png" for (c, e) in sorted(_AVAILABLE)]


def accent_color(severity: str | None) -> str:
    return _ACCENT_BY_SEVERITY.get((severity or "").upper(), _ACCENT_BY_SEVERITY["INFO"])
