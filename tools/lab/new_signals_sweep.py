"""Prueba de señales NUEVAS nunca incluidas en el roster (2026-10-05).
Contexto: rsi2_v3 llego a established (n=52) con score=14 < KILL<45. El usuario quiere
encontrar indicadores que puedan llegar a established con score>=45.

Señales nuevas (ningun overlap con las 20+ del roster anterior ni MACD/BB/Stoch/ADX/crossovers):
  1. IBS(5m) < 0.2 long  -- 5-min Internal Bar Strength (probado en BTC con PF=1.34 diario)
  2. IBS(5m) > 0.8 short -- espejo short
  3. ORB breakout long   -- precio rompe ORB_high despues de 10:00
  4. ORB breakout short  -- precio rompe ORB_low
  5. ORB fade long       -- precio perfora ORB_low y reclaima -> long
  6. ORB fade short      -- precio perfora ORB_high y reclaima -> short
  7. PDL reclaim long    -- precio perfora PDL (prev-day low) y reclaima -> long
  8. RSI2(5m) < 5        -- RSI2 mas selectivo que el live (threshold 5 vs 15)
  9. RSI2(5m) < 10       -- intermedio

Metodologia: misma que backtest_all_intraday.py (score = 100% PF, hit=informativo,
seasonality breakdown, horizon_score DEPLOY>=65/PAPER>=45/KILLED<45).
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest import Day, stats, run_market
from backtest_short import run_market_short
from backtest_all_intraday import load_days
from _score_common import horizon_score, wilson_lb

ENTRY_MIN = 30   # 10:00 ET
ENTRY_MAX = 375  # 15:45 ET


# ─────────────────────────── helpers ────────────────────────────────────────

def _ibs(day, k):
    """Internal Bar Strength for 5-min block k. Returns None if range==0."""
    hi, lo, cl = day.f_h[k], day.f_l[k], day.f_c[k]
    return (cl - lo) / (hi - lo) if hi != lo else None


def _f_atr(day, k):
    """5-min ATR for block k (from day.f_atr)."""
    if k < len(day.f_atr) and day.f_atr[k] is not None:
        return day.f_atr[k]
    return None


# ─────────────────────────── señales ────────────────────────────────────────

def ibs5_long(sl_mult=1.0, tp_r=2.0, max_ibs=0.2):
    """IBS(5m) < max_ibs -> long."""
    def _sig(day, i):
        if i % 5 != 4 or i < 34:   # sealed 5-min block, after 10:04 ET
            return None
        k = i // 5
        if k >= len(day.f_h):
            return None
        ibs = _ibs(day, k)
        if ibs is None or ibs >= max_ibs:
            return None
        atr = _f_atr(day, k)
        if atr is None or atr <= 0:
            return None
        sl = day.f_l[k] - sl_mult * atr
        return {"sl_abs": sl, "tp": ("r", tp_r)}
    return _sig


def ibs5_short(sl_mult=1.0, tp_r=2.0, min_ibs=0.8):
    """IBS(5m) > min_ibs -> short."""
    def _sig(day, i):
        if i % 5 != 4 or i < 34:
            return None
        k = i // 5
        if k >= len(day.f_h):
            return None
        ibs = _ibs(day, k)
        if ibs is None or ibs <= min_ibs:
            return None
        atr = _f_atr(day, k)
        if atr is None or atr <= 0:
            return None
        # para run_market_short, el signal debe indicar entry_short
        # usamos sl_abs como el stop arriba del entry (high + mult*atr)
        sl = day.f_h[k] + sl_mult * atr
        return {"sl_abs": sl, "tp": ("r", tp_r)}
    return _sig


def orb_breakout_long(sl_pct=0.5, tp_r=2.0):
    """Primera vez que un 1-min bar cierra > or_high despues de 10:00 -> long."""
    def _sig(day, i):
        if i < ENTRY_MIN or day.or_high is None:
            return None
        if day.c[i] <= day.or_high:
            return None
        # solo la primera rotura
        if any(day.c[j] > day.or_high for j in range(ENTRY_MIN, i)):
            return None
        risk = max(day.c[i] - day.or_low, 0.10)
        sl = day.c[i] - sl_pct * risk
        return {"sl_abs": sl, "tp": ("r", tp_r)}
    return _sig


def orb_break_short(sl_pct=0.5, tp_r=2.0):
    """Primera vez que un 1-min bar cierra < or_low despues de 10:00 -> short."""
    def _sig(day, i):
        if i < ENTRY_MIN or day.or_low is None:
            return None
        if day.c[i] >= day.or_low:
            return None
        if any(day.c[j] < day.or_low for j in range(ENTRY_MIN, i)):
            return None
        risk = max(day.or_high - day.c[i], 0.10)
        sl = day.c[i] + sl_pct * risk
        return {"sl_abs": sl, "tp": ("r", tp_r)}
    return _sig


def orb_fade_long(atr_mult=0.5, tp_r=2.0):
    """Precio perfora ORB_low (bar cierra < or_low) y luego reclaima (bar cierra > or_low) -> long."""
    def _sig(day, i):
        if i < ENTRY_MIN + 1 or day.or_low is None:
            return None
        # requiere: barra anterior cerró < or_low, esta barra cierra > or_low
        if day.c[i - 1] >= day.or_low or day.c[i] <= day.or_low:
            return None
        atr = day.atr[i]
        if atr is None or atr <= 0:
            return None
        sl = min(day.l[i - 1], day.l[i]) - atr_mult * atr
        return {"sl_abs": sl, "tp": ("r", tp_r)}
    return _sig


def orb_fade_short(atr_mult=0.5, tp_r=2.0):
    """Precio perfora ORB_high y reclaima por debajo -> short."""
    def _sig(day, i):
        if i < ENTRY_MIN + 1 or day.or_high is None:
            return None
        if day.c[i - 1] <= day.or_high or day.c[i] >= day.or_high:
            return None
        atr = day.atr[i]
        if atr is None or atr <= 0:
            return None
        sl = max(day.h[i - 1], day.h[i]) + atr_mult * atr
        return {"sl_abs": sl, "tp": ("r", tp_r)}
    return _sig


def pdl_reclaim_long(atr_mult=0.5, tp_r=2.0):
    """Precio perfora PDL (prev-day low) y reclaima -> long."""
    def _sig(day, i):
        if i < ENTRY_MIN + 1 or day.pdl is None:
            return None
        if day.c[i - 1] >= day.pdl or day.c[i] <= day.pdl:
            return None
        atr = day.atr[i]
        if atr is None or atr <= 0:
            return None
        sl = min(day.l[i - 1], day.l[i]) - atr_mult * atr
        return {"sl_abs": sl, "tp": ("r", tp_r)}
    return _sig


def rsi2_5m_thresh(thresh=5.0, sl_mult=1.0, tp_r=2.0):
    """RSI2 del bloque 5-min < thresh -> long (mas selectivo que el live thresh=15)."""
    def _sig(day, i):
        if i % 5 != 4 or i < 34:
            return None
        k = i // 5
        if k >= len(day.f_rsi2) or day.f_rsi2[k] is None:
            return None
        if day.f_rsi2[k] >= thresh:
            return None
        atr = _f_atr(day, k)
        if atr is None or atr <= 0:
            return None
        sl = day.f_l[k] - sl_mult * atr
        return {"sl_abs": sl, "tp": ("r", tp_r)}
    return _sig


# ─────────────────────────── roster ─────────────────────────────────────────

# ─────────────────────────── señales batch 2 — filtros selectivos ─────────────────────────

def ibs5_long_pm(sl_mult=1.0, tp_r=2.0, max_ibs=0.2, min_block=30):
    """IBS(5m) < max_ibs, solo despues de min_block (block 30 = 12:00 ET)."""
    def _sig(day, i):
        if i % 5 != 4:
            return None
        k = i // 5
        if k < min_block or k >= len(day.f_h):
            return None
        ibs = _ibs(day, k)
        if ibs is None or ibs >= max_ibs:
            return None
        atr = _f_atr(day, k)
        if atr is None or atr <= 0:
            return None
        sl = day.f_l[k] - sl_mult * atr
        return {"sl_abs": sl, "tp": ("r", tp_r)}
    return _sig


def ibs5_below_vwap(sl_mult=1.0, tp_r=2.0, max_ibs=0.2):
    """IBS(5m) < max_ibs AND 5-min close < VWAP (oversold AND below VWAP = mean-reversion)."""
    def _sig(day, i):
        if i % 5 != 4 or i < 34:
            return None
        k = i // 5
        if k >= len(day.f_h):
            return None
        ibs = _ibs(day, k)
        if ibs is None or ibs >= max_ibs:
            return None
        if day.vwap[i] is None or day.f_c[k] >= day.vwap[i]:
            return None
        atr = _f_atr(day, k)
        if atr is None or atr <= 0:
            return None
        sl = day.f_l[k] - sl_mult * atr
        return {"sl_abs": sl, "tp": ("r", tp_r)}
    return _sig


def pdl_reclaim_after_noon(atr_mult=0.5, tp_r=2.0):
    """PDL reclaim, solo despues de 12:00 ET (menos ruido de apertura)."""
    def _sig(day, i):
        if i < 150 + 1 or day.pdl is None:   # 150 = 12:00 ET
            return None
        if day.c[i - 1] >= day.pdl or day.c[i] <= day.pdl:
            return None
        atr = day.atr[i]
        if atr is None or atr <= 0:
            return None
        sl = min(day.l[i - 1], day.l[i]) - atr_mult * atr
        return {"sl_abs": sl, "tp": ("r", tp_r)}
    return _sig


def orb_fade_long_tight(atr_mult=0.3, tp_r=1.5):
    """ORB fade long con SL mas ajustado y TP 1.5R."""
    def _sig(day, i):
        if i < ENTRY_MIN + 1 or day.or_low is None:
            return None
        if day.c[i - 1] >= day.or_low or day.c[i] <= day.or_low:
            return None
        atr = day.atr[i]
        if atr is None or atr <= 0:
            return None
        sl = min(day.l[i - 1], day.l[i]) - atr_mult * atr
        return {"sl_abs": sl, "tp": ("r", tp_r)}
    return _sig


ROSTER = [
    # Batch 1: señales base
    ("IBS(5m)<0.2 long",       "NEW",  lambda d: run_market(d,  ibs5_long(1.0, 2.0, 0.20),  c4=True)),
    ("IBS(5m)<0.15 long",      "NEW",  lambda d: run_market(d,  ibs5_long(1.0, 2.0, 0.15),  c4=True)),
    ("IBS(5m)>0.8 short",      "NEW",  lambda d: run_market_short(d, ibs5_short(1.0, 2.0, 0.80), c4=True)),
    ("ORB breakout long",      "NEW",  lambda d: run_market(d,  orb_breakout_long(0.5, 2.0), c4=True)),
    ("ORB break short",        "NEW",  lambda d: run_market_short(d, orb_break_short(0.5, 2.0), c4=True)),
    ("ORB fade long",          "NEW",  lambda d: run_market(d,  orb_fade_long(0.5, 2.0),     c4=True)),
    ("ORB fade short",         "NEW",  lambda d: run_market_short(d, orb_fade_short(0.5, 2.0), c4=True)),
    ("PDL reclaim long",       "NEW",  lambda d: run_market(d,  pdl_reclaim_long(0.5, 2.0),  c4=True)),
    ("RSI2(5m)<5 long",        "NEW",  lambda d: run_market(d,  rsi2_5m_thresh(5.0, 1.0, 2.0), c4=True)),
    ("RSI2(5m)<10 long",       "NEW",  lambda d: run_market(d,  rsi2_5m_thresh(10.0, 1.0, 2.0), c4=True)),
    # Batch 2: filtros selectivos
    ("IBS<0.2 post-12:00",     "NEW2", lambda d: run_market(d,  ibs5_long_pm(1.0, 2.0, 0.20, 30), c4=True)),
    ("IBS<0.2 +below VWAP",    "NEW2", lambda d: run_market(d,  ibs5_below_vwap(1.0, 2.0, 0.20), c4=True)),
    ("PDL reclaim post-12:00", "NEW2", lambda d: run_market(d,  pdl_reclaim_after_noon(0.5, 2.0), c4=True)),
    ("ORB fade tight 1.5R",    "NEW2", lambda d: run_market(d,  orb_fade_long_tight(0.3, 1.5),    c4=True)),
]


def fmt_row(label, s):
    if s is None or s["n"] == 0:
        return f"  {label:<25}  n=    0  —"
    wlb = wilson_lb(s["w"], s["n"])
    hs  = horizon_score(s)
    total = hs["total"]
    verdict = hs["verdict"]
    pf_s = f"{s['pf']:.3f}" if s["pf"] != float("inf") else "  inf"
    return (f"  {label:<25}  n={s['n']:>5}  hit={s['hit']:5.1f}%(lb{wlb*100:4.1f}%)"
            f"  PF={pf_s}  pnl/sh={s['pnl']:>+7.2f}  mLL={s['mll']:>2}"
            f"  score={total:>5.1f}  [{verdict}]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="YYYY: anno de inicio (default=2016)")
    ap.add_argument("--json",  default=None)
    a = ap.parse_args()

    years = range(int(a.since) if a.since else 2016, 2027)
    print(f"Cargando {min(years)}-{max(years)} 1-min QQQ...")
    days = load_days(years)
    print(f"{len(days)} dias. Corriendo {len(ROSTER)} señales nuevas...\n")

    results = {}
    for label, status, runner in ROSTER:
        trades = runner(days)
        s = stats(trades) if trades else None
        results[label] = {"status": status, "stats": s}
        print(fmt_row(label, s))

    # resumen de supervivientes
    survivors = [(lb, r["stats"]) for lb, r in results.items()
                 if r["stats"] and r["stats"]["n"] >= 50 and horizon_score(r["stats"])["total"] >= 45]
    print(f"\n--- Supervivientes (n>=50, score>=45 PAPER): {len(survivors)} ---")
    for lb, s in sorted(survivors, key=lambda x: horizon_score(x[1])["total"], reverse=True):
        print(fmt_row(lb, s))

    if a.json:
        import json
        out = {}
        for lb, r in results.items():
            s = r["stats"]
            out[lb] = {
                "n": s["n"] if s else 0,
                "pf": s["pf"] if s else 0,
                "hit": s["hit"] if s else 0,
                "pnl": s["pnl"] if s else 0,
                "score": horizon_score(s)["total"] if s else 0,
            }
        with open(a.json, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\nResultados en {a.json}")


if __name__ == "__main__":
    main()
