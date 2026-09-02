"""Outil CLI du backtester (§15) : rejoue les golden scenarios et affiche le
verdict + les métriques agrégées, sans lancer WoT.

Usage :
    python -m wot_companion.tools.backtest
    python -m wot_companion.tools.backtest --scenarios tests/golden_scenarios
"""
from __future__ import annotations

import argparse
from pathlib import Path

from ..backtest import compute_metrics, load_golden_dir, run_golden, run_timeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WoT Companion - backtester")
    parser.add_argument("--scenarios", default="tests/golden_scenarios",
                        help="Dossier de golden scenarios (*.json).")
    args = parser.parse_args(argv)

    scenarios = load_golden_dir(Path(args.scenarios))
    if not scenarios:
        print("Aucun scénario trouvé dans %s" % args.scenarios)
        return 1

    ok = 0
    print("== Golden scenarios ==")
    for sc in scenarios:
        res = run_golden(sc)
        flag = "OK  " if res.passed else "FAIL"
        ok += res.passed
        detail = res.got_action or ("silence" if res.silent else "?")
        print("  [%s] %-28s %s (%s)" % (flag, sc.name, detail, res.reason))
        # Métriques de la timeline du scénario (indicatif).
        m = compute_metrics(run_timeline(sc.timeline))
        if m.advice_count:
            print("        conseils=%d silence=%.0f%% intents=%s"
                  % (m.advice_count, m.silence_rate * 100, m.by_intent))

    print("\n%d/%d scénarios conformes." % (ok, len(scenarios)))
    return 0 if ok == len(scenarios) else 2


if __name__ == "__main__":
    raise SystemExit(main())
