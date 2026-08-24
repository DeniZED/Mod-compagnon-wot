"""TextRenderer : transforme un AdviceObject en texte selon la personnalite.

Le rendu est la SEULE etape ou le texte final est produit. Le LLM optionnel
peut reformuler ce texte, jamais decider de l'action (section 7.4).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ..settings import Personality, Settings
from ..core.advice import AdviceObject

logger = logging.getLogger("wot_companion.ui")
_TEMPLATES_PATH = Path(__file__).parent / "templates.json"


class TextRenderer:
    def __init__(self, settings: Settings, templates_path: Path | None = None) -> None:
        self.settings = settings
        doc = json.loads((templates_path or _TEMPLATES_PATH).read_text(encoding="utf-8"))
        self._templates: dict[str, dict[str, str]] = doc["templates"]
        self.version = doc.get("version", "unknown")

    def render(self, advice: AdviceObject) -> str:
        personality = self.settings.personality.value
        variants = self._templates.get(advice.template_key)
        if not variants:
            logger.warning("Template manquant: %s", advice.template_key)
            text = advice.context.get("explanation") or advice.action
        else:
            template = variants.get(personality) or variants.get(Personality.COACH.value)
            text = self._safe_format(template, advice.context)

        text = self._apply_streamer_mode(text)
        return self._truncate(text)

    def _safe_format(self, template: str, context: dict) -> str:
        """Formate en tolerant les cles manquantes (fallback sûr, pas d'erreur)."""
        class _Default(dict):
            def __missing__(self, key):  # noqa: D401
                return "?"
        try:
            return template.format_map(_Default(context))
        except Exception:  # pragma: no cover - securite
            return template

    def _apply_streamer_mode(self, text: str) -> str:
        # Les templates ne contiennent aucun identifiant prive ; le mode streamer
        # reste un point d'extension (masquage pseudo/ids) si des donnees en
        # contenaient un jour.
        return text

    def _truncate(self, text: str) -> str:
        limit = self.settings.ui.max_bubble_chars
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "…"
