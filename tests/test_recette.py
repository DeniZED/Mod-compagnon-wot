"""Cas de recette prioritaires REC-01 a REC-10 (section 14.2)."""
from __future__ import annotations

import pytest

from wot_companion.app import CompanionApp
from wot_companion.core.advice import AdviceObject
from wot_companion.core.context.battle_context import BattleContext
from wot_companion.core.engine import AdviceEngine
from wot_companion.core.events import EventType, RawEvent
from wot_companion.core.rules.base import Rule, RuleContext
from wot_companion.game_adapter.base import GameAdapter
from wot_companion.game_adapter.simulator import SimulatedAdapter, make_default_scenarios
from wot_companion.integrations.wargaming_api import WargamingAPIClient, WargamingAPIError
from wot_companion.profile.store import HistoryStore
from wot_companion.settings import AdviceCategory, Personality, Settings, Severity
from wot_companion.ui.overlay import NullOverlay
from wot_companion.ui.renderer import TextRenderer

from .helpers import ev, opening_events, tick


def test_rec01_missing_map_no_invented_advice():
    engine = AdviceEngine()
    engine.start_battle("b", 0)
    engine.on_event(ev(EventType.PLAYER_VEHICLE.value,
                       {"vehicle_id": "leopard_1", "class": "medium", "tier": 10}))
    # Pas de MAP_INFO : le plan initial ne doit rien inventer.
    engine.on_event(tick(1))
    advice = engine.evaluate()
    assert advice is None or advice.rule_id != "plan.initial"


def test_rec02_two_urgent_rules_single_output():
    engine = AdviceEngine()
    for e in opening_events(map_id="himmelsdorf", spawn="north", vehicle_id="e50m",
                            vehicle_class="medium"):
        engine.on_event(e)
    # Situation declenchant repli (critique) + HP bas simultanement.
    engine.on_event(ev(EventType.PLAYER_POSITION.value, {"flank": "town"}))
    engine.on_event(ev(EventType.PLAYER_HP_CHANGED.value, {"hp_ratio": 0.4}))
    engine.on_event(tick(60))
    engine.on_event(ev(EventType.ALLY_DESTROYED.value, {"flank": "town"}))
    engine.on_event(ev(EventType.ALLY_DESTROYED.value, {"flank": "town", "allies_alive": 10}))
    engine.on_event(ev(EventType.TEAM_COUNT.value, {"allies_alive": 10, "enemies_alive": 14}))
    advice = engine.evaluate()
    assert isinstance(advice, AdviceObject)  # exactement un conseil, non None
    # Le plus prioritaire (repli critique) l'emporte.
    assert advice.severity == Severity.CRITICAL.value


def test_rec03_repeated_advice_blocked_by_cooldown():
    engine = AdviceEngine()
    for e in opening_events():
        engine.on_event(e)
    engine.context.last_contribution_s = 0
    engine.context.allies_alive, engine.context.enemies_alive = 14, 12
    engine.on_event(tick(120))
    first = engine.evaluate()
    assert first is not None
    engine.on_event(tick(130))  # 10 s plus tard
    assert engine.evaluate() is None  # cooldown bloque la repetition


def test_rec04_api_loss_does_not_break_battle():
    client = WargamingAPIClient(application_id=None)  # desactive par defaut
    assert client.is_available() is False
    with pytest.raises(WargamingAPIError):
        client.account_info(123)
    # Le moteur tourne sans aucune dependance reseau.
    engine = AdviceEngine()
    for e in opening_events():
        engine.on_event(e)
    engine.on_event(tick(10))
    engine.evaluate()  # ne leve pas


def test_rec05_overlay_hidden_engine_continues():
    engine = AdviceEngine(overlay=NullOverlay())
    for e in opening_events():
        engine.on_event(e)
    engine.on_event(tick(5))
    # Aucun crash meme si l'overlay n'affiche rien.
    engine.evaluate()


def test_rec06_forbidden_field_rejected_and_logged(caplog):
    engine = AdviceEngine()
    engine.start_battle("b", 0)
    accepted = engine.on_event(RawEvent("ENEMY_RELOAD", {"seconds": 2}))
    assert accepted is False
    assert engine.fairplay.report.blocked_count >= 1


class _FaultyAdapter(GameAdapter):
    """Simule un patch WoT qui casse l'adapter en cours de flux."""
    def events(self):
        yield ev(EventType.BATTLE_START.value, {"battle_id": "b"})
        raise RuntimeError("adapter casse par un patch WoT")


def test_rec07_adapter_failure_is_contained():
    app = CompanionApp(store=HistoryStore(":memory:"))
    # Un adapter defaillant (patch WoT) ne doit pas propager de crash :
    # le compagnon se desactive proprement et signale l'echec.
    ok = app.run(_FaultyAdapter())
    assert ok is False
    # Le moteur reste dans un etat coherent, reutilisable.
    assert app.engine is not None


def test_rec07b_faulty_rule_does_not_crash_engine():
    class BoomRule(Rule):
        id = "boom"
        category = AdviceCategory.TEMPO.value
        dependencies = ()
        def evaluate(self, rc: RuleContext):
            raise ValueError("regle defaillante")

    engine = AdviceEngine(rules=[BoomRule()])
    for e in opening_events():
        engine.on_event(e)
    engine.on_event(tick(10))
    # Une regle qui plante ne casse jamais le moteur.
    assert engine.evaluate() is None


def test_rec08_battle_end_single_summary_transactional():
    store = HistoryStore(":memory:")
    app = CompanionApp(store=store)
    app.run(SimulatedAdapter(make_default_scenarios()[:1]))
    assert store.count_battles() == 1  # une seule synthese/enregistrement


def test_rec09_bubble_truncated_to_max_chars():
    settings = Settings()
    settings.ui.max_bubble_chars = 40
    renderer = TextRenderer(settings)
    advice = AdviceObject(
        rule_id="r", category="RETREAT", severity="CRITICAL", score=80,
        action="PREPARE_RETREAT", reason_code="R", template_key="retreat_flank",
        ttl_seconds=9, cooldown_key="retreat",
        context={"flank_label": "une zone au nom vraiment tres tres long"},
    )
    text = renderer.render(advice)
    assert len(text) <= 40


def test_rec10_silent_mode_no_non_critical():
    settings = Settings(personality=Personality.SILENCIEUX)
    engine = AdviceEngine(settings=settings)
    for e in opening_events():
        engine.on_event(e)
    engine.context.last_contribution_s = 0
    engine.context.allies_alive, engine.context.enemies_alive = 14, 12
    engine.on_event(tick(120))
    # Le plan initial et le tempo sont non critiques -> silence total.
    assert engine.evaluate() is None
