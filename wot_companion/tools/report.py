"""Rapport de session / historique (GAR-002, GAR-003, section 18).

Transforme l'historique local (SQLite) en synthese exploitable multi-batailles :
tendances globales, par vehicule et par rôle, profil de coaching, axe prioritaire.
Egalement : gestion des donnees (reset, export diagnostic non sensible).

Usage :
    python -m wot_companion.tools.report --db wot_companion.sqlite
    python -m wot_companion.tools.report --db ... --vehicle j20_type_2605
    python -m wot_companion.tools.report --db ... --export diag.json
    python -m wot_companion.tools.report --db ... --reset
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import APP_VERSION
from ..profile.store import HistoryStore
from ..profile.trends import (
    TrendAnalyzer, aggregate_records, build_player_profile, group_records,
)


def _fmt_agg(a: dict) -> str:
    if a.get("sample_size", 0) == 0:
        return "aucune bataille"
    parts = [
        f"{a['sample_size']} batailles",
        f"DPG {a['avg_damage']}",
        f"assist {a['avg_assist']}",
        f"survie {int(a['survival_rate'] * 100)}%",
    ]
    if a.get("avg_kills"):
        parts.append(f"kills {a['avg_kills']}")
    line = " · ".join(parts)
    if a.get("low_sample"):
        line += "  (echantillon faible)"
    return line


def build_report(store: HistoryStore, vehicle: str | None = None) -> list[str]:
    out: list[str] = []
    total = store.count_battles()
    out.append(f"WoT Companion - rapport de session (v{APP_VERSION})")
    out.append(f"Historique : {store.db_path}  |  {total} batailles enregistrees")
    if total == 0:
        out.append("\nAucune bataille pour l'instant. Joue quelques parties, "
                   "compagnon lance, puis relance ce rapport.")
        return out

    analyzer = TrendAnalyzer(store)

    out.append("\n--- Tendances recentes ---")
    for window in (5, 10, 20):
        recs = store.recent_battles(window, vehicle)
        if recs:
            out.append(f"  {window} dernieres : {_fmt_agg(aggregate_records(recs))}")

    all_recs = store.recent_battles(limit=100000)

    out.append("\n--- Par vehicule ---")
    for vid, recs in sorted(group_records(all_recs, "vehicle_id").items(),
                            key=lambda kv: -len(kv[1])):
        out.append(f"  {vid:<20} {_fmt_agg(aggregate_records(recs))}")

    out.append("\n--- Par rôle ---")
    for role, recs in sorted(group_records(all_recs, "vehicle_role").items(),
                             key=lambda kv: -len(kv[1])):
        out.append(f"  {role:<16} {_fmt_agg(aggregate_records(recs))}")

    out.append("\n--- Profil de coaching ---")
    profile = build_player_profile(store, window=50)
    out.append(f"  Echantillon {profile['sample_size']} · confiance {profile['confidence']}")
    out.append(f"  Preservation HP {profile['hp_preservation']} · "
               f"agressivite early {profile['aggression_early']} · "
               f"survie {profile['survival']}")

    # Axe prioritaire (GAR-001/003).
    trends = analyzer.session_trends(window=20, vehicle_id=vehicle)
    out.append("\n--- Axe prioritaire ---")
    for line in analyzer.summary_lines(trends):
        out.append("  " + line)

    out.append("\nRappel : ces indicateurs sont des reperes de coaching, pas des "
               "jugements ; un faible echantillon doit etre confirme.")
    return out


def export_diagnostic(store: HistoryStore, path: str | Path) -> None:
    """Export diagnostic NON sensible (agregats + versions), sans logs ni tokens."""
    all_recs = store.recent_battles(limit=100000)
    diag = {
        "app_version": APP_VERSION,
        "total_battles": store.count_battles(),
        "global": aggregate_records(all_recs),
        "by_role": {r: aggregate_records(recs)
                    for r, recs in group_records(all_recs, "vehicle_role").items()},
        "player_profile": build_player_profile(store, window=50),
    }
    Path(path).write_text(json.dumps(diag, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rapport de session WoT Companion")
    parser.add_argument("--db", default="wot_companion.sqlite")
    parser.add_argument("--vehicle", default=None, help="Filtrer sur un vehicle_id.")
    parser.add_argument("--export", metavar="PATH",
                        help="Exporte un diagnostic non sensible (JSON) et quitte.")
    parser.add_argument("--reset", action="store_true",
                        help="Supprime TOUTES les donnees locales (section 8.2).")
    args = parser.parse_args(argv)

    store = HistoryStore(args.db)
    try:
        if args.reset:
            confirm = input("Supprimer definitivement tout l'historique local ? [oui/non] ")
            if confirm.strip().lower() in ("oui", "o", "yes", "y"):
                store.delete_all()
                print("Donnees supprimees.")
            else:
                print("Annule.")
            return 0
        if args.export:
            export_diagnostic(store, args.export)
            print(f"Diagnostic exporte -> {args.export}")
            return 0
        for line in build_report(store, vehicle=args.vehicle):
            print(line)
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
