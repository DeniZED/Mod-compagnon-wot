"""Lanceur LIVE du compagnon (fenetre console).

A executer sur le PC de jeu, en parallele de World of Tanks.

Usage :
    python -m wot_companion.tools.live
    python -m wot_companion.tools.live --personality commandant --port 47800
    python -m wot_companion.tools.live --db C:/Users/moi/wotc.sqlite --objective survie
"""
from __future__ import annotations

import argparse
import logging

from ..game_adapter.ipc import DEFAULT_HOST, DEFAULT_PORT
from ..live.runner import LiveRunner
from ..settings import Personality, Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WoT Companion - lanceur live")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--personality", choices=[p.value for p in Personality],
                        default="coach")
    parser.add_argument("--intensity", type=float, default=1.0)
    parser.add_argument("--objective", default=None,
                        help="survie / degats / assistance / discipline_early")
    parser.add_argument("--db", default="wot_companion.sqlite",
                        help="Chemin du fichier historique SQLite persistant.")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    settings = Settings(
        personality=Personality(args.personality),
        intensity=args.intensity,
        session_objective=args.objective,
    )
    runner = LiveRunner(
        settings=settings, host=args.host, port=args.port,
        db_path=args.db, use_color=not args.no_color,
    )
    runner.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
