"""Liquidity Wick Reversal (LWR) — calibracion grid + veredicto Horizon Score.

Rechazo intra-vela 1-min (mecha inferior/superior >= wick_thresh * range) -> fade
mean-reversion. LONG = mecha inferior (backtest.wick_reversal); SHORT = mecha
superior (backtest_short.wick_rejection_fade), shadow-only (shorts no son LIVE).

Grid: wick_thresh x tp_mode, base y +C4, sobre TODA la ventana cacheada en
tools/data/qqq_1min.json (regenerar con fetch_data.py si esta vieja). Reusa
horizon_score() de tools/lab/horizon_lab.py (generica sobre stats()) para el
veredicto DEPLOY/PAPER/KILLED por celda -- asi el filtro "Horizon Lab" corre
sobre esta hipotesis sin reescribir su parser NL (que no cubre wick ratio).

Uso: python calibrate_lwr.py [--since 2026-04-20]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lab"))   # horizon_lab.py vive en tools/lab

from backtest import stats, run_market, wick_reversal
from backtest_short import run_market_short, wick_rejection_fade
from analysis_30d import build_days
from horizon_lab import horizon_score

WICK_THRESHOLDS = (0.50, 0.55, 0.60, 0.65, 0.70)
TP_MODES = [("r", 0.5), ("r", 1.0), ("r", 1.5), ("vwap",)]


def _tp_label(tp):
    return f"tp={tp[1]}R" if tp[0] == "r" else "tp=VWAP"


def _row(label, s, sc):
    if s is None:
        return f"  {label:<26} n=0"
    pf = "  inf" if s["pf"] == float("inf") else f"{s['pf']:5.2f}"
    return (f"  {label:<26} n={s['n']:>3}  hit={s['hit']:>5.1f}%  pnl={s['pnl']:>+7.2f}/sh  "
            f"PF={pf}  mLL={s['mll']:>2}  score={sc['total']:>5.1f} [{sc['verdict']}]")


def run_grid(days, side_name, runner, factory):
    best = None
    print(f"\n=== {side_name} ===")
    for wt in WICK_THRESHOLDS:
        for tp in TP_MODES:
            t0 = runner(days, factory(tp, wick_thresh=wt)(), c4=False)
            t4 = runner(days, factory(tp, wick_thresh=wt)(), c4=True)
            s0, s4 = stats(t0), stats(t4)
            sc0, sc4 = horizon_score(s0), horizon_score(s4)
            label = f"wt={wt:.2f} {_tp_label(tp)}"
            print(_row(label + " base", s0, sc0))
            print(_row(label + " +C4", s4, sc4))
            for tag, s, sc in ((label + " base", s0, sc0), (label + " +C4", s4, sc4)):
                if best is None or sc["total"] > best[2]["total"]:
                    best = (tag, s, sc)
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="primera sesion YYYY-MM-DD (default: toda la cache)")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    all_days, _ = build_days()
    days = [d for d in all_days if a.since is None or d.date >= a.since]
    print("=" * 78)
    print(f"LWR calibration  ·  QQQ 1-min  ·  {days[0].date} -> {days[-1].date}  ({len(days)} sesiones)")
    print("=" * 78)

    best_long = run_grid(days, "LONG (mecha inferior, wick_reversal)", run_market, wick_reversal)
    best_short = run_grid(days, "SHORT (mecha superior, wick_rejection_fade, shadow-only)",
                          run_market_short, wick_rejection_fade)

    print("\n" + "=" * 78)
    for side, best in (("LONG", best_long), ("SHORT", best_short)):
        if best is None:
            print(f"{side}: sin celdas validas")
            continue
        tag, s, sc = best
        print(f"MEJOR {side}: {tag}  ->  Horizon Score {sc['total']}/100  ->  {sc['verdict']}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
