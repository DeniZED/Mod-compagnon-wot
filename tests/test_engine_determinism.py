"""Determinisme du moteur : memes evenements + memes versions => meme sortie.

Fondamental pour la confiance, les tests et le Fair Play (section 7).
"""
from __future__ import annotations

from wot_companion.core.engine import AdviceEngine
from wot_companion.game_adapter.simulator import SimulatedAdapter, make_default_scenarios
from wot_companion.settings import Settings


def _run_digest() -> list[tuple]:
    engine = AdviceEngine(settings=Settings())
    adapter = SimulatedAdapter(make_default_scenarios())
    for event in adapter.events():
        engine.feed(event)
    return [
        (e.battle_id, round(e.elapsed_s, 1), e.decision,
         (e.advice or {}).get("rule_id"), round((e.advice or {}).get("score", 0), 2),
         (e.advice or {}).get("text"))
        for e in engine.journal.entries
    ]


def test_engine_is_deterministic_across_runs():
    assert _run_digest() == _run_digest()


def test_engine_produces_advice():
    digest = _run_digest()
    shown = [d for d in digest if d[2] == "SHOWN"]
    assert shown, "le moteur doit produire au moins un conseil"
    # Le plan initial de Prokhorovka doit apparaitre.
    assert any(d[3] == "plan.initial" for d in shown)
    assert any(d[3] == "retreat.flank_collapse" for d in shown)
