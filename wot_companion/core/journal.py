"""Journaux techniques et des conseils (BAT-009).

Trace timestamp, regle, contexte minimal, score, conseil et decision d'affichage.
Un journal permet de reproduire le choix du moteur (rejeu deterministe).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("wot_companion.journal")


@dataclass
class AdviceLogEntry:
    elapsed_s: float
    battle_id: str
    decision: str                # "SHOWN" | "SILENCE"
    context: dict[str, Any]
    advice: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "elapsed_s": round(self.elapsed_s, 2), "battle_id": self.battle_id,
            "decision": self.decision, "context": self.context,
            "advice": self.advice, "candidates": self.candidates,
        }


class AdviceJournal:
    """Journal en memoire, exportable en JSON Lines."""

    def __init__(self) -> None:
        self.entries: list[AdviceLogEntry] = []

    def record(self, entry: AdviceLogEntry) -> None:
        self.entries.append(entry)
        if entry.decision == "SHOWN" and entry.advice:
            logger.info(
                "[%s t=%.1f] %s score=%.1f -> %s",
                entry.battle_id, entry.elapsed_s, entry.advice.get("rule_id"),
                entry.advice.get("score", 0), entry.advice.get("text", ""),
            )

    def export_jsonl(self, path: str | Path) -> None:
        p = Path(path)
        with p.open("w", encoding="utf-8") as fh:
            for e in self.entries:
                fh.write(json.dumps(e.as_dict(), ensure_ascii=False) + "\n")

    def shown(self) -> list[AdviceLogEntry]:
        return [e for e in self.entries if e.decision == "SHOWN"]
