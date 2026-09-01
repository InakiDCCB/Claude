"""Re-test de TD9S (RUUT Cyclone / TD Sequential) bajo la metodologia nueva del usuario
(2026-08-28): hit ratio informativo, NO filtro; P&L/PF manda; desglose estacionalidad/regimen.

Config EXACTA de td_shadow.py (la que corrio como shadow real hasta ser ARCHIVADA 2026-08-20 tras
research exhaustivo, ver project_shadow_full_history_validation.md / project_gt_closelow_v2.md):
Setup 9 Perfeccionado (S9P) SHORT en bloques 5-min + filtro RSI14(5m) >= 60 + slippage $0.02
(SL=high+2xATR14, TP=close-3xATR14) -- confirmado NUNCA cruza PF=1.0 en ningun tratamiento previo
(td9s_full_treatment.py, td9s_full_matrix.py de 36 combos). Esta corrida no busca un combo nuevo
(eso ya se hizo exhaustivamente) -- aplica la lente nueva (seasonality/regimen) a la config LIVE
para consistencia con el resto del roster.

Reutiliza tools/td_backtest.py (rsi/ema/atr/td_signals) y la carga/simulacion de 10 anios de
tools/lab/td9s_full_matrix.py (load_bydate/build_5min_blocks/simulate_1min). El bucket de
regimen liq/vol se calcula sobre Day objects (tools/backtest.py) construidos desde las mismas
barras 1-min -- mismo criterio (mediana propia de la ventana) que el resto del roster.

Uso: python backtest_all_td9s.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest import Day, stats
from td_backtest import rsi as td_rsi, atr as td_atr, td_signals
from td9s_full_matrix import load_bydate, build_5min_blocks, simulate_1min
from _score_common import horizon_score, seasonality_breakdown, print_seasonality, wilson_lb

RSI_MIN = 60          # td_shadow.py RSI_MIN -- filtro exacto del shadow LIVE
SLIPPAGE = 0.02


def build_days_from_bydate(bydate):
    dates = sorted(bydate)
    days, prev = [], None
    for d in dates:
        bars = bydate[d]
        if len(bars) < 300:
            continue
        day = Day(d, bars, prev)
        days.append(day)
        prev = day
    return days


def fmt(s):
    if s is None or s["n"] == 0:
        return "n=0"
    wlb = wilson_lb(s["w"], s["n"])
    pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else " inf"
    return (f"n={s['n']:>5}  hit={s['hit']:5.1f}%(wlb {wlb*100:4.1f}%)  PF={pf_s:>5}  "
            f"pnl/sh={s['pnl']:>+9.2f}  mLL={s['mll']:>2}")


def main():
    print("Cargando barras 1-min 2016-2026...")
    bydate = load_bydate(range(2016, 2027))
    blocks = build_5min_blocks(bydate)
    r14 = td_rsi([b["c"] for b in blocks])
    a14 = td_atr(blocks)
    sigs = td_signals(blocks)
    print(f"{len(blocks)} bloques 5-min, {len(sigs)} señales TD crudas.\n")

    trades = []
    for s in sigs:
        if s["side"] != "short" or s["kind"] != "S9P":
            continue
        i = s["i"]
        if a14[i] is None or r14[i] is None or r14[i] < RSI_MIN:
            continue
        b = blocks[i]
        entry = b["c"]
        sl, tp = entry + 2 * a14[i], entry - 3 * a14[i]
        r = simulate_1min(bydate, b["d"], b["i1"], "short", entry, sl, tp, SLIPPAGE)
        if r is None:
            continue
        trades.append({"day": b["d"], "pnl": r})

    days = build_days_from_bydate(bydate)
    s_all = stats(trades)
    sc = horizon_score(s_all)
    print("=== TD9S (S9P short + RSI14>=60, slippage $0.02)  [ARCHIVADO 2026-08-20] ===")
    print(f"  {fmt(s_all)}   score={sc['total']:.1f}/100 [{sc['verdict']}] (score = 100% PF/riesgo, hit NO pondera)")
    seas = seasonality_breakdown(trades, days, stats)
    print_seasonality(seas)
    return {"TD9S": {"status": "ARCHIVADO 2026-08-20 (S9P short + RSI14>=60)",
                     "stats": s_all, "score": sc, "seasonality": seas}}


if __name__ == "__main__":
    main()
