"""Prueba standalone de los indicadores NUEVOS (MACD, Bollinger, Stochastic, +ADX como filtro)
contra los ~10.6 años completos de 1-min QQQ -- ampliacion del universo pedida por el usuario
2026-08-28 ("mas indicadores para agregar a estas pruebas"). Mismo motor/metodologia que
backtest_all_intraday.py (hit ratio informativo, score = 100% PF, seasonality/regimen).

Señales nuevas (definidas en indicators_ext.py, jamas probadas antes en este proyecto):
  MACD(12,26,9) cruce de histograma  · Bollinger(20,2) reversion a la banda ·
  Stochastic(14,3,3) reversal desde sobreventa/sobrecompra · + 2 variantes con filtro ADX(14)
  (RSI2 dip solo en no-tendencia ADX<20; MACD cross solo en tendencia fuerte ADX>25).

Uso: python backtest_new_indicators.py [--json out.json]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest import stats, run_market, rsi2_dip
from backtest_short import run_market_short
from backtest_all_intraday import load_days
from indicators_ext import macd_cross, bb_reversion, stoch_reversal, with_adx_filter, attach_ext_indicators
from _score_common import horizon_score, seasonality_breakdown, print_seasonality, wilson_lb

ROSTER = [
    ("MACD cross long", lambda days: run_market(days, macd_cross("long", ("r", 1.5))(), c4=True)),
    ("MACD cross short", lambda days: run_market_short(days, macd_cross("short", ("r", 1.5))(), c4=True)),
    ("BB(20,2) reversion long", lambda days: run_market(days, bb_reversion("long", ("r", 1.0))(), c4=True)),
    ("BB(20,2) reversion short", lambda days: run_market_short(days, bb_reversion("short", ("r", 1.0))(), c4=True)),
    ("Stoch(14,3,3) reversal long", lambda days: run_market(days, stoch_reversal("long", ("r", 1.0))(), c4=True)),
    ("Stoch(14,3,3) reversal short", lambda days: run_market_short(days, stoch_reversal("short", ("r", 1.0))(), c4=True)),
    ("RSI2 dip + ADX<20 filter", lambda days: run_market(
        days, with_adx_filter(rsi2_dip(0.5, thresh=15, sl_mult=1.0, time_stop=15), max_adx=20)(), c4=True)),
    ("MACD cross + ADX>25 filter", lambda days: run_market(
        days, with_adx_filter(macd_cross("long", ("r", 1.5)), min_adx=25)(), c4=True)),
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
    ap.add_argument("--json")
    a = ap.parse_args()

    print("Cargando barras 1-min 2016-2026...")
    days = load_days(range(2016, 2027))
    print(f"{len(days)} dias cargados. Precomputando MACD/BB/Stoch/ADX por sesion...")
    attach_ext_indicators(days)
    print("Listo.\n")

    out = {}
    for name, runner in ROSTER:
        trades = runner(days)
        s = stats(trades)
        sc = horizon_score(s)
        print(f"=== {name} ===")
        print(f"  {fmt(s)}   score={sc['total']:.1f}/100 [{sc['verdict']}]")
        seas = seasonality_breakdown(trades, days, stats)
        print_seasonality(seas)
        print()
        out[name] = {"stats": s, "score": sc, "seasonality": seas,
                     "trades": [{"day": t["day"], "ei": t["ei"], "pnl": t["pnl"]} for t in trades]}

    if a.json:
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, default=str, indent=2))
        print(f"[guardado] {a.json}")
    return out


if __name__ == "__main__":
    main()
