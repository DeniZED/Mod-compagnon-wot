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
    parser.add_argument("--tactical-kb", default=None,
                        help="Chemin du JSON de zones (build_tk). Memorise : les "
                             "conseils de placement issus des replays s'activent. "
                             "Passer \"\" (vide) pour desactiver.")
    parser.add_argument("--overlay", choices=["console", "tk", "none"], default=None,
                        help="Affichage des conseils : console, tk (overlay graphique "
                             "in-game), none. Memorise : par defaut, reprend le dernier "
                             "choix (console au premier lancement).")
    parser.add_argument("--overlay-anchor",
                        choices=["top_right", "top_left", "bottom_left", "bottom_right"],
                        default=None, help="Coin d'ancrage de l'overlay (evite la minimap).")
    parser.add_argument("--overlay-x", type=int, default=None,
                        help="Decalage horizontal de l'overlay en pixels (+ vers la droite).")
    parser.add_argument("--overlay-y", type=int, default=None,
                        help="Decalage vertical de l'overlay en pixels (+ vers le bas).")
    parser.add_argument("--no-click-through", action="store_true",
                        help="Rend l'overlay cliquable (desactive le click-through).")
    parser.add_argument("--overlay-debug", action="store_true",
                        help="Overlay OPAQUE (diagnostic) : sans transparence ni "
                             "click-through, pour verifier qu'il s'affiche par-dessus le jeu.")
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
    if args.tactical_kb is not None:
        settings.tactical_kb_path = args.tactical_kb or None
    if args.overlay is not None:
        settings.ui.overlay_kind = args.overlay
    overlay_kind = settings.ui.overlay_kind
    if args.overlay_anchor is not None:
        settings.ui.anchor = args.overlay_anchor
    if args.overlay_x is not None:
        settings.ui.offset_x = args.overlay_x
    if args.overlay_y is not None:
        settings.ui.offset_y = args.overlay_y
    if args.no_click_through:
        settings.ui.click_through = False
    save_settings(settings, config_path)

    runner = LiveRunner(
        settings=settings, host=args.host, port=args.port,
        db_path=args.db, use_color=not args.no_color, overlay=overlay_kind,
        config_path=config_path, overlay_debug=args.overlay_debug,
    )
    print(f"Config : {config_path}  (personnalite={settings.personality.value}, "
          f"intensite={settings.intensity}, objectif={settings.session_objective}, "
          f"overlay={overlay_kind})")
    if overlay_kind == "console":
        print("NB : overlay=console (pas d'affichage in-game). "
              "Ajoute --overlay tk pour l'overlay graphique dans le jeu.")
    kb = runner.app.engine.tactical_kb
    if settings.tactical_kb_path:
        print(f"Base tactique : {len(kb.clusters)} zones chargees "
              f"({settings.tactical_kb_path})")
    else:
        print("Base tactique : aucune (option --tactical-kb pour l'activer)")
    runner.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
