"""Golden Scenarios (§16) : situations de référence à comportement attendu.

Un scénario décrit un état (ou une courte timeline) et ce qu'on ATTEND du
moteur : intentions acceptables, intentions interdites, silence attendu. On
rejoue le scénario et on vérifie le dernier conseil (ou le silence).

Format JSON portable (dossier `tests/golden_scenarios/`), donc extensible sans
code : un scénario = un fichier.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

from .runner import AdviceRecord, run_timeline
from .timeline import ScenarioTimeline, StateTick, intent_of


@dataclass
class GoldenScenario:
    name: str
    timeline: ScenarioTimeline
    acceptable_intents: Set[str] = field(default_factory=set)
    forbidden_intents: Set[str] = field(default_factory=set)
    expect_silence: bool = False


@dataclass
class GoldenResult:
    name: str
    passed: bool
    reason: str
    got_action: Optional[str]
    got_intent: Optional[str]
    silent: bool


def scenario_from_json(d: dict) -> GoldenScenario:
    tl = ScenarioTimeline(
        map_id=d.get("map_id"),
        bounds=tuple(d["bounds"]) if d.get("bounds") else None,
        vehicle_class=d.get("vehicle_class"),
        vehicle_id=d.get("vehicle_id"),
        spawn=d.get("spawn"),
        ticks=[StateTick(
            t=float(tk["t"]),
            own=tuple(tk["own"]) if tk.get("own") else None,
            allies=[tuple(a) for a in tk.get("allies", [])],
            enemies_spotted=[tuple(e) for e in tk.get("enemies_spotted", [])],
            hp_ratio=tk.get("hp"),
            allies_alive=tk.get("allies_alive"),
            enemies_alive=tk.get("enemies_alive"),
            remaining_s=tk.get("remaining_s"),
        ) for tk in d.get("ticks", [])],
    )
    return GoldenScenario(
        name=d["name"], timeline=tl,
        acceptable_intents=set(d.get("acceptable_intents", [])),
        forbidden_intents=set(d.get("forbidden_intents", [])),
        expect_silence=bool(d.get("expect_silence", False)),
    )


def load_golden_dir(path) -> List[GoldenScenario]:
    directory = Path(path)
    out: List[GoldenScenario] = []
    if directory.is_dir():
        for fp in sorted(directory.glob("*.json")):
            out.append(scenario_from_json(json.loads(fp.read_text(encoding="utf-8"))))
    return out


def _last_shown(records: List[AdviceRecord]) -> Optional[AdviceRecord]:
    for r in reversed(records):
        if not r.silent:
            return r
    return None


def run_golden(sc: GoldenScenario, *, settings=None, tactical_kb=None) -> GoldenResult:
    """Rejoue un scénario et vérifie l'attendu. Le dernier conseil fait foi."""
    records = run_timeline(sc.timeline, settings=settings, tactical_kb=tactical_kb)
    shown = _last_shown(records)

    if sc.expect_silence:
        if shown is None:
            return GoldenResult(sc.name, True, "silence attendu et obtenu",
                                None, None, True)
        return GoldenResult(sc.name, False,
                            "silence attendu mais conseil '%s'" % shown.action,
                            shown.action, intent_of(shown.action), False)

    if shown is None:
        return GoldenResult(sc.name, False, "conseil attendu mais silence",
                            None, None, True)

    intent = intent_of(shown.action)
    if intent in sc.forbidden_intents:
        return GoldenResult(sc.name, False,
                            "intention interdite '%s' (action %s)" % (intent, shown.action),
                            shown.action, intent, False)
    if sc.acceptable_intents and intent not in sc.acceptable_intents:
        return GoldenResult(sc.name, False,
                            "intention '%s' hors des acceptables %s (action %s)"
                            % (intent, sorted(sc.acceptable_intents), shown.action),
                            shown.action, intent, False)
    return GoldenResult(sc.name, True, "conforme", shown.action, intent, False)
