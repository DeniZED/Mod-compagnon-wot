"""Rejeu d'une timeline dans le VRAI moteur, sans jeu ni UI.

Construit un `AdviceEngine` (sans overlay), injecte les événements statiques
(carte, char, spawn), puis pour chaque tick pousse l'état (positions, HP,
comptes, horloge) et collecte le conseil éventuel. Sortie : la timeline des
conseils, prête pour `compute_metrics` ou les golden scenarios.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..core.engine import AdviceEngine
from ..core.events import EventType, RawEvent
from ..settings import Settings
from .timeline import ScenarioTimeline, StateTick


@dataclass
class AdviceRecord:
    t: float
    rule_id: Optional[str]
    action: Optional[str]
    category: Optional[str]
    score: float
    severity: Optional[str]
    text: str
    silent: bool


def _ev(kind: EventType, payload: dict, t_ms: int) -> RawEvent:
    return RawEvent(event_type=kind.value, payload=payload, timestamp_ms=t_ms)


def run_timeline(tl: ScenarioTimeline, *, settings: Optional[Settings] = None,
                 tactical_kb=None) -> List[AdviceRecord]:
    """Rejoue `tl` et retourne un AdviceRecord par tick (silencieux compris)."""
    engine = AdviceEngine(settings=settings or Settings(), overlay=None,
                          tactical_kb=tactical_kb)
    engine.start_battle("backtest", 0)

    # Contexte statique.
    if tl.map_id is not None or tl.bounds is not None:
        engine.on_event(_ev(EventType.MAP_INFO,
                             {"map_id": tl.map_id, "bounds": list(tl.bounds)
                              if tl.bounds else None}, 0))
    if tl.vehicle_class is not None or tl.vehicle_id is not None:
        engine.on_event(_ev(EventType.PLAYER_VEHICLE,
                             {"class": tl.vehicle_class,
                              "vehicle_id": tl.vehicle_id}, 0))
    if tl.spawn is not None:
        engine.on_event(_ev(EventType.SPAWN_INFO, {"spawn": tl.spawn}, 0))

    out: List[AdviceRecord] = []
    for tick in tl.ticks:
        t_ms = int(tick.t * 1000)
        engine.on_event(_ev(EventType.CLOCK_TICK,
                            {"elapsed_s": tick.t,
                             **({"remaining_s": tick.remaining_s}
                                if tick.remaining_s is not None else {})}, t_ms))
        if tick.allies_alive is not None or tick.enemies_alive is not None:
            engine.on_event(_ev(EventType.TEAM_COUNT,
                                {"allies_alive": tick.allies_alive,
                                 "enemies_alive": tick.enemies_alive}, t_ms))
        if tick.hp_ratio is not None:
            engine.on_event(_ev(EventType.PLAYER_HP_CHANGED,
                                {"hp_ratio": tick.hp_ratio}, t_ms))
        if tick.own is not None:
            engine.on_event(_ev(EventType.POSITIONS,
                                {"own": list(tick.own),
                                 "allies": [list(a) for a in tick.allies],
                                 "enemies_spotted": [list(e) for e in tick.enemies_spotted]},
                                t_ms))
        advice = engine.evaluate()
        if advice is None:
            out.append(AdviceRecord(tick.t, None, None, None, 0.0, None, "", True))
        else:
            out.append(AdviceRecord(
                tick.t, advice.rule_id, advice.action, advice.category,
                float(getattr(advice, "score", 0.0)),
                getattr(advice, "severity", None), advice.text or "", False))
    return out
