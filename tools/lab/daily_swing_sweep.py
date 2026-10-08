"""Nuevos candidatos de señal DIARIA — temporalidad similar a gt_closelow_v2.

Señales nunca barridas antes (2026-10-08):
  1. clr2_both      — dos días consecutivos clr < 0.20 (doble presión)
  2. high_vol_clr   — clr < 0.10 + volumen > 1.5× media20 (señal con volumen)
  3. outside_down   — barra exterior + clr < 0.15 (outside day bearish close)
  4. hammer_daily   — mecha inferior > 60% del rango + close > open (bullish hammer)
  5. dist_sma20     — cierre 1.5%+ por debajo de SMA20 (overshooting mean)
  6. gap_dn_recov   — abrió con gap bajista + cerró en verde (rechazo del gap)
  7. ohl_distrib    — abrió por encima del prev_close + cerró en 15% inferior del rango

Metodología idéntica a backtest_all_daily_gt.py:
  - Episodios (GAP_TOLERANCE=3), no bar-a-bar
  - Hold periods: 2, 3, 5 días
  - Score = 100% PF, hit informativo (ver backlog.md)
  - Full (27a) + recent (2021-2026)
  - No LLM, no Supabase, offline
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from _score_common import horizon_score, wilson_lb
from backtest import stats

DATA = Path(__file__).parent.parent / "data" / "qqq_daily_full.json"
GAP_TOLERANCE = 3
HOLDS = (2, 3, 5)
RECENT_CUT = "2021-01-01"


# ─────────────────────────── helpers ────────────────────────────────────────

def sma(values, period, i):
    if i < period - 1:
        return None
    return sum(values[i - period + 1 : i + 1]) / period


def vol_sma(volumes, period, i):
    if i < period:
        return None
    return sum(volumes[i - period : i]) / period  # excluye barra actual (causal)


def find_episodes(flags):
    raw_runs, i, n = [], 0, len(flags)
    while i < n:
        if flags[i]:
            j = i
            while j < n and flags[j]:
                j += 1
            raw_runs.append([i, j - 1])
            i = j
        else:
            i += 1
    if not raw_runs:
        return []
    merged = [raw_runs[0]]
    for run in raw_runs[1:]:
        if run[0] - merged[-1][1] - 1 <= GAP_TOLERANCE:
            merged[-1][1] = run[1]
        else:
            merged.append(run)
    return merged


def fmt(s, n_ep):
    if s is None or s["n"] == 0:
        return "n=0"
    wlb = wilson_lb(s["w"], s["n"])
    pf_s = f"{s['pf']:.3f}" if s["pf"] != float("inf") else "  inf"
    return (f"ep={n_ep:>4}  n={s['n']:>4}  "
            f"hit={s['hit']:5.1f}%(wlb {wlb*100:4.1f}%)  "
            f"PF={pf_s}  ret={100*s['pnl']:>+6.1f}pp")


# ─────────────────────────── señales ────────────────────────────────────────
# Cada señal recibe arrays y devuelve lista de bools (flag[i] = señal en barra i).
# Entry = open[i+1], exit = close[i+hold].
# CAUSAL: solo usa información disponible al cierre de la barra i.

def sig_clr2_both(closes, opens, highs, lows, volumes, dates):
    """Dos días consecutivos clr < 0.20."""
    n = len(closes)
    clr = [(closes[i] - lows[i]) / (highs[i] - lows[i]) if highs[i] > lows[i] else 0.5
           for i in range(n)]
    return [i >= 1 and clr[i] < 0.20 and clr[i - 1] < 0.20 for i in range(n)]


def sig_high_vol_clr(closes, opens, highs, lows, volumes, dates):
    """clr < 0.10 + volumen > 1.5× media20 de días anteriores."""
    n = len(closes)
    clr = [(closes[i] - lows[i]) / (highs[i] - lows[i]) if highs[i] > lows[i] else 0.5
           for i in range(n)]
    flags = []
    for i in range(n):
        if clr[i] >= 0.10:
            flags.append(False)
            continue
        avg_v = vol_sma(volumes, 20, i)
        if avg_v is None or avg_v == 0:
            flags.append(False)
            continue
        flags.append(volumes[i] > 1.5 * avg_v)
    return flags


def sig_outside_down(closes, opens, highs, lows, volumes, dates):
    """Barra exterior (high > prev_high, low < prev_low) + clr < 0.15."""
    n = len(closes)
    clr = [(closes[i] - lows[i]) / (highs[i] - lows[i]) if highs[i] > lows[i] else 0.5
           for i in range(n)]
    flags = [False]
    for i in range(1, n):
        outside = highs[i] > highs[i - 1] and lows[i] < lows[i - 1]
        flags.append(outside and clr[i] < 0.15)
    return flags


def sig_hammer_daily(closes, opens, highs, lows, volumes, dates):
    """Mecha inferior ≥ 60% del rango + barra alcista (close > open)."""
    n = len(closes)
    flags = []
    for i in range(n):
        rng = highs[i] - lows[i]
        if rng <= 0:
            flags.append(False)
            continue
        body_low = min(opens[i], closes[i])
        lower_wick = body_low - lows[i]
        bullish = closes[i] > opens[i]
        flags.append(bullish and lower_wick / rng >= 0.60)
    return flags


def sig_dist_sma20(closes, opens, highs, lows, volumes, dates):
    """Cierre 1.5%+ por debajo de SMA20 (excluye día actual del cálculo)."""
    n = len(closes)
    flags = []
    for i in range(n):
        ma = sma(closes, 20, i - 1) if i >= 1 else None  # SMA de los 20 días previos
        if ma is None:
            flags.append(False)
            continue
        flags.append(closes[i] < ma * 0.985)
    return flags


def sig_gap_dn_recov(closes, opens, highs, lows, volumes, dates):
    """Abrió con gap bajista (open < prev_close) + cerró en verde (close > open)."""
    n = len(closes)
    flags = [False]
    for i in range(1, n):
        gap_down = opens[i] < closes[i - 1]
        bullish = closes[i] > opens[i]
        flags.append(gap_down and bullish)
    return flags


def sig_ohl_distrib(closes, opens, highs, lows, volumes, dates):
    """Abrió por encima del prev_close (gap up o flat-up) + cerró en 15% inferior del rango.
    Señal de distribución: compradores en la apertura, vendedores en el cierre."""
    n = len(closes)
    clr = [(closes[i] - lows[i]) / (highs[i] - lows[i]) if highs[i] > lows[i] else 0.5
           for i in range(n)]
    flags = [False]
    for i in range(1, n):
        opened_up = opens[i] > closes[i - 1]
        flags.append(opened_up and clr[i] < 0.15)
    return flags


SIGNALS = [
    ("clr2_both",    "Dos dias consecutivos clr<0.20",             sig_clr2_both),
    ("high_vol_clr", "clr<0.10 + vol>1.5x avg20",                 sig_high_vol_clr),
    ("outside_down", "Barra exterior + clr<0.15",                  sig_outside_down),
    ("hammer_daily", "Mecha inferior>=60% del rango + close>open", sig_hammer_daily),
    ("dist_sma20",   "Close 1.5%+ bajo SMA20",                     sig_dist_sma20),
    ("gap_dn_recov", "Gap bajista + cierre en verde",               sig_gap_dn_recov),
    ("ohl_distrib",  "Abrio arriba + cerro en 15% inferior",       sig_ohl_distrib),
]


# ─────────────────────────── motor ──────────────────────────────────────────

def run_signal(flag_fn, closes, opens, highs, lows, volumes, dates, hold, recent_cut):
    flags = flag_fn(closes, opens, highs, lows, volumes, dates)
    episodes = find_episodes(flags)
    n = len(closes)
    trades_full, trades_recent = [], []
    for start, _end in episodes:
        entry_i = start + 1
        exit_i = entry_i + hold - 1
        if exit_i >= n:
            continue
        r = closes[exit_i] / opens[entry_i] - 1
        t = {"day": dates[entry_i], "pnl": r}
        trades_full.append(t)
        if dates[entry_i] >= recent_cut:
            trades_recent.append(t)
    return episodes, trades_full, trades_recent


def main():
    raw = json.loads(DATA.read_text())
    raw.sort(key=lambda b: b["t"])
    dates   = [b["t"][:10] for b in raw]
    opens   = [b["o"]      for b in raw]
    closes  = [b["c"]      for b in raw]
    highs   = [b["h"]      for b in raw]
    lows    = [b["l"]      for b in raw]
    volumes = [b.get("v", 0) for b in raw]
    print(f"QQQ diario: {len(dates)} sesiones ({dates[0]} -> {dates[-1]})\n")

    # baseline: comprar siempre al open, vender al close+N
    print("=== BASELINE (comprar siempre) ===")
    for hold in HOLDS:
        bl = []
        for i in range(len(dates) - hold):
            r = closes[i + hold - 1] / opens[i] - 1
            bl.append({"day": dates[i], "pnl": r})
        s = stats(bl)
        sc = horizon_score(s)
        print(f"  hold={hold}d  n={s['n']}  hit={s['hit']:.1f}%  PF={s['pf']:.3f}  "
              f"ret={100*s['pnl']:+.1f}pp  score={sc['total']:.1f}")
    print()

    results = {}
    for name, desc, flag_fn in SIGNALS:
        print(f"{'='*60}")
        print(f"  {name}: {desc}")
        best_score, best_hold = -999, None
        for hold in HOLDS:
            ep, tf, tr = run_signal(
                flag_fn, closes, opens, highs, lows, volumes, dates, hold, RECENT_CUT
            )
            sf = stats(tf)
            sr = stats(tr)
            scf = horizon_score(sf)
            scr = horizon_score(sr)
            tag = ""
            if scf["total"] >= 65:
                tag = "  DEPLOY!"
            elif scf["total"] >= 45:
                tag = "  PAPER"
            label_r = f"  recent={fmt(sr, len(ep))}" if sr and sr["n"] > 0 else ""
            print(f"  hold={hold}d  FULL: {fmt(sf, len(ep))}  "
                  f"score={scf['total']:.1f} [{scf['verdict']}]{tag}{label_r}")
            if scf["total"] > best_score:
                best_score, best_hold = scf["total"], hold
        print(f"  > mejor hold: {best_hold}d  score={best_score:.1f}")
        print()
        results[name] = {"desc": desc, "best_hold": best_hold, "best_score": best_score}

    # resumen
    print("=" * 60)
    print("RESUMEN (ordenado por score full)")
    ranked = sorted(results.items(), key=lambda x: -x[1]["best_score"])
    for name, r in ranked:
        verdict = "DEPLOY" if r["best_score"] >= 65 else ("PAPER" if r["best_score"] >= 45 else "KILLED")
        print(f"  {name:<16}  hold={r['best_hold']}d  score={r['best_score']:5.1f}  [{verdict}]")


if __name__ == "__main__":
    main()
