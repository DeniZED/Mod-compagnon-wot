"""Lanceur LIVE du compagnon (fenetre console).

A executer sur le PC de jeu, en parallele de World of Tanks.

Les preferences (personnalite, intensite, objectif...) sont PERSISTANTES : elles
sont chargees depuis un fichier de config et re-sauvegardees a chaque lancement.
Les options de ligne de commande ont priorite et sont memorisees.

Usage :
    python -m wot_companion.tools.live
    python -m wot_companion.tools.live --personality commandant --intensity 1.3
    python -m wot_companion.tools.live --objective survie
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..config import DEFAULT_CONFIG_NAME, load_settings, save_settings
from ..game_adapter.ipc import DEFAULT_HOST, DEFAULT_PORT
from ..live.runner import LiveRunner
from ..settings import Personality


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WoT Companion - lanceur live")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    # Defauts None => on ne surcharge la config que si l'option est fournie.
    parser.add_argument("--personality", choices=[p.value for p in Personality],
                        default=None)
    parser.add_argument("--intensity", type=float, default=None)
    parser.add_argument("--objective", default=None,
                        help="survie / degats / assistance / discipline_early")
    parser.add_argument("--db", default="wot_companion.sqlite",
                        help="Chemin du fichier historique SQLite persistant.")
    parser.add_argument("--config", default=None,
                        help="Chemin du fichier de config (defaut: a cote de la DB).")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    config_path = Path(args.config) if args.config else \
        Path(args.db).resolve().parent / DEFAULT_CONFIG_NAME

    # Charge les preferences persistees, puis applique les surcharges CLI.
    settings = load_settings(config_path)
    if args.personality is not None:
        settings.personality = Personality(args.personality)
    if args.intensity is not None:
        settings.intensity = args.intensity
    if args.objective is not None:
        settings.session_objective = args.objective or None
    save_settings(settings, config_path)

    runner = LiveRunner(
        settings=settings, host=args.host, port=args.port,
        db_path=args.db, use_color=not args.no_color,
    )
    print(f"Config : {config_path}  (personnalite={settings.personality.value}, "
          f"intensite={settings.intensity}, objectif={settings.session_objective})")
    runner.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
