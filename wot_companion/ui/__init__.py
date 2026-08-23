"""Couche UI : rendu textuel (personnalites) et abstraction d'affichage."""
from .renderer import TextRenderer
from .overlay import OverlaySink, ConsoleOverlay, NullOverlay, DisplayedAdvice

__all__ = [
    "TextRenderer", "OverlaySink", "ConsoleOverlay", "NullOverlay", "DisplayedAdvice",
]
