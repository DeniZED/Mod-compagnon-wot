"""Demo bout-en-bout : joue des batailles simulees a travers le moteur complet.

Usage :
    python -m wot_companion.tools.run_simulation
    python -m wot_companion.tools.run_simulation --personality commandant --intensity 1.3
    python -m wot_companion.tools.run_simulation --audit --journal out.jsonl
"""
from __future__ import annotations

import argparse
import logging

from ..app import CompanionApp
from ..game_adapter.simulator import SimulatedAdapter, make_default_scenarios
from ..profile.store import HistoryStore
from ..settings import Personality, Settings
from ..ui.overlay import ConsoleOverlay


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulation WoT Companion")
    parser.add_argument("--personality", choices=[p.value for p in Personality],
                        default="coach")
    parser.add_argument("--intensity", type=float, default=1.0)
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--audit", action="store_true",
                        help="Affiche le rapport d'audit Fair Play a la fin.")
    parser.add_argument("--journal", metavar="PATH",
                        help="Exporte le journal des conseils (JSON Lines).")
    parser.add_argument("--objective", default=None,
                        help="Objectif de session (survie/degats/assistance/discipline_early).")
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
    overlay = ConsoleOverlay(use_color=not args.no_color)
    store = HistoryStore(":memory:")
    app = CompanionApp(settings=settings, store=store, overlay=overlay)

    adapter = SimulatedAdapter(make_default_scenarios())
    print(f"== Simulation WoT Companion (personnalite={args.personality}, "
          f"intensite={args.intensity}) ==\n")
    app.run(adapter)

    print(f"Batailles enregistrees : {store.count_battles()}")

    if args.journal:
        app.engine.journal.export_jsonl(args.journal)
        print(f"Journal exporte -> {args.journal}")

    if args.audit:
        report = app.engine.fairplay.report.as_dict()
        print("\n--- Rapport d'audit Fair Play ---")
        print(f"Evenements autorises : {report['allowed_count']}")
        print(f"Evenements bloques   : {report['blocked_count']}")
        print("Champs consommes par fonction :")
        for etype, fields in report["consumed_fields"].items():
            print(f"  {etype}: {', '.join(fields)}")
        if report["violations"]:
            print("Violations :")
            for v in report["violations"]:
                print(f"  [{v['kind']}] {v['detail']}")

    app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
