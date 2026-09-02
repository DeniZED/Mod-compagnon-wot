"""Métriques de qualité d'une timeline de conseils (§15.2).

Ne nécessite AUCune vérité terrain : ces métriques mesurent la COHÉRENCE et la
sobriété du moteur (silence, redondance, contradictions, flips, confiance). Les
métriques de pertinence (position/route) viendront avec le mining de replays.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .runner import AdviceRecord
from .timeline import intent_of, is_contradiction

# Fenêtre (nb de conseils consécutifs) pour juger contradiction / flip.
_WINDOW = 3
# Sous ce score, un conseil est jugé « peu confiant ».
_LOW_SCORE = 40.0


@dataclass
class BacktestMetrics:
    ticks: int
    advice_count: int
    silence_rate: float
    repeat_rate: float
    contradiction_rate: float
    action_flip_rate: float
    low_confidence_rate: float
    by_action: Dict[str, int] = field(default_factory=dict)
    by_intent: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "ticks": self.ticks, "advice_count": self.advice_count,
            "silence_rate": round(self.silence_rate, 3),
            "repeat_rate": round(self.repeat_rate, 3),
            "contradiction_rate": round(self.contradiction_rate, 3),
            "action_flip_rate": round(self.action_flip_rate, 3),
            "low_confidence_rate": round(self.low_confidence_rate, 3),
            "by_action": dict(self.by_action), "by_intent": dict(self.by_intent),
        }


def compute_metrics(records: List[AdviceRecord]) -> BacktestMetrics:
    ticks = len(records)
    shown = [r for r in records if not r.silent]
    n = len(shown)

    by_action: Dict[str, int] = {}
    by_intent: Dict[str, int] = {}
    for r in shown:
        by_action[r.action or "?"] = by_action.get(r.action or "?", 0) + 1
        it = intent_of(r.action)
        by_intent[it] = by_intent.get(it, 0) + 1

    # Répétition : conseil identique (règle+action) au précédent conseil affiché.
    repeats = sum(1 for a, b in zip(shown, shown[1:])
                  if a.rule_id == b.rule_id and a.action == b.action)

    # Contradiction : deux conseils d'intentions opposées dans une fenêtre courte.
    intents = [intent_of(r.action) for r in shown]
    contradictions = 0
    for i in range(len(intents)):
        for j in range(i + 1, min(i + _WINDOW, len(intents))):
            if is_contradiction(intents[i], intents[j]):
                contradictions += 1
                break

    # Flip d'action : intention X -> Y -> X (instable) sur des intentions « fortes ».
    strong = {"ADVANCE", "RETREAT", "RELOCATE", "CAP"}
    flips = 0
    for i in range(2, len(intents)):
        a, b, c = intents[i - 2], intents[i - 1], intents[i]
        if a in strong and b in strong and a == c and a != b:
            flips += 1

    low_conf = sum(1 for r in shown if r.score < _LOW_SCORE)

    denom = n or 1
    return BacktestMetrics(
        ticks=ticks, advice_count=n,
        silence_rate=(ticks - n) / (ticks or 1),
        repeat_rate=repeats / denom,
        contradiction_rate=contradictions / denom,
        action_flip_rate=flips / denom,
        low_confidence_rate=low_conf / denom,
        by_action=by_action, by_intent=by_intent,
    )
