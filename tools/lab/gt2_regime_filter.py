"""
tools/lab/gt2_regime_filter.py
Mejora de gt_closelow_v2 (LIVE, hold=3d) mediante filtros de régimen y señales situacionales.

Pregunta central: ¿puede filtrarse gt_closelow_v2 para mejorar su PF=2.07?
Candidatos explorados:
  1. gap_up_sin_llenar como contra-indicador (bearish → evitar longs de gt2 ese día)
  2. hh_agotamiento como contra-indicador (higher_high + close<mid → bearish)
  3. Régimen alcista (ema200, yoy) como reforzador
  4. RSI2_daily como reforzador (sobreventa extrema)
  5. Combinaciones de lo anterior

Referencia: gt_closelow_v2 sin filtro: n=219, PF=2.07, score=60.6 PAPER (LIVE desde v3.1.14)

Uso:
  uv run python tools/lab/gt2_regime_filter.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest import stats
from _score_common import horizon_score, wilson_lb

DATA = Path(__file__).parent.parent / "data" / "qqq_daily_full.json"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ── indicadores ───────────────────────────────────────────────────────────────

def ema(vals, n):
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    s = sum(vals[:n]) / n
    out[n-1] = s
    k = 2 / (n + 1)
    for i in range(n, len(vals)):
        s = vals[i] * k + s * (1 - k)
        out[i] = s
    return out


def wilder_rsi2(closes):
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
        max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        for i in range(1, m)
    ]
    atr = [None] * m
    if m <= n:
        return atr
    atr[n] = sum(trs[1:n+1]) / n
    for i in range(n+1, m):
        atr[i] = (atr[i-1] * (n-1) + trs[i]) / n
    return atr


def atr_pct_60(atr_arr):
    out = [None] * len(atr_arr)
    for i in range(len(atr_arr)):
        if atr_arr[i] is None:
            continue
        start = max(0, i - 59)
        vals = [v for v in atr_arr[start:i+1] if v is not None]
        if len(vals) < 5:
            continue
        out[i] = sum(1 for v in vals if v <= atr_arr[i]) / len(vals)
    return out


# ── señales situacionales ─────────────────────────────────────────────────────

def gap_up_sin_llenar(opens, highs, lows, closes):
    """open > high[D-1] AND close > high[D-1] — sesgo bearish para D+1."""
    s = set()
    for i in range(1, len(closes)):
        if opens[i] > highs[i-1] and closes[i] > highs[i-1]:
            s.add(i)
    return s


def hh_agotamiento(highs, lows, closes):
    """higher_high + close < midpoint — sesgo bearish para D+1."""
    s = set()
    for i in range(1, len(closes)):
        h, l, c = highs[i], lows[i], closes[i]
        if h > highs[i-1] and l > lows[i-1] and c < (h + l) / 2:
            s.add(i)
    return s


def gap_down_sin_llenar_ema200_yoy(opens, lows, closes, ema200, yoy):
    """GDSL signal (v1): gap abajo exterior + ema200 + yoy."""
    s = set()
    for i in range(1, len(closes)):
        if opens[i] < lows[i-1] and closes[i] < lows[i-1]:
            if ema200[i] is not None and closes[i] > ema200[i]:
                if yoy[i] is not None and yoy[i] > 0:
                    s.add(i)
    return s


# ── simulación gt_closelow_v2 ─────────────────────────────────────────────────

def sim_gt2(dates, opens, highs, lows, closes, n_total, hold=3,
            exclude_days: set | None = None, require_days: set | None = None):
    """
    Replica gt_closelow_v2 (clr[D-1] < 0.1, hold=3d).
    exclude_days: set de índices D donde la señal es bloqueada.
    require_days: set de índices D donde la señal DEBE estar para entrar.
    """
    clr = [(closes[i] - lows[i]) / (highs[i] - lows[i])
           if highs[i] > lows[i] else 0.5
           for i in range(n_total)]
    trades = []
    in_trade_until = -1
    for i in range(1, n_total):
        if i <= in_trade_until:
            continue
        if clr[i-1] < 0.1:
            # señal en D = i-1, entrada en D+1 = i
            sig_day = i - 1
            if exclude_days and sig_day in exclude_days:
                continue
            if require_days and sig_day not in require_days:
                continue
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


def fmt(s, sc, label=""):
    if s is None or s["n"] == 0:
        return f"{label:<30} n=0"
    wlb = wilson_lb(s["w"], s["n"])
    wlb_s = f"{wlb*100:.1f}%" if wlb else "?"
    pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "  inf"
    return (f"{label:<35} n={s['n']:>4}  hit={s['hit']:>5.1f}%(wlb {wlb_s})  "
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
            pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "  inf"
            print(f"  {yr:<6} {s['n']:>4}  {s['hit']:>5.1f}%  {pf_s:>5}  "
                  f"{100*s['pnl']:>+9.1f}pp")
    print()


def main():
    raw = json.loads(DATA.read_text())
    raw.sort(key=lambda b: b["t"])
    dates  = [b["t"][:10] for b in raw]
    opens  = [float(b["o"]) for b in raw]
    highs  = [float(b["h"]) for b in raw]
    lows   = [float(b["l"]) for b in raw]
    closes = [float(b["c"]) for b in raw]
    vols   = [float(b.get("v", 0)) for b in raw]
    n      = len(dates)

    # Indicadores
    ema200_arr = ema(closes, 200)
    ema50_arr  = ema(closes, 50)
    rsi2_arr   = wilder_rsi2(closes)
    atr14_arr  = wilder_atr(highs, lows, closes, 14)
    apct_arr   = atr_pct_60(atr14_arr)
    yoy        = [None] * n
    for i in range(252, n):
        yoy[i] = closes[i] / closes[i-252] - 1

    # Señales situacionales (calculadas sobre D = signal_day)
    gus_set  = gap_up_sin_llenar(opens, highs, lows, closes)  # bearish D+1
    hha_set  = hh_agotamiento(highs, lows, closes)            # bearish D+1
    gdsl_set = gap_down_sin_llenar_ema200_yoy(opens, lows, closes, ema200_arr, yoy)

    print(f"QQQ diario: {n} sesiones ({dates[0]} -> {dates[-1]})\n")
    print(f"gap_up_sin_llenar:  {len(gus_set)} dias ({100*len(gus_set)/n:.1f}%)")
    print(f"hh_agotamiento:     {len(hha_set)} dias ({100*len(hha_set)/n:.1f}%)")
    print(f"gdsl_v1:            {len(gdsl_set)} dias ({100*len(gdsl_set)/n:.1f}%)\n")

    # ── Base: gt_closelow_v2 sin filtro ──────────────────────────────────────
    print("=== BASE: gt_closelow_v2 (clr<0.1, hold=3d) ===")
    base = sim_gt2(dates, opens, highs, lows, closes, n, hold=3)
    s_base = stats(base)
    sc_base = horizon_score(s_base)
    print(fmt(s_base, sc_base, "sin_filtro"))
    print()

    # ── A) Filtros de exclusión (señales bearish el día de la señal gt2) ─────
    print("=== A) Exclusiones — días con señal bearish simultánea ===")
    print(f"  {'Filtro':<35} {'n':>4}  {'Hit%':>6}  {'PF':>5}  {'ret':>8}  {'mLL':>4}  "
          f"{'Score':>6}  Veredicto")
    print("  " + "-" * 88)

    EXCLUSIONS = [
        ("excl_gap_up_sin_llenar",     gus_set),
        ("excl_hh_agotamiento",        hha_set),
        ("excl_gus_OR_hha",            gus_set | hha_set),
        ("excl_gdsl_v1 (raros combo)", gdsl_set),
    ]
    best_excl = None
    best_excl_sc = -1
    for name, excl_set in EXCLUSIONS:
        t = sim_gt2(dates, opens, highs, lows, closes, n, hold=3, exclude_days=excl_set)
        s  = stats(t)
        sc = horizon_score(s)
        if s:
            pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "  inf"
            star = " *" if sc["total"] > sc_base["total"] else ""
            print(f"  {name:<35} {s['n']:>4}  {s['hit']:>5.1f}%  "
                  f"{pf_s:>5}  {100*s['pnl']:>+7.1f}pp  {s['mll']:>4}  "
                  f"{sc['total']:>5.1f}  {sc['verdict']}{star}")
            if sc["total"] > best_excl_sc:
                best_excl_sc = sc["total"]
                best_excl = (name, t, s, sc)
        else:
            print(f"  {name:<35} n=0")

    if best_excl:
        print(f"\n  Mejor exclusión: {best_excl[0]} (delta vs base: "
              f"{best_excl[3]['total']-sc_base['total']:+.1f} score, "
              f"{best_excl[2]['pf']-s_base['pf']:+.2f} PF)")

    # ── B) Filtros de régimen alcista (reforzadores de gt2) ──────────────────
    print("\n=== B) Régimen alcista como reforzador de gt2 ===")
    print(f"  {'Filtro':<35} {'n':>4}  {'Hit%':>6}  {'PF':>5}  {'ret':>8}  {'mLL':>4}  "
          f"{'Score':>6}  Veredicto")
    print("  " + "-" * 88)

    REFUERZOS = [
        ("base",               None, None),
        ("ema200_above",       lambda i: ema200_arr[i] is not None and closes[i] > ema200_arr[i], None),
        ("ema200_and_yoy",     lambda i: (ema200_arr[i] is not None and yoy[i] is not None
                                          and closes[i] > ema200_arr[i] and yoy[i] > 0), None),
        ("rsi2d_lt10",         lambda i: rsi2_arr[i] is not None and rsi2_arr[i] < 10, None),
        ("ema200_rsi2d_lt10",  lambda i: (ema200_arr[i] is not None and rsi2_arr[i] is not None
                                          and closes[i] > ema200_arr[i] and rsi2_arr[i] < 10), None),
        ("atr_pct_lt50",       lambda i: apct_arr[i] is not None and apct_arr[i] < 0.50, None),
        # combos con excl gus
        ("ema200_excl_gus",    lambda i: ema200_arr[i] is not None and closes[i] > ema200_arr[i],
                               gus_set),
        ("ema200_yoy_excl_gus",lambda i: (ema200_arr[i] is not None and yoy[i] is not None
                                           and closes[i] > ema200_arr[i] and yoy[i] > 0),
                               gus_set),
        ("rsi2d<10_excl_gus",  lambda i: (ema200_arr[i] is not None and rsi2_arr[i] is not None
                                           and closes[i] > ema200_arr[i] and rsi2_arr[i] < 10),
                               gus_set),
    ]

    best_refuerzo = None
    best_refuerzo_sc = -1
    refuerzo_results = []
    for name, req_fn, excl_set in REFUERZOS:
        if req_fn is None and excl_set is None:
            t = base
        else:
            req_set = {i for i in range(n) if req_fn(i)} if req_fn else None
            t = sim_gt2(dates, opens, highs, lows, closes, n, hold=3,
                        exclude_days=excl_set, require_days=req_set)
        s  = stats(t)
        sc = horizon_score(s)
        refuerzo_results.append((name, t, s, sc))
        if s:
            pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "  inf"
            star = " *" if sc["total"] > sc_base["total"] else ""
            print(f"  {name:<35} {s['n']:>4}  {s['hit']:>5.1f}%  "
                  f"{pf_s:>5}  {100*s['pnl']:>+7.1f}pp  {s['mll']:>4}  "
                  f"{sc['total']:>5.1f}  {sc['verdict']}{star}")
            if sc["total"] > best_refuerzo_sc and s["n"] >= 20:
                best_refuerzo_sc = sc["total"]
                best_refuerzo = (name, t, s, sc)
        else:
            print(f"  {name:<35} n=0")

    # ── C) Walk-forward mejores configuraciones ───────────────────────────────
    print("\n=== C) Walk-forward (train=2016-20, test=2021-26) ===")
    TRAIN_END, TEST_START = "2020-12-31", "2021-01-01"

    def split(trades, cutoff, after=True):
        return [t for t in trades if (t["day"] > cutoff) == after]

    # Base
    tr_base = split(base, TRAIN_END, False)
    te_base = split(base, TEST_START, True)
    s_tr = stats(tr_base); s_te = stats(te_base)
    pf_tr = f"{s_tr['pf']:.2f}" if s_tr else "—"
    pf_te = f"{s_te['pf']:.2f}" if s_te else "—"
    print(f"  {'base':<35} TRAIN n={s_tr['n'] if s_tr else 0} PF={pf_tr}  "
          f"TEST n={s_te['n'] if s_te else 0} PF={pf_te}")

    for name, t, s, sc in refuerzo_results[1:]:  # skip base
        if not s or s["n"] < 15:
            continue
        tr_t = split(t, TRAIN_END, False)
        te_t = split(t, TEST_START, True)
        s_tr = stats(tr_t); s_te = stats(te_t)
        if not s_tr or not s_te:
            continue
        pf_tr = f"{s_tr['pf']:.2f}"; pf_te = f"{s_te['pf']:.2f}"
        v = "OK" if s_te["pf"] >= 1.5 else "WEAK"
        star = " *" if sc["total"] > sc_base["total"] else ""
        print(f"  {name:<35} TRAIN n={s_tr['n']:>3} PF={pf_tr}  "
              f"TEST n={s_te['n']:>3} PF={pf_te}  {v}{star}")

    # ── D) Detalles mejores configuraciones ───────────────────────────────────
    if best_refuerzo and best_refuerzo[3]["total"] > sc_base["total"]:
        name, t, s, sc = best_refuerzo
        print(f"\n=== D) Año a año — mejor refuerzo ({name}) ===")
        print(fmt(s, sc, name))
        year_table(t, name)

    # ── E) Días consecutivos bajistas antes del gt2 ───────────────────────────
    print("\n=== E) Días consecutivos bajistas previos al gt2 ===")

    def sim_gt2_consec(dates, opens, highs, lows, closes, n_total, hold, min_dn, max_dn=None):
        """gt2 filtrado por N días consecutivos bajistas ANTES de la señal."""
        clr = [(closes[i] - lows[i]) / (highs[i] - lows[i])
               if highs[i] > lows[i] else 0.5
               for i in range(n_total)]
        # Días bajistas: close[i] < close[i-1]
        consec_dn = [0] * n_total
        for i in range(1, n_total):
            if closes[i] < closes[i-1]:
                consec_dn[i] = consec_dn[i-1] + 1
            else:
                consec_dn[i] = 0

        trades = []
        in_trade_until = -1
        for i in range(1, n_total):
            if i <= in_trade_until:
                continue
            if clr[i-1] < 0.1:
                sig_day = i - 1
                dn = consec_dn[sig_day]
                if dn < min_dn:
                    continue
                if max_dn is not None and dn > max_dn:
                    continue
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

    print(f"  {'Filtro':<30} {'n':>4}  {'Hit%':>6}  {'PF':>5}  {'ret':>8}  "
          f"{'mLL':>4}  {'Score':>6}  Veredicto")
    print("  " + "-" * 78)

    for min_dn, max_dn, label in [
        (0, None, "todos (base)"),
        (1, None, ">=1 día bajista"),
        (2, None, ">=2 días bajistas"),
        (3, None, ">=3 días bajistas"),
        (4, None, ">=4 días bajistas"),
        (1, 2,    "1-2 días bajistas"),
        (2, 4,    "2-4 días bajistas"),
    ]:
        t = sim_gt2_consec(dates, opens, highs, lows, closes, n, 3, min_dn, max_dn)
        s  = stats(t)
        sc = horizon_score(s)
        if s:
            pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "  inf"
            star = " *" if sc["total"] > sc_base["total"] else ""
            print(f"  {label:<30} {s['n']:>4}  {s['hit']:>5.1f}%  "
                  f"{pf_s:>5}  {100*s['pnl']:>+7.1f}pp  {s['mll']:>4}  "
                  f"{sc['total']:>5.1f}  {sc['verdict']}{star}")
        else:
            print(f"  {label:<30} n=0")

    # ── F) GDSL disparado el mismo día que gt2 (señal doble) ─────────────────
    print("\n=== F) Co-señal GDSL+gt2 el mismo día (confirmación doble) ===")
    # clr signal day = i-1 en sim_gt2
    # gdsl signal day = i en compute_signals
    # BOTH fire on the same day D means:
    #   - clr(D) < 0.1 (para gt2, entry D+1)
    #   - gdsl fires on D (open_D < low_{D-1} AND close_D < low_{D-1} + ema200 + yoy)
    # Note: if gdsl fires on D AND clr(D)<0.1, that's a rare but potentially strong co-signal

    clr_arr = [(closes[i] - lows[i]) / (highs[i] - lows[i])
               if highs[i] > lows[i] else 0.5
               for i in range(n)]
    co_signal_days = {i for i in gdsl_set if clr_arr[i] < 0.1}
    gt2_only_days  = set()
    for i in range(1, n):
        if clr_arr[i-1] < 0.1 and (i-1) not in gdsl_set:
            gt2_only_days.add(i-1)

    print(f"  GDSL ∩ gt2 (co-señal): {len(co_signal_days)} días ({100*len(co_signal_days)/n:.1f}%)")
    print(f"  gt2 solo (sin GDSL):   {len(gt2_only_days)} días")

    # Trades de la co-señal (entry D+1, hold=3)
    co_trades = []
    in_trade_until = -1
    for i in range(1, n):
        if i <= in_trade_until:
            continue
        sig_day = i - 1
        if sig_day in co_signal_days:
            entry_i = i
            exit_i  = i + 2  # hold=3d (entry + 2 more days)
            if exit_i >= n:
                break
            entry = opens[entry_i]
            exit_ = closes[exit_i]
            if entry > 0:
                co_trades.append({"day": dates[entry_i], "pnl": exit_ / entry - 1})
            in_trade_until = exit_i

    s_co = stats(co_trades)
    sc_co = horizon_score(s_co)
    if s_co:
        print(f"\n  {fmt(s_co, sc_co, 'co-señal GDSL+gt2')}")
        year_table(co_trades, "co-señal GDSL+gt2")
    else:
        print("  co-señal: sin trades (no hubo overlap suficiente)")

    print("\n=== RESUMEN ===")
    print(f"  base:    {fmt(s_base, sc_base, 'gt2_sin_filtro')}")
    if best_excl and best_excl[3]["total"] > sc_base["total"]:
        print(f"  excl:    {fmt(best_excl[2], best_excl[3], best_excl[0])}")
    if best_refuerzo and best_refuerzo[3]["total"] > sc_base["total"]:
        print(f"  refuerzo:{fmt(best_refuerzo[2], best_refuerzo[3], best_refuerzo[0])}")
    else:
        print("  => Ningún filtro mejora el score de la base de forma significativa.")
    print()


if __name__ == "__main__":
    main()
