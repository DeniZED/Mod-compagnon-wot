"""Abstraction d'affichage (sink) du compagnon 2D.

Le moteur ne connait que l'interface `OverlaySink`. L'overlay reel (integre au
client ou externe) sera decide apres le POC (section 19). En attendant, une
implementation console permet de tout tester de bout en bout.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..core.advice import AdviceObject


@dataclass
class DisplayedAdvice:
    advice: AdviceObject
    text: str
    color: str  # normal | attention | critical | positive


_SEVERITY_COLOR = {
    "INFO": "normal", "ATTENTION": "attention",
    "CRITICAL": "critical", "POSITIVE": "positive",
}


def color_for(advice: AdviceObject) -> str:
    return _SEVERITY_COLOR.get(advice.severity, "normal")


class OverlaySink(ABC):
    @abstractmethod
    def show(self, displayed: DisplayedAdvice) -> None: ...

    @abstractmethod
    def clear(self) -> None: ...

    def notify_state(self, hp_ratio: float | None = None) -> None:
        """Etat de jeu continu (HP...) independant des conseils : permet a la
        mascotte de suivre l'etat du char en direct. No-op par defaut."""
        return None


class NullOverlay(OverlaySink):
    """Ne fait rien : personnage totalement masque, sans notification."""
    def show(self, displayed: DisplayedAdvice) -> None:  # noqa: D401
        pass

    def clear(self) -> None:
        pass


class ConsoleOverlay(OverlaySink):
    """Affichage texte en console, avec code couleur (pour demo/tests/debug)."""

    _ANSI = {
        "normal": "\033[37m", "attention": "\033[33m",
        "critical": "\033[31m", "positive": "\033[32m",
    }
    _RESET = "\033[0m"

    def __init__(self, use_color: bool = True) -> None:
        self.use_color = use_color
        self.history: list[DisplayedAdvice] = []

    def show(self, displayed: DisplayedAdvice) -> None:
        self.history.append(displayed)
        tag = f"[{displayed.color.upper()}]"
        line = f"{tag:<12} {displayed.text}"
        if self.use_color:
            c = self._ANSI.get(displayed.color, "")
            line = f"{c}{line}{self._RESET}"
        print(line)

    def clear(self) -> None:
        pass
