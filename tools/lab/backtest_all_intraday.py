"""Re-test de TODOS los sistemas intradia (LIVE, shadow, descartados, retirados) contra los ~10.6
anios completos de 1-min QQQ (tools/data/qqq_1min/), bajo la metodologia nueva del usuario
(2026-08-28): el hit ratio NO filtra nada -- es solo un dato de validez impreso junto al resto.
Lo que decide es P&L/PF, y cada sistema se desglosa por estacionalidad (dia semana/mes) y
regimen (liq x vol) para ver si tiene edge en condiciones especificas aunque el agregado sea
plano. Ver feedback_hit_ratio_not_a_filter_research.md.

Reutiliza el motor y las factories EXACTAS de tools/backtest.py / tools/backtest_short.py /
tools/lab/smc_backtest.py / smc_confluence_backtest.py / smc_structure_backtest.py -- ningun
parametro se reinventa aqui, todos vienen 1:1 de la config LIVE/shadow/calibracion documentada
en memoria (project_systems_history.md, project_liquidity_wick_reversal.md,
project_shadow_full_history_validation.md, project_short_enablement.md).

Roster (12 sistemas, motor compartido Day/simulate):
  S1 RSI2 (LIVE), S2 FVG (LIVE), S3 VWAPPB (retirado v3.1.10), S4 SWP (LIVE),
  S5 GAPF (descartada 07-10), S6 SWP-short (retirado v3.1.10),
  LWR long (shadow), LWR short (nunca rescatado), OB (rechazada 07-16), OBNB (rechazada),
  SMC estructura BOS+CHoCH (cerrada), + mirrors nunca promovidos (RSI2-short, VWAPPB-short, GAPF-short).
TD9S (5-min, distinta granularidad) y la familia Golden Ticket diaria viven en scripts separados
(td9s_full_matrix.py ya la trato exhaustivamente; backtest_all_daily_gt.py corre GT).

Uso: python backtest_all_intraday.py [--json out.json]
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest import (Day, stats, run_market, run_fvg, rsi2_dip, vwap_pullback,
                      sweep_reclaim, gap_fill, wick_reversal)
from backtest_short import (run_market_short, rsi2_pop, vwap_rejection, sweep_rejection,
                            gap_fade, wick_rejection_fade)
from smc_backtest import run_ob
from smc_confluence_backtest import run_ob_conf
from smc_structure_backtest import run_structure
from _score_common import horizon_score, seasonality_breakdown, print_seasonality, wilson_lb

DATA_DIR = Path(__file__).parent.parent / "data" / "qqq_1min"


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
    days, prev = [], None
    for d in dates:
        bars = bydate[d]
        if len(bars) < 300:                  # descarta medios dias / feriados con data incompleta
            continue
        day = Day(d, bars, prev)
        days.append(day)
        prev = day
    return days


# ---- Roster: (label, status, runner) -- runner(days) -> trades ------------------------------
# c4=True en todos los que tienen C4 vigente en produccion (todos los intradia, CLAUDE.md).
# OB/OBNB/estructura nunca corrieron con C4 en produccion (nunca fueron LIVE) -- se reportan sin.

ROSTER = [
    ("S1 RSI2", "LIVE",
     lambda days: run_market(days, rsi2_dip(0.5, thresh=15, sl_mult=1.0, time_stop=15)(), c4=True)),
    ("S2 FVG", "LIVE",
     lambda days: run_fvg(days, None, c4=True)),
    ("S3 VWAPPB", "retirado v3.1.10",
     lambda days: run_market(days, vwap_pullback(45, 65, tp=("r", 1.0))(), c4=True)),
    ("S4 SWP", "LIVE (override usuario pese a research negativo)",
     lambda days: run_market(days, sweep_reclaim(("r", 0.5))(), c4=True)),
    ("S5 GAPF", "descartada 2026-07-10",
     lambda days: run_market(days, gap_fill()(), c4=True)),
    ("S6 SWP-short", "retirado v3.1.10",
     lambda days: run_market_short(days, sweep_rejection(("r", 0.5))(), c4=True)),
    ("LWR long", "shadow (usuario mantuvo pese a research negativo)",
     lambda days: run_market(days, wick_reversal(("r", 0.5), wick_thresh=0.60, min_rvol=3.0)(), c4=True)),
    ("LWR short", "nunca rescatado (KILLED en calibracion)",
     lambda days: run_market_short(days, wick_rejection_fade(("r", 0.5), wick_thresh=0.60, min_rvol=3.0)(), c4=True)),
    ("OB", "rechazada 2026-07-16",
     lambda days: run_ob(days, n=2, tp_r=2.0, c4=False)),
    ("OBNB", "rechazada (filtro sin-BOS no rescato)",
     lambda days: [t for t in run_ob_conf(days, n=2, tp_r=2.0) if t["kind"] != "bos"]),
    ("SMC estructura BOS+CHoCH", "cerrada (stream SMC, E.1)",
     lambda days: run_structure(days, n=2, tp_r=2.0, kinds=("bos", "choch"), c4=False)),
    ("RSI2-short (mirror)", "nunca validado (pieza aislada de short_enablement)",
     lambda days: run_market_short(days, rsi2_pop(0.5, thresh=85, sl_mult=1.0, time_stop=15)(), c4=True)),
    ("VWAPPB-short (mirror)", "nunca validado (espejo naive, PF 0.78 en 06-16)",
     lambda days: run_market_short(days, vwap_rejection(45, 65, tp=("r", 1.0))(), c4=True)),
    ("GAPF-short (mirror)", "nunca corrido en vivo",
     lambda days: run_market_short(days, gap_fade()(), c4=True)),
]


def fmt(s):
    if s is None or s["n"] == 0:
        return "n=0"
    wlb = wilson_lb(s["w"], s["n"])
    pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else " inf"
    return (f"n={s['n']:>5}  hit={s['hit']:5.1f}%(wlb {wlb*100:4.1f}%)  PF={pf_s:>5}  "
            f"pnl/sh={s['pnl']:>+9.2f}  mLL={s['mll']:>2}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="ruta para volcar resultados completos en JSON")
    ap.add_argument("--since", default=None, help="filtra dias >= esta fecha antes de correr (debug)")
    a = ap.parse_args()

    print("Cargando barras 1-min 2016-2026 y construyendo Day objects...")
    days = load_days(range(2016, 2027))
    if a.since:
        days = [d for d in days if d.date >= a.since]
    print(f"{len(days)} dias de sesion cargados ({days[0].date} -> {days[-1].date}).\n")

    out = {}
    for name, status, runner in ROSTER:
        trades = runner(days)
        s = stats(trades)
        sc = horizon_score(s)
        print(f"=== {name}  [{status}] ===")
        print(f"  {fmt(s)}   score={sc['total']:.1f}/100 [{sc['verdict']}] (score = 100% PF/riesgo, hit NO pondera)")
        seas = seasonality_breakdown(trades, days, stats)
        print_seasonality(seas)
        print()
        out[name] = {"status": status, "stats": s, "score": sc, "seasonality": seas}

    if a.json:
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, default=str, indent=2))
        print(f"[guardado] {a.json}")


if __name__ == "__main__":
    main()
