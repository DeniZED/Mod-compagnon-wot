"""Injecteur de test : envoie des evenements au compagnon LIVE via le pont IPC.

Permet de valider TOUT le chainage (pont -> moteur -> affichage -> historique)
sur le PC de jeu, AVANT meme d'installer le mod WoT. C'est la preuve que le
compagnon fonctionne en conditions reelles cote logiciel.

Usage (dans une 2e fenetre, pendant que `wot-companion-live` tourne) :
    python -m wot_companion.tools.inject --scenarios
    python -m wot_companion.tools.inject --scenarios --speed 10
    python -m wot_companion.tools.inject --scenarios --realtime
    python -m wot_companion.tools.inject --silence      # bascule le mode silence
"""
from __future__ import annotations

import argparse
import sys
import time

from ..game_adapter.base import EventEnvelope
from ..game_adapter.ipc import DEFAULT_HOST, DEFAULT_PORT, EnvelopeClient
from ..game_adapter.simulator import SimulatedAdapter, make_default_scenarios


def _replay_scenarios(client: EnvelopeClient, speed: float, realtime: bool) -> int:
    adapter = SimulatedAdapter(make_default_scenarios())
    sent = 0
    prev_ts: int | None = None
    for evt in adapter.events():
        # Pacing : respecte l'ecart temporel entre evenements.
        if prev_ts is not None:
            delta_ms = max(0, evt.timestamp_ms - prev_ts)
            if realtime:
                time.sleep(delta_ms / 1000.0)
            elif speed > 0:
                time.sleep(delta_ms / 1000.0 / speed)
        prev_ts = evt.timestamp_ms
        env = EventEnvelope.from_raw_event(evt)
        if not client.send(env):
            print("Connexion perdue avec le compagnon.", file=sys.stderr)
            return sent
        sent += 1
        print(f"-> {env.event_type} {env.payload}")
    return sent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Injecteur d'evenements WoT Companion")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--scenarios", action="store_true",
                        help="Rejoue les batailles simulees de reference.")
    parser.add_argument("--speed", type=float, default=20.0,
                        help="Acceleration du temps simule (defaut 20x).")
    parser.add_argument("--realtime", action="store_true",
                        help="Rejoue au rythme reel (ignore --speed).")
    parser.add_argument("--silence", action="store_true",
                        help="Envoie un basculement du mode silence (CTRL_SILENCE_TOGGLE).")
    parser.add_argument("--ping", action="store_true")
    args = parser.parse_args(argv)

    client = EnvelopeClient(host=args.host, port=args.port)
    if not client.connect(retries=3):
        print(f"Impossible de joindre le compagnon sur {args.host}:{args.port}. "
              "Lance d'abord : python -m wot_companion.tools.live", file=sys.stderr)
        return 1

    try:
        if args.silence:
            client.send(EventEnvelope(event_type="CTRL_SILENCE_TOGGLE"))
            print("Basculement du mode silence envoye.")
            return 0
        if args.ping:
            client.send(EventEnvelope(event_type="CTRL_PING", payload={"from": "inject"}))
            print("Ping envoye.")
            return 0
        if args.scenarios:
            n = _replay_scenarios(client, args.speed, args.realtime)
            print(f"\n{n} evenements envoyes.")
            return 0
        parser.print_help()
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
