"""Backtestea los 5 sistemas LIVE (S1 RSI2, S2 FVG, S3 VWAPPB, S4 SWP, S6 SWP-short) contra los
10 años completos de 1-min QQQ (tools/data/qqq_1min/, ver tools/fetch_1min_full.py) en vez de los
~10 días de junio-2026 usados para la calibración original. Reutiliza el motor de fill/exit y las
factories EXACTAS de tools/backtest.py / tools/backtest_short.py -- parámetros verificados 1:1
contra workflows/cycle_prompt.md STEP 6/7-fill:

  S1 RSI2   = rsi2_dip(tp_mode=0.5, thresh=15, sl_mult=1.0, time_stop=15)
  S2 FVG    = run_fvg(days, None, max_fills=None)          -- tp=2R hardcoded en simulate()
  S3 VWAPPB = vwap_pullback(45, 65, tp=("r", 1.0))          -- sl=2xATR1m, tp=1R=2xATR1m
  S4 SWP    = sweep_reclaim(("r", 0.5))
  S6 SWP-short = sweep_rejection(("r", 0.5))                -- de backtest_short.py

Reporta, para cada sistema: pool 2016-2026 Y desglose año-por-año (lección de la sesión de
research de hoy: nunca confiar en el agregado solo) -- n, hit%, Wilson LB 95%, PF, pnl/share
total, mean pnl/share, max pérdidas consecutivas (proxy de drawdown).

Uso: python backtest_live_full_history.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))  # tools/
from backtest import Day, stats, run_fvg, run_market, rsi2_dip, vwap_pullback, sweep_reclaim
from backtest_short import run_market_short, run_fvg_short, sweep_rejection

DATA_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"


def wilson_lb(wins, n, z=1.96):
    if n == 0:
        return None
    p = wins / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (center - margin) / denom


def load_days(years):
    bydate = {}
    for year in years:
        path = DATA_DIR / f"{year}.csv"
        if not path.exists():
            continue
        with path.open() as f:
            for row in csv.DictReader(f):
                date = row["t"][:10]
                bydate.setdefault(date, []).append(
                    {"t": row["t"], "o": float(row["o"]), "h": float(row["h"]),
                     "l": float(row["l"]), "c": float(row["c"]), "v": float(row["v"])})
    dates = sorted(bydate)
    days = []
    prev = None
    for d in dates:
        bars = bydate[d]
        if len(bars) < 300:   # descarta medios días / feriados con data incompleta
            continue
        day = Day(d, bars, prev)
        days.append(day)
        prev = day
    return days


def fmt_stats(s):
    if s is None or s["n"] == 0:
        return "n=0"
    wlb = wilson_lb(s["w"], s["n"])
    pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "inf"
    return (f"n={s['n']:>4} hit={s['hit']:5.1f}% wilsonLB={wlb*100:5.1f}% pf={pf_s:>5} "
            f"pnl/sh={s['pnl']:+8.2f} mean={s['mean']:+.4f} mLL={s['mll']}")


def report(name, trades):
    print(f"\n=== {name} ===")
    s_all = stats(trades)
    print(f"  POOL 2016-2026: {fmt_stats(s_all)}")
    by_year = {}
    for t in trades:
        by_year.setdefault(t["day"][:4], []).append(t)
    for year in sorted(by_year):
        s_y = stats(by_year[year])
        print(f"  {year}: {fmt_stats(s_y)}")


def main():
    years = range(2016, 2027)
    print("Cargando barras y construyendo Day objects (2016-2026)...")
    days = load_days(years)
    print(f"{len(days)} días de sesión cargados.")

    print("\nCorriendo S1 RSI2 (rsi2_dip 0.5/th15/sl1.0/ts15)...")
    s1 = run_market(days, rsi2_dip(0.5, thresh=15, sl_mult=1.0, time_stop=15)(), c4=False)
    report("S1 RSI2", s1)

    print("\nCorriendo S2 FVG (sin tope de fills)...")
    s2 = run_fvg(days, None, c4=False)
    report("S2 FVG", s2)

    print("\nCorriendo S3 VWAPPB (45-65, tp=1R)...")
    s3 = run_market(days, vwap_pullback(45, 65, tp=("r", 1.0))(), c4=False)
    report("S3 VWAPPB", s3)

    print("\nCorriendo S4 SWP (0.5R)...")
    s4 = run_market(days, sweep_reclaim(("r", 0.5))(), c4=False)
    report("S4 SWP", s4)

    print("\nCorriendo S6 SWP-short (0.5R)...")
    s6 = run_market_short(days, sweep_rejection(("r", 0.5))(), c4=False)
    report("S6 SWP-short", s6)


if __name__ == "__main__":
    main()
