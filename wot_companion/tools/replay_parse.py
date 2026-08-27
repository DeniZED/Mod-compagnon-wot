"""Outil : lit un ou plusieurs .wotreplay et affiche la verite terrain.

Hors-ligne, local. Sert a valider les donnees live (degats/assist) et a
alimenter la Tactical Knowledge Base (Phase B) : resultats par vehicule +
trajectoires decodees, avec selection des meilleurs joueurs de la partie.

Usage :
    python -m wot_companion.tools.replay_parse partie.wotreplay [autre.wotreplay ...]
    python -m wot_companion.tools.replay_parse --full partie.wotreplay   # + trajectoires
    python -m wot_companion.tools.replay_parse --json parties/*.wotreplay
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from ..replays import parse_replay
from ..replays.parse import ReplayParseError, parse_replay_full


def _print_summary(s) -> None:
    surv = "survie" if s.survived else "mort" if s.survived is not None else "?"
    print("  %s (%s) — %s" % (s.map_label or s.map_id, s.vehicle, s.result or "?"))
    print("  degats=%d  assist=%d (radio %d / track %d)  kills=%d  spotted=%d  %s  vie=%ss"
          % (s.damage, s.assist_total, s.assist_radio, s.assist_track,
             s.kills, s.spotted, surv, s.life_time_s))


def _print_full(ds) -> None:
    _print_summary(ds.summary)
    print("  vehicules=%d  trajectoires=%d  (equipe gagnante=%s)"
          % (len(ds.vehicles), len(ds.trajectories), ds.summary_winner_team()))
    print("  -- meilleurs joueurs de l'equipe gagnante (impact combat) --")
    for v in ds.best_performers(5, winners_only=True):
        star = " *" if v.is_player else ""
        print("     %-16s %-32s dmg=%-5d assist=%-5d kills=%d  pts_traj=%d%s"
              % ((v.name or "?")[:16], (v.vehicle_type or "?")[:32], v.damage,
                 v.assist_total, v.kills, len(ds.trajectory_of(v.vehicle_id)), star))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lecture de replays WoT (.wotreplay)")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--full", action="store_true",
                        help="Decode aussi les trajectoires + meilleurs joueurs.")
    parser.add_argument("--json", action="store_true", help="Sortie JSON brute.")
    args = parser.parse_args(argv)

    payload = []
    for path in args.paths:
        name = path.split("/")[-1]
        try:
            if args.full or args.json:
                ds = parse_replay_full(path)
            else:
                ds = None
                s = parse_replay(path)
        except ReplayParseError as exc:
            print("! %s : %s" % (name, exc))
            continue

        if args.json:
            payload.append({
                "path": name,
                "summary": asdict(ds.summary),
                "vehicles": [asdict(v) for v in ds.vehicles.values()],
                "trajectory_points": {str(k): len(v) for k, v in ds.trajectories.items()},
            })
            continue

        print("\n%s" % name)
        if args.full:
            _print_full(ds)
        else:
            _print_summary(s)
            if s.binary_bytes:
                print("  flux positions : %d Ko (option --full pour les trajectoires)"
                      % (s.binary_bytes // 1024))

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
