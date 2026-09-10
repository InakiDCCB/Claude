"""
tools/lab/gap_down_backtest.py
Backtest de la señal gap_down_sin_llenar sobre QQQ diario 2016-2026.

Señal (replica regla SQL situational_snapshot):
  Dia D: open_D < low_{D-1}  AND  close_D < low_{D-1}
  => gap abajo EXTERIOR que aguanto todo el dia => sesgo bullish para D+1.

Prueba dos modalidades:
  A) Fixed hold: 1, 2, 3, 5 dias (buy open D+1, exit close D+hold)
  B) SL/TP ATR: grid SL=[0.5,1.0,1.5]xATR14 x TP=[1.0,1.5,2.0]xATR14
     Simulacion dia a dia con barra diaria:
       - Entrada: open D+1
       - Conservador: si low[j] <= sl_price => SL (incluso dia entrada)
       - Si high[j] >= tp_price => TP
       - Time-stop: cierre de la ultima barra del hold maximo

Referencia: gt_closelow_v2 (LIVE swing v3.1.14) sobre los mismos datos.

Uso:
  uv run python tools/lab/gap_down_backtest.py
  uv run python tools/lab/gap_down_backtest.py --since 2020
  uv run python tools/lab/gap_down_backtest.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest import stats
from _score_common import horizon_score, seasonality_breakdown, print_seasonality, wilson_lb

DATA = Path(__file__).parent.parent / "data" / "qqq_daily_full.json"
MAX_HOLD = 5   # dias maximos de time-stop en simulacion SL/TP


# ── indicadores ───────────────────────────────────────────────────────────────

def ema(closes, n):
    out = [None] * len(closes)
    if len(closes) < n:
        return out
    s = sum(closes[:n]) / n
    out[n-1] = s
    k = 2 / (n + 1)
    for i in range(n, len(closes)):
        s = closes[i] * k + s * (1 - k)
        out[i] = s
    return out


def wilder_rsi2_daily(closes):
    n, out = 2, [None] * len(closes)
    if len(closes) < n + 1:
        return out
    gains  = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    out[n] = 100 - 100 / (1 + (ag / al if al else 1e9))
    for i in range(n+1, len(closes)):
        ag = (ag * (n-1) + gains[i-1]) / n
        al = (al * (n-1) + losses[i-1]) / n
        out[i] = 100 - 100 / (1 + (ag / al if al else 1e9))
    return out


def wilder_atr(highs, lows, closes, n=14):
    m = len(closes)
    trs = [highs[0] - lows[0]] + [
        max(highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i]  - closes[i-1]))
        for i in range(1, m)
    ]
    atr = [None] * m
    if m <= n:
        return atr
    atr[n] = sum(trs[1:n+1]) / n
    for i in range(n+1, m):
        atr[i] = (atr[i-1] * (n-1) + trs[i]) / n
    return atr


# ── señal ─────────────────────────────────────────────────────────────────────

def find_signals(opens, highs, lows, closes):
    """
    Devuelve lista de indices i donde:
      open[i] < low[i-1] AND close[i] < low[i-1]
      (gap abajo exterior que aguanto todo el dia D=i)
    La entrada es en open[i+1].
    """
    signals = []
    for i in range(1, len(closes)):
        if opens[i] < lows[i-1] and closes[i] < lows[i-1]:
            signals.append(i)
    return signals


# ── clase DailyBar (duck-type para _score_common) ─────────────────────────────

class DailyBar:
    __slots__ = ("date", "h", "l", "c", "v")
    def __init__(self, date, h, l, c, v):
        self.date = date
        self.h = [h]; self.l = [l]; self.c = [c]; self.v = [v]


# ── simulacion fixed-hold ─────────────────────────────────────────────────────

def sim_fixed_hold(signals, dates, opens, closes, n_total, hold):
    trades = []
    for i in signals:
        entry_i = i + 1
        exit_i  = i + hold
        if exit_i >= n_total:
            continue
        entry = opens[entry_i]
        if entry <= 0:
            continue
        exit_ = closes[exit_i]
        trades.append({"day": dates[entry_i], "pnl": exit_ / entry - 1})
    return trades


# ── simulacion SL/TP bar-a-bar (diario) ──────────────────────────────────────

def sim_sltp(signals, dates, opens, highs, lows, closes, atr,
             sl_mult, tp_mult, max_hold=MAX_HOLD):
    """
    Entrada open[i+1]. SL/TP basados en ATR del dia señal (i).
    Conservador: en cada barra, SL se chequea antes que TP.
    Si se abre debajo del SL (gap down en el broker), asume fill en SL.
    """
    trades = []
    n = len(closes)
    for i in signals:
        if atr[i] is None:
            continue
        entry_i = i + 1
        if entry_i >= n:
            continue
        entry   = opens[entry_i]
        if entry <= 0:
            continue
        sl_price = entry - sl_mult * atr[i]
        tp_price = entry + tp_mult * atr[i]
        pnl_pct  = None

        for j in range(entry_i, min(entry_i + max_hold, n)):
            # gap down al abrir por debajo del SL (ej. noticias overnight)
            if opens[j] <= sl_price:
                pnl_pct = sl_price / entry - 1
                break
            if lows[j] <= sl_price:
                pnl_pct = sl_price / entry - 1
                break
            if highs[j] >= tp_price:
                pnl_pct = tp_price / entry - 1
                break
        else:
            # time-stop: cierre de la ultima barra del hold
            last_j = min(entry_i + max_hold - 1, n - 1)
            pnl_pct = closes[last_j] / entry - 1

        trades.append({"day": dates[entry_i], "pnl": pnl_pct,
                       "sl": sl_mult, "tp": tp_mult})
    return trades


# ── referencia gt_closelow_v2 ─────────────────────────────────────────────────

def find_ll_agotamiento(highs, lows, closes):
    """
    lower_low structure (hoy < ayer en ambos extremos) PERO cierre > midpoint.
    Interpreta: hubo intento de continuacion bajista que fallo => sesgo bullish D+1.
    """
    sigs = []
    for i in range(1, len(closes)):
        h, l, c = highs[i], lows[i], closes[i]
        ph, pl = highs[i-1], lows[i-1]
        if h < ph and l < pl and c > (h + l) / 2:
            sigs.append(i)
    return sigs


def find_hh_agotamiento(highs, lows, closes):
    """
    higher_high structure PERO cierre < midpoint => sesgo bearish D+1.
    (Referencia para el otro lado — no implementamos shorts, solo informativo.)
    """
    sigs = []
    for i in range(1, len(closes)):
        h, l, c = highs[i], lows[i], closes[i]
        ph, pl = highs[i-1], lows[i-1]
        if h > ph and l > pl and c < (h + l) / 2:
            sigs.append(i)
    return sigs


def rolling_atr_percentile(atr, window=60):
    """Percentil del ATR actual dentro de su ventana rodante. 0=minimo, 1=maximo."""
    n = len(atr)
    out = [None] * n
    for i in range(n):
        if atr[i] is None:
            continue
        start = max(0, i - window + 1)
        vals = [v for v in atr[start:i+1] if v is not None]
        if len(vals) < 5:
            continue
        rank = sum(1 for v in vals if v <= atr[i]) / len(vals)
        out[i] = rank
    return out


def ref_gt_closelow_v2(dates, opens, highs, lows, closes, n_total, hold=3):
    clr = [(closes[i] - lows[i]) / (highs[i] - lows[i])
           if highs[i] > lows[i] else 0.5
           for i in range(n_total)]
    trades = []
    in_trade_until = -1
    for i in range(1, n_total):
        if i <= in_trade_until:
            continue
        if clr[i-1] < 0.1:
            entry_i = i
            exit_i  = i + hold - 1
            if exit_i >= n_total:
                break
            entry = opens[entry_i]
            exit_ = closes[exit_i]
            if entry > 0:
                trades.append({"day": dates[entry_i], "pnl": exit_ / entry - 1})
            in_trade_until = exit_i
    return trades


# ── output ────────────────────────────────────────────────────────────────────

def fmt(s, sc):
    if s is None or s["n"] == 0:
        return "n=0"
    wlb = wilson_lb(s["w"], s["n"])
    wlb_s = f"{wlb*100:.1f}%" if wlb is not None else "?"
    pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "inf"
    return (f"n={s['n']:>4}  hit={s['hit']:5.1f}%(wlb {wlb_s})  "
            f"PF={pf_s:>5}  ret={100*s['pnl']:>+7.1f}pp  mLL={s['mll']:>2}  "
            f"score={sc['total']:.1f} [{sc['verdict']}]")


def year_table(trades, label=""):
    by_year: dict[str, list] = {}
    for t in trades:
        yr = t["day"][:4]
        by_year.setdefault(yr, []).append(t)
    if label:
        print(f"  Año a año — {label}:")
    print(f"  {'Año':<6} {'n':>4}  {'Hit%':>6}  {'PF':>5}  {'ret_total':>10}")
    for yr in sorted(by_year):
        s = stats(by_year[yr])
        if s:
            pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else " inf"
            print(f"  {yr:<6} {s['n']:>4}  {s['hit']:>5.1f}%  {pf_s:>5}  "
                  f"{100*s['pnl']:>+9.1f}pp")
    print()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="YYYY-MM-DD para filtrar")
    ap.add_argument("--json",  action="store_true")
    args = ap.parse_args()

    raw = json.loads(DATA.read_text())
    raw.sort(key=lambda b: b["t"])

    if args.since:
        raw = [b for b in raw if b["t"][:10] >= args.since]

    dates  = [b["t"][:10] for b in raw]
    opens  = [float(b["o"]) for b in raw]
    highs  = [float(b["h"]) for b in raw]
    lows   = [float(b["l"]) for b in raw]
    closes = [float(b["c"]) for b in raw]
    vols   = [float(b.get("v", 0)) for b in raw]
    n      = len(dates)

    atr14 = wilder_atr(highs, lows, closes, n=14)

    print(f"QQQ diario: {n} sesiones ({dates[0]} -> {dates[-1]})\n")

    # ── señales ──────────────────────────────────────────────────────────────
    signals = find_signals(opens, highs, lows, closes)
    freq_pct = 100 * len(signals) / n if n else 0
    print(f"gap_down_sin_llenar: {len(signals)} señales ({freq_pct:.1f}% de sesiones)\n")

    day_objs = [DailyBar(dates[i], highs[i], lows[i], closes[i], vols[i]) for i in range(n)]

    results = {}

    # ── A) Fixed hold ──────────────────────────────────────────────────────
    print("=== A) Fixed hold (buy open D+1, exit close D+hold) ===")
    for hold in [1, 2, 3, 5]:
        trades = sim_fixed_hold(signals, dates, opens, closes, n, hold)
        s  = stats(trades)
        sc = horizon_score(s)
        key = f"hold_{hold}d"
        results[key] = {"trades": trades, "stats": s, "score": sc}
        print(f"  hold={hold}d  {fmt(s, sc)}")

    # ── B) SL/TP grid ──────────────────────────────────────────────────────
    print("\n=== B) SL/TP grid (ATR14, max_hold=5d) ===")
    best_sltp = None
    best_score = -1
    sl_mults = [0.5, 1.0, 1.5]
    tp_mults = [1.0, 1.5, 2.0]
    print(f"  {'Config':<16} {'n':>4}  {'Hit%':>6}  {'PF':>5}  {'ret':>8}  {'mLL':>4}  "
          f"{'Score':>6}  Veredicto")
    for sl_m in sl_mults:
        for tp_m in tp_mults:
            trades = sim_sltp(signals, dates, opens, highs, lows, closes, atr14,
                              sl_m, tp_m)
            s  = stats(trades)
            sc = horizon_score(s)
            key = f"sl{sl_m}R_tp{tp_m}R"
            results[key] = {"trades": trades, "stats": s, "score": sc}
            if s and sc["total"] > best_score:
                best_score = sc["total"]
                best_sltp  = (sl_m, tp_m, key)
            if s:
                wlb = wilson_lb(s["w"], s["n"])
                pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "  inf"
                print(f"  SL={sl_m}R TP={tp_m}R    "
                      f"{s['n']:>4}  {s['hit']:>5.1f}%  {pf_s}  "
                      f"{100*s['pnl']:>+7.1f}pp  {s['mll']:>4}  "
                      f"{sc['total']:>5.1f}  {sc['verdict']}")
            else:
                print(f"  SL={sl_m}R TP={tp_m}R    n=0")

    # ── Referencia gt_closelow_v2 ──────────────────────────────────────────
    print("\n=== REF: gt_closelow_v2 (LIVE, hold=3d) ===")
    gt2_trades = ref_gt_closelow_v2(dates, opens, highs, lows, closes, n, hold=3)
    s_gt2  = stats(gt2_trades)
    sc_gt2 = horizon_score(s_gt2)
    results["gt_closelow_v2_ref"] = {"trades": gt2_trades, "stats": s_gt2, "score": sc_gt2}
    print(f"  {fmt(s_gt2, sc_gt2)}")

    # ── Detalles mejores variantes ─────────────────────────────────────────
    print("\n=== Año a año — mejores variantes ===")

    # Mejor fixed hold
    best_hold = max(
        [(k, results[k]) for k in results if k.startswith("hold_")],
        key=lambda x: x[1]["score"]["total"] if x[1]["stats"] else -1
    )
    year_table(best_hold[1]["trades"], f"MEJOR fixed hold ({best_hold[0]})")

    # Mejor SL/TP
    if best_sltp:
        key_sltp = best_sltp[2]
        label_sltp = f"MEJOR SL/TP (SL={best_sltp[0]}R TP={best_sltp[1]}R)"
        year_table(results[key_sltp]["trades"], label_sltp)

    # gt_closelow_v2
    year_table(gt2_trades, "gt_closelow_v2 ref")

    # ── Estacionalidad mejor variante SL/TP ──────────────────────────────
    if best_sltp:
        key_sltp = best_sltp[2]
        trades_best = results[key_sltp]["trades"]
        if trades_best:
            print(f"=== Estacionalidad — {key_sltp} ===")
            seas = seasonality_breakdown(trades_best, day_objs, stats)
            print_seasonality(seas)
            print()

    # ── Overlap con gt_closelow_v2 ─────────────────────────────────────────
    gdsl_entry_dates = {results["hold_1d"]["trades"][k]["day"]
                        for k in range(len(results["hold_1d"]["trades"]))}
    gt2_entry_dates  = {t["day"] for t in gt2_trades}
    overlap = gdsl_entry_dates & gt2_entry_dates
    print(f"=== Overlap gap_down vs gt_closelow_v2 ===")
    print(f"  gdsl entries: {len(gdsl_entry_dates)}"
          f"  gt2 entries: {len(gt2_entry_dates)}"
          f"  overlap: {len(overlap)} ({100*len(overlap)/len(gdsl_entry_dates):.1f}% gdsl)")
    print()

    # ── C) Filtros de regimen alcista ──────────────────────────────────────
    print("=== C) Filtros de regimen (base: hold_3d y hold_5d) ===")
    print()

    ema50_arr  = ema(closes, 50)
    ema200_arr = ema(closes, 200)
    rsi2_arr   = wilder_rsi2_daily(closes)

    # Precio relativo YoY (cierre vs cierre hace 252 dias)
    yoy = [None] * n
    for i in range(252, n):
        yoy[i] = closes[i] / closes[i - 252] - 1   # positivo = mercado sube YoY

    # Precio relativo vs cierre hace 63 dias (trimestre)
    qtr = [None] * n
    for i in range(63, n):
        qtr[i] = closes[i] / closes[i - 63] - 1

    REGIMES = [
        ("sin_filtro",           lambda i: True),
        ("ema200_above",         lambda i: ema200_arr[i] is not None and closes[i] > ema200_arr[i]),
        ("ema50_above",          lambda i: ema50_arr[i]  is not None and closes[i] > ema50_arr[i]),
        ("ema50_and_200",        lambda i: (ema200_arr[i] is not None and ema50_arr[i] is not None
                                            and closes[i] > ema200_arr[i]
                                            and closes[i] > ema50_arr[i])),
        ("yoy_positive",         lambda i: yoy[i] is not None and yoy[i] > 0),
        ("qtr_positive",         lambda i: qtr[i] is not None and qtr[i] > 0),
        ("ema200_and_yoy",       lambda i: (ema200_arr[i] is not None and yoy[i] is not None
                                            and closes[i] > ema200_arr[i] and yoy[i] > 0)),
        ("rsi2d_lt30",           lambda i: rsi2_arr[i] is not None and rsi2_arr[i] < 30),
        ("ema200_rsi2d_lt30",    lambda i: (ema200_arr[i] is not None and rsi2_arr[i] is not None
                                            and closes[i] > ema200_arr[i]
                                            and rsi2_arr[i] < 30)),
        ("ema200_rsi2d_lt10",    lambda i: (ema200_arr[i] is not None and rsi2_arr[i] is not None
                                            and closes[i] > ema200_arr[i]
                                            and rsi2_arr[i] < 10)),
    ]

    hdr = f"  {'Filtro':<24} {'hold':>5}  {'n':>4}  {'Hit%':>6}  {'PF':>5}  {'ret':>8}  {'mLL':>4}  {'Score':>6}  Veredicto"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    regime_results = {}
    for name, fn in REGIMES:
        filtered = [i for i in signals if fn(i)]
        for hold in [3, 5]:
            trades = sim_fixed_hold(filtered, dates, opens, closes, n, hold)
            s  = stats(trades)
            sc = horizon_score(s)
            key = f"{name}_h{hold}"
            regime_results[key] = {"trades": trades, "stats": s, "score": sc,
                                   "n_signals": len(filtered)}
            if s:
                pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "  inf"
                star = " *" if sc["total"] >= 45 else ""
                print(f"  {name:<24} {hold:>5}d  {s['n']:>4}  {s['hit']:>5.1f}%  "
                      f"{pf_s:>5}  {100*s['pnl']:>+7.1f}pp  {s['mll']:>4}  "
                      f"{sc['total']:>5.1f}  {sc['verdict']}{star}")
            else:
                print(f"  {name:<24} {hold:>5}d  n=0")

    # Mejor filtro por score
    best_key = max(regime_results,
                   key=lambda k: regime_results[k]["score"]["total"]
                                 if regime_results[k]["stats"] else -1)
    best_r = regime_results[best_key]
    print(f"\n  Mejor: {best_key}")
    if best_r["stats"]:
        print(f"  {fmt(best_r['stats'], best_r['score'])}")
        print()
        year_table(best_r["trades"], f"Mejor regimen ({best_key})")
        seas = seasonality_breakdown(best_r["trades"], day_objs, stats)
        print(f"  Estacionalidad regimen/vol:")
        for k in sorted(seas.get("by_regime", {})):
            v = seas["by_regime"][k]
            pf_s = v["pf"] if isinstance(v["pf"], str) else f"{v['pf']:.2f}"
            print(f"    {k:<16} n={v['n']:>3}  hit={v['hit']:>5.1f}%  "
                  f"pnl={v['pnl']:>+6.2f}  PF={pf_s}")
        print()

    # ── D) ll_agotamiento ─────────────────────────────────────────────────────
    print("\n=== D) ll_agotamiento (lower_low + close>mid => bullish D+1) ===")
    ll_signals = find_ll_agotamiento(highs, lows, closes)
    hh_signals = find_hh_agotamiento(highs, lows, closes)
    freq_ll = 100 * len(ll_signals) / n if n else 0
    freq_hh = 100 * len(hh_signals) / n if n else 0
    print(f"ll_agotamiento: {len(ll_signals)} señales ({freq_ll:.1f}%)  "
          f"| hh_agotamiento (ref bearish): {len(hh_signals)} ({freq_hh:.1f}%)")

    # Overlap ll vs gap_down
    gdsl_sig_dates = {dates[i] for i in signals}
    ll_sig_dates   = {dates[i] for i in ll_signals}
    ov_ll = gdsl_sig_dates & ll_sig_dates
    print(f"  Overlap gdsl∩ll: {len(ov_ll)} dias ({100*len(ov_ll)/max(len(ll_signals),1):.1f}% de ll)\n")

    LL_REGIMES = [
        ("sin_filtro",     lambda i: True),
        ("ema200_above",   lambda i: ema200_arr[i] is not None and closes[i] > ema200_arr[i]),
        ("ema200_and_yoy", lambda i: (ema200_arr[i] is not None and yoy[i] is not None
                                      and closes[i] > ema200_arr[i] and yoy[i] > 0)),
        ("ema200_rsi2d_lt30", lambda i: (ema200_arr[i] is not None and rsi2_arr[i] is not None
                                          and closes[i] > ema200_arr[i] and rsi2_arr[i] < 30)),
        ("ema200_rsi2d_lt10", lambda i: (ema200_arr[i] is not None and rsi2_arr[i] is not None
                                          and closes[i] > ema200_arr[i] and rsi2_arr[i] < 10)),
        ("gdsl_excl",      lambda i: i not in {s for s in signals}),   # no-overlap con gap_down
        ("ema200_excl",    lambda i: (ema200_arr[i] is not None and closes[i] > ema200_arr[i]
                                      and i not in {s for s in signals})),
    ]
    # Pre-compute signal set for exclusion filter
    signal_set = set(signals)
    LL_REGIMES[5] = ("gdsl_excl",   lambda i, ss=signal_set: i not in ss)
    LL_REGIMES[6] = ("ema200_excl", lambda i, ss=signal_set:
                      ema200_arr[i] is not None and closes[i] > ema200_arr[i] and i not in ss)

    print(f"  {'Filtro':<24} {'hold':>5}  {'n':>4}  {'Hit%':>6}  {'PF':>5}  "
          f"{'ret':>8}  {'mLL':>4}  {'Score':>6}  Veredicto")
    print("  " + "-" * 88)

    ll_best_key, ll_best_score = None, -1
    ll_regime_results = {}
    for name, fn in LL_REGIMES:
        for hold in [1, 3, 5]:
            filtered = [i for i in ll_signals if fn(i)]
            trades = sim_fixed_hold(filtered, dates, opens, closes, n, hold)
            s  = stats(trades)
            sc = horizon_score(s)
            key = f"ll_{name}_h{hold}"
            ll_regime_results[key] = {"trades": trades, "stats": s, "score": sc}
            if s:
                pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "  inf"
                star = " *" if sc["total"] >= 45 else ""
                print(f"  {name:<24} {hold:>5}d  {s['n']:>4}  {s['hit']:>5.1f}%  "
                      f"{pf_s:>5}  {100*s['pnl']:>+7.1f}pp  {s['mll']:>4}  "
                      f"{sc['total']:>5.1f}  {sc['verdict']}{star}")
                if sc["total"] > ll_best_score:
                    ll_best_score = sc["total"]
                    ll_best_key   = key
            else:
                print(f"  {name:<24} {hold:>5}d  n=0")

    if ll_best_key and ll_regime_results[ll_best_key]["stats"]:
        print(f"\n  Mejor ll: {ll_best_key}")
        print(f"  {fmt(ll_regime_results[ll_best_key]['stats'], ll_regime_results[ll_best_key]['score'])}")
        year_table(ll_regime_results[ll_best_key]["trades"], f"ll mejor ({ll_best_key})")

    # ── E) ATR-percentile filter sobre el mejor config gap_down ──────────────
    print("\n=== E) gap_down + ema200_and_yoy + filtro vol/ATR (hold_5d) ===")

    atr_pct = rolling_atr_percentile(atr14, window=60)

    # Base signals ya filtradas por ema200_and_yoy
    base_signals = [i for i in signals
                    if ema200_arr[i] is not None and yoy[i] is not None
                    and closes[i] > ema200_arr[i] and yoy[i] > 0]

    COMBOS = [
        ("ema200_yoy_base",      lambda i: True),
        ("+ atr_pct < 0.5",      lambda i: atr_pct[i] is not None and atr_pct[i] < 0.5),
        ("+ atr_pct < 0.3",      lambda i: atr_pct[i] is not None and atr_pct[i] < 0.3),
        ("+ atr_pct >= 0.5",     lambda i: atr_pct[i] is not None and atr_pct[i] >= 0.5),
        ("+ atr_pct >= 0.7",     lambda i: atr_pct[i] is not None and atr_pct[i] >= 0.7),
        ("+ rsi2d_lt10",         lambda i: rsi2_arr[i] is not None and rsi2_arr[i] < 10),
        ("+ qtr_positive",       lambda i: qtr[i] is not None and qtr[i] > 0),
        ("+ ema200_rsi2d_lt10",  lambda i: (rsi2_arr[i] is not None and rsi2_arr[i] < 10
                                             and atr_pct[i] is not None)),
    ]

    print(f"  {'Combo':<28} {'n':>4}  {'Hit%':>6}  {'PF':>5}  {'ret':>8}  {'mLL':>4}  "
          f"{'Score':>6}  Veredicto")
    print("  " + "-" * 85)

    best_combo_key, best_combo_score = None, -1
    combo_results = {}
    for name, fn in COMBOS:
        filtered = [i for i in base_signals if fn(i)]
        trades = sim_fixed_hold(filtered, dates, opens, closes, n, 5)
        s  = stats(trades)
        sc = horizon_score(s)
        key = f"gdsl_e_{name}"
        combo_results[key] = {"trades": trades, "stats": s, "score": sc}
        if s:
            pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "  inf"
            star = " *" if sc["total"] >= 65 else (" ." if sc["total"] >= 45 else "")
            print(f"  {name:<28} {s['n']:>4}  {s['hit']:>5.1f}%  "
                  f"{pf_s:>5}  {100*s['pnl']:>+7.1f}pp  {s['mll']:>4}  "
                  f"{sc['total']:>5.1f}  {sc['verdict']}{star}")
            if sc["total"] > best_combo_score:
                best_combo_score = sc["total"]
                best_combo_key   = key
        else:
            print(f"  {name:<28} n=0")

    if best_combo_key:
        r = combo_results[best_combo_key]
        if r["stats"]:
            print(f"\n  Mejor combo: {best_combo_key}")
            print(f"  {fmt(r['stats'], r['score'])}")
            year_table(r["trades"], f"E-mejor ({best_combo_key})")

    # ── Resumen final de candidatos ────────────────────────────────────────────
    print("\n=== RESUMEN — candidatos DEPLOY (score >= 65) ===")
    all_results = {
        **{f"gap_down/{k}": v for k, v in regime_results.items()},
        **{f"ll/{k}": v for k, v in ll_regime_results.items()},
        **{f"gdsl_e/{k}": v for k, v in combo_results.items()},
    }
    deploy_candidates = [
        (k, v) for k, v in all_results.items()
        if v["stats"] and v["score"]["total"] >= 65
    ]
    deploy_candidates.sort(key=lambda x: x[1]["score"]["total"], reverse=True)

    if deploy_candidates:
        print(f"  {'Sistema':<40} {'n':>4}  {'PF':>5}  {'Score':>6}")
        print("  " + "-" * 65)
        for k, v in deploy_candidates:
            s, sc = v["stats"], v["score"]
            pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "  inf"
            print(f"  {k:<40} {s['n']:>4}  {pf_s:>5}  {sc['total']:>5.1f}")
    else:
        print("  Ninguno.")

    print()

    # ── F) Walk-forward validation: train 2016-2020, test 2021-2026 ─────────────
    print("\n=== F) Walk-forward validation (train=2016-20 / test=2021-26) ===")
    TRAIN_END = "2020-12-31"
    TEST_START = "2021-01-01"

    def split_trades(trades, cutoff, after=True):
        if after:
            return [t for t in trades if t["day"] > cutoff]
        else:
            return [t for t in trades if t["day"] <= cutoff]

    def sim_regime_split(sig_list, regime_fn, hold, split_date, after=True):
        filtered = [i for i in sig_list if regime_fn(i)]
        all_t = sim_fixed_hold(filtered, dates, opens, closes, n, hold)
        return split_trades(all_t, split_date, after)

    WF_CONFIGS = [
        ("ema200_and_yoy_h5",
         lambda i: (ema200_arr[i] is not None and yoy[i] is not None
                    and closes[i] > ema200_arr[i] and yoy[i] > 0),
         5),
        ("ema200_rsi2d_lt10_h5",
         lambda i: (ema200_arr[i] is not None and rsi2_arr[i] is not None
                    and closes[i] > ema200_arr[i] and rsi2_arr[i] < 10),
         5),
        ("atr_pct_lt05_ema200_yoy_h5",
         lambda i: (ema200_arr[i] is not None and yoy[i] is not None
                    and closes[i] > ema200_arr[i] and yoy[i] > 0
                    and atr_pct[i] is not None and atr_pct[i] < 0.5),
         5),
        ("atr_pct_lt03_ema200_yoy_h5",
         lambda i: (ema200_arr[i] is not None and yoy[i] is not None
                    and closes[i] > ema200_arr[i] and yoy[i] > 0
                    and atr_pct[i] is not None and atr_pct[i] < 0.3),
         5),
    ]

    print(f"  {'Config':<32} {'TRAIN n':>7}  {'TRAIN PF':>8}  {'TEST n':>7}  {'TEST PF':>8}  Verdict")
    print("  " + "-" * 85)
    for name, fn, hold in WF_CONFIGS:
        filtered = [i for i in signals if fn(i)]
        all_trades = sim_fixed_hold(filtered, dates, opens, closes, n, hold)
        train = split_trades(all_trades, TRAIN_END, after=False)
        test  = split_trades(all_trades, TEST_START, after=True)
        s_tr = stats(train)
        s_te = stats(test)
        pf_tr = f"{s_tr['pf']:.2f}" if s_tr and s_tr["pf"] != float("inf") else ("inf" if s_tr else "—")
        pf_te = f"{s_te['pf']:.2f}" if s_te and s_te["pf"] != float("inf") else ("inf" if s_te else "—")
        n_tr = s_tr["n"] if s_tr else 0
        n_te = s_te["n"] if s_te else 0
        # Verdict: hold si test PF >= 1.5 (señal de robustez out-of-sample)
        verdict = "OK" if (s_te and s_te["pf"] >= 1.5) else ("WEAK" if (s_te and s_te["pf"] >= 1.0) else "FAIL")
        print(f"  {name:<32} {n_tr:>7}  {pf_tr:>8}  {n_te:>7}  {pf_te:>8}  {verdict}")

    # ── G) Portfolio ll + gap_down (sin overlap) ───────────────────────────────
    print("\n=== G) Portfolio: gap_down_ema200_yoy + ll_excl_ema200_yoy (hold_5d) ===")
    # gap_down base (ema200+yoy, h5)
    gdsl_base = [i for i in signals
                 if ema200_arr[i] is not None and yoy[i] is not None
                 and closes[i] > ema200_arr[i] and yoy[i] > 0]
    # ll sin overlap con gap_down (ema200+yoy, h5)
    ll_excl_base = [i for i in ll_signals
                    if ema200_arr[i] is not None and yoy[i] is not None
                    and closes[i] > ema200_arr[i] and yoy[i] > 0
                    and i not in signal_set]

    gdsl_trades = sim_fixed_hold(gdsl_base, dates, opens, closes, n, 5)
    ll_excl_trades = sim_fixed_hold(ll_excl_base, dates, opens, closes, n, 5)

    s_gdsl = stats(gdsl_trades)
    s_ll   = stats(ll_excl_trades)

    # correlación de retornos entre los dos sistemas
    gdsl_map = {t["day"]: t["pnl"] for t in gdsl_trades}
    ll_map   = {t["day"]: t["pnl"] for t in ll_excl_trades}
    common_dates = set(gdsl_map) & set(ll_map)
    if len(common_dates) > 5:
        xs = [gdsl_map[d] for d in sorted(common_dates)]
        ys = [ll_map[d]   for d in sorted(common_dates)]
        xm = sum(xs)/len(xs); ym = sum(ys)/len(ys)
        num = sum((x-xm)*(y-ym) for x,y in zip(xs,ys))
        den = (sum((x-xm)**2 for x in xs) * sum((y-ym)**2 for y in ys)) ** 0.5
        corr = num/den if den else 0
    else:
        corr = 0

    pf_g = f"{s_gdsl['pf']:.2f}" if s_gdsl and s_gdsl["pf"] != float("inf") else "inf"
    pf_l = f"{s_ll['pf']:.2f}"   if s_ll   and s_ll["pf"]   != float("inf") else "inf"
    print(f"  gap_down (ema200+yoy): n={s_gdsl['n'] if s_gdsl else 0}  PF={pf_g}  "
          f"hit={s_gdsl['hit']:.1f}%  score={horizon_score(s_gdsl)['total']:.1f}" if s_gdsl else "  gap_down: n=0")
    print(f"  ll_excl  (ema200+yoy): n={s_ll['n'] if s_ll else 0}  PF={pf_l}  "
          f"hit={s_ll['hit']:.1f}%  score={horizon_score(s_ll)['total']:.1f}" if s_ll else "  ll_excl: n=0")
    print(f"  Correlacion dias solapados (n={len(common_dates)}): r={corr:.3f}")
    print(f"  => Portfolio complementario: {'SI' if abs(corr) < 0.3 else 'NO (alta correlacion)'}")
    print()

    # ── H) MFE/MAE por día — GDSL ema200_and_yoy (n=144) ────────────────────────
    print("\n=== H) MFE/MAE día a día — GDSL ema200+yoy (n=144) ===")

    base_signals_h = [i for i in signals
                      if ema200_arr[i] is not None and yoy[i] is not None
                      and closes[i] > ema200_arr[i] and yoy[i] > 0]

    # Para cada señal, seguimos el trade día a día: D+1 (entry) a D+5 (exit)
    day_rets  = [[] for _ in range(6)]   # d=0..5: retorno vs entry en el cierre del dia D+d
    peak_days = []                         # qué día dentro del hold tuvo el retorno máximo
    worst_days = []                        # qué día tuvo el retorno mínimo (MAE)
    mfe_vals  = []                         # máximo retorno favorable en el hold
    mae_vals  = []                         # máximo retorno adverso en el hold (positivo = pérdida)

    for sig_i in base_signals_h:
        entry_i = sig_i + 1
        if entry_i >= n:
            continue
        entry_px = opens[entry_i]
        if entry_px <= 0:
            continue

        rets = []
        for d in range(0, 6):  # d=0: open entry (ref=0), d=1-5: closes
            idx = entry_i + d
            if idx >= n:
                break
            if d == 0:
                rets.append(0.0)  # entry reference
            else:
                rets.append(closes[idx] / entry_px - 1)

        if len(rets) < 6:
            continue

        for d in range(6):
            day_rets[d].append(rets[d])

        peak_d = max(range(1, 6), key=lambda x: rets[x])
        worst_d = min(range(1, 6), key=lambda x: rets[x])
        peak_days.append(peak_d)
        worst_days.append(worst_d)
        mfe_vals.append(max(rets[1:]))
        mae_vals.append(min(rets[1:]))

    print(f"\n  Evolución media del retorno vs open_entry (n={len(mfe_vals)}):")
    print(f"  {'Día':>5}  {'Media ret':>10}  {'Win%':>6}  {'Mediana':>9}  {'P25':>8}  {'P75':>8}")
    print("  " + "-" * 56)
    for d in range(1, 6):
        rr = day_rets[d]
        if not rr:
            continue
        mean_r  = sum(rr) / len(rr)
        win_pct = 100 * sum(1 for r in rr if r > 0) / len(rr)
        sorted_r = sorted(rr)
        mid = len(sorted_r) // 2
        median = sorted_r[mid] if len(sorted_r) % 2 == 1 else (sorted_r[mid-1] + sorted_r[mid]) / 2
        p25 = sorted_r[len(sorted_r) // 4]
        p75 = sorted_r[3 * len(sorted_r) // 4]
        print(f"  D+{d:>2}   {100*mean_r:>+9.2f}%  {win_pct:>5.1f}%  {100*median:>+8.2f}%  "
              f"{100*p25:>+7.2f}%  {100*p75:>+7.2f}%")

    if mfe_vals:
        mean_mfe = sum(mfe_vals) / len(mfe_vals)
        mean_mae = sum(mae_vals) / len(mae_vals)
        print(f"\n  MFE medio: {100*mean_mfe:+.2f}%  |  MAE medio: {100*mean_mae:+.2f}%")
        print(f"  Ratio MFE/|MAE|: {mean_mfe / abs(mean_mae):.2f}x")

    if peak_days:
        from collections import Counter
        peak_dist  = Counter(peak_days)
        worst_dist = Counter(worst_days)
        print(f"\n  Día del pico máximo (D+N):  " +
              "  ".join(f"D+{d}={peak_dist.get(d,0)}" for d in range(1,6)))
        print(f"  Día del peor retorno (D+N): " +
              "  ".join(f"D+{d}={worst_dist.get(d,0)}" for d in range(1,6)))

    # Dynamic exit: FPC (first profitable close) vs fixed 5d
    print(f"\n  Dynamic exit vs fixed hold:")
    fpc_trades = []
    fixed5_trades = []
    for sig_i in base_signals_h:
        entry_i = sig_i + 1
        if entry_i >= n:
            continue
        ep = opens[entry_i]
        if ep <= 0:
            continue
        # FPC: primer día (D+1..D+5) donde close > entry
        fpc_exit = None
        for d in range(1, 6):
            idx = entry_i + d
            if idx >= n:
                break
            if closes[idx] > ep:
                fpc_exit = closes[idx] / ep - 1
                break
        if fpc_exit is None:  # nunca fue positivo → salida al cierre D+5
            exit_i = entry_i + 5
            if exit_i < n:
                fpc_exit = closes[exit_i] / ep - 1
        if fpc_exit is not None:
            fpc_trades.append({"day": dates[entry_i], "pnl": fpc_exit})
        # Fixed 5
        exit_i5 = entry_i + 5
        if exit_i5 < n:
            fixed5_trades.append({"day": dates[entry_i], "pnl": closes[exit_i5] / ep - 1})

    s_fpc   = stats(fpc_trades)
    s_fix5  = stats(fixed5_trades)
    sc_fpc  = horizon_score(s_fpc)
    sc_fix5 = horizon_score(s_fix5)
    if s_fpc and s_fix5:
        pf_fpc  = f"{s_fpc['pf']:.2f}"  if s_fpc['pf']  != float("inf") else "inf"
        pf_fix5 = f"{s_fix5['pf']:.2f}" if s_fix5['pf'] != float("inf") else "inf"
        print(f"  FPC (first profitable close): n={s_fpc['n']:>4}  "
              f"hit={s_fpc['hit']:>5.1f}%  PF={pf_fpc:>5}  "
              f"ret={100*s_fpc['pnl']:>+7.1f}pp  score={sc_fpc['total']:.1f}")
        print(f"  Fixed hold=5d (ema200+yoy):   n={s_fix5['n']:>4}  "
              f"hit={s_fix5['hit']:>5.1f}%  PF={pf_fix5:>5}  "
              f"ret={100*s_fix5['pnl']:>+7.1f}pp  score={sc_fix5['total']:.1f}")

    if args.json:
        # Serializar solo los resúmenes (no los trades completos)
        out = {k: {"stats": v["stats"], "score": v["score"]}
               for k, v in results.items() if v["stats"] is not None}
        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
