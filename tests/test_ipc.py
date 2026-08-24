"""Tests du pont IPC socket : round-trip, controle, moteur pilote par le socket.

Reproduit le chainage reel (source -> pont -> moteur) sur la boucle locale.
"""
from __future__ import annotations

import threading
import time

from wot_companion.core.engine import AdviceEngine
from wot_companion.core.events import EventType
from wot_companion.game_adapter.base import EventEnvelope
from wot_companion.game_adapter.ipc import EnvelopeClient, SocketEventServerAdapter

from .helpers import opening_events, tick


def _start_server(control_handler=None) -> SocketEventServerAdapter:
    adapter = SocketEventServerAdapter(
        port=0, control_handler=control_handler, single_connection=True
    )
    adapter.start()
    return adapter


def test_socket_roundtrip_and_control_separation():
    controls: list[EventEnvelope] = []
    adapter = _start_server(control_handler=controls.append)
    received = []

    t = threading.Thread(target=lambda: received.extend(adapter.events()), daemon=True)
    t.start()

    client = EnvelopeClient(port=adapter.port)
    assert client.connect(retries=10)
    client.send(EventEnvelope("CTRL_PING", {"x": 1}))
    client.send(EventEnvelope(EventType.MAP_INFO.value, {"map_id": "mines"}))
    # Un evenement interdit transite par le pont (couche transport) ; c'est le
    # moteur qui le bloquera cote FairPlay, pas le pont.
    client.send(EventEnvelope("ENEMY_RELOAD", {"seconds": 2}))
    time.sleep(0.3)
    client.close()
    t.join(timeout=3)

    types = [e.event_type for e in received]
    assert "MAP_INFO" in types
    assert "ENEMY_RELOAD" in types  # transmis, sera bloque en aval
    assert len(controls) == 1 and controls[0].event_type == "CTRL_PING"


def test_engine_driven_over_socket():
    engine = AdviceEngine()
    adapter = _start_server()

    def consume():
        for ev in adapter.events():
            engine.feed(ev)

    t = threading.Thread(target=consume, daemon=True)
    t.start()

    client = EnvelopeClient(port=adapter.port)
    assert client.connect(retries=10)

    for e in opening_events():
        client.send(EventEnvelope.from_raw_event(e))
    client.send(EventEnvelope("ENEMY_RELOAD", {"seconds": 2}))  # doit etre bloque
    client.send(EventEnvelope.from_raw_event(tick(10)))
    client.send(EventEnvelope(EventType.BATTLE_END.value, {"battle_id": "b1"}))
    time.sleep(0.4)
    client.close()
    t.join(timeout=3)

    # Le plan initial a ete calcule via le flux socket.
    shown = [e for e in engine.journal.entries if e.decision == "SHOWN"]
    assert any(s.advice and s.advice["rule_id"] == "plan.initial" for s in shown)
    # L'evenement interdit a bien ete bloque par le FairPlayFilter.
    assert engine.fairplay.report.blocked_count >= 1
