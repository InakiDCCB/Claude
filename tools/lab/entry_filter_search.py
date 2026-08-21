"""Dos pedidos del usuario tras el cierre negativo de exit-redesign (S4/LWR no se salvan ajustando
SL/TP con slippage realista):

1. **Filtro de ENTRADA** (no de gestión post-entrada): ¿algo conocido AL MOMENTO de la señal --
   hora del día, rvol, pendiente de VWAP, RSI14, ganancia del día hasta ahora, y features propios
   de cada sistema (profundidad del sweep en S4, tamaño de la mecha/rango en LWR) -- distingue
   ganadoras de perdedoras lo suficiente como para filtrar entradas, aunque elimine señales?
2. **TP=SL (R:R 1:1)**: con hit rate ~65%, ¿un TP igual al SL da PF>1 una vez que se re-mide el
   hit rate REAL con ese nuevo TP (no el 65% actual, que es específico de TP=0.5R) y con slippage?

TODO con slippage=$0.02 (lección de la sesión anterior: sin esto los números mienten) sobre el SL
actual de cada sistema (no el SL ajustado, que ya se descartó). Full 2016-2026 vs recent 2023-2026.

Uso: python entry_filter_search.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from backtest import Day, sweep_reclaim, wick_reversal, ENTRY_MIN, ENTRY_MAX, FORCED  # noqa: E402
from s4_lwr_path_analysis import load_days, record_path, resolve  # noqa: E402

RECENT_YEARS = {"2023", "2024", "2025", "2026"}
SLIP = 0.02


def resolve_slip(path, sl_r, tp_r, risk, slip_dollars=SLIP):
    slip_r = slip_dollars / risk
    for offset, o_r, l_r, h_r, c_r in path:
        if l_r <= -sl_r:
            base = o_r if o_r <= -sl_r else -sl_r
            return base - slip_r
        if h_r >= tp_r:
            base = o_r if o_r >= tp_r else tp_r
            return base - slip_r
    return path[-1][4]


def pf_of(rets):
    gw = sum(r for r in rets if r > 0)
    gl = -sum(r for r in rets if r <= 0)
    return gw / gl if gl > 0 else float("inf")


def scan_with_features(days, signal_fn, c4, system):
    trades = []
    for day in days:
        pos_until = -1
        consec_sl = 0
        for i in range(day.n - 1):
            e = i + 1
            if not (ENTRY_MIN <= e <= ENTRY_MAX) or e <= pos_until:
                continue
            if c4 and consec_sl >= 2:
                break
            sig = signal_fn(day, i)
            if sig is None:
                continue
            entry = day.o[e]
            if "sl_abs" not in sig:
                continue
            sl = round(sig["sl_abs"], 2)
            if sl >= entry:
                continue
            risk = entry - sl
            tp = sig["tp"]
            tp_r = tp[1] if tp[0] == "r" else (tp[1] - entry) / risk
            path = record_path(day, e, entry, risk)
            _, offset, exit_r = resolve(path, 1.0, tp_r)

            rng = day.h[i] - day.l[i]
            feat = {
                "time_of_day": i,  # minutos desde apertura (bar index ~ minuto)
                "rvol": (day.v[i] / day.avgv5[i]) if day.avgv5[i] else None,
                "vwap_slope": day.slope30[i],
                "rsi14": day.rsi14[i],
                "day_gain_so_far": (day.c[i] - day.o[0]) / day.o[0] if day.o[0] else None,
                "above_vwap": (day.c[i] > day.vwap[i]) if day.vwap[i] else None,
            }
            if system == "S4":
                feat["sweep_depth"] = (day.prev_low[i] - day.l[i]) if day.prev_low[i] else None
            else:
                lower_wick = min(day.o[i], day.c[i]) - day.l[i]
                feat["wick_ratio"] = lower_wick / rng if rng > 0 else None
                feat["range_size"] = rng

            trades.append({"day": day.date, "risk": risk, "tp_r": tp_r, "path": path,
                           "exit_r": exit_r, "feat": feat})
            pos_until = e + offset
            consec_sl = consec_sl + 1 if exit_r <= 0 else 0
    return trades


def bucket3(vals_with_idx):
    """vals_with_idx: [(valor, idx_original)] -> dict idx->bucket usando terciles."""
    xs = sorted(v for v, _ in vals_with_idx if v is not None)
    n = len(xs)
    if n < 30:
        return {}
    lo, hi = xs[n // 3], xs[2 * n // 3]
    out = {}
    for v, idx in vals_with_idx:
        if v is None:
            continue
        out[idx] = "low" if v < lo else ("high" if v > hi else "mid")
    return out


def analyze_feature(name, trades, feat_key, current_sl=1.0, buckets_override=None):
    if buckets_override:
        bmap = {i: buckets_override(t["feat"].get(feat_key)) for i, t in enumerate(trades)}
    else:
        vals = [(t["feat"].get(feat_key), i) for i, t in enumerate(trades)]
        bmap = bucket3(vals)
    if not bmap:
        print(f"  {feat_key}: sin datos suficientes")
        return
    print(f"\n  -- {feat_key} --")
    for era_name, era_years in (("full", None), ("recent", RECENT_YEARS)):
        by_bucket = {}
        for i, t in enumerate(trades):
            if i not in bmap:
                continue
            if era_years is not None and t["day"][:4] not in era_years:
                continue
            rets_slip = resolve_slip(t["path"], current_sl, t["tp_r"], t["risk"])
            by_bucket.setdefault(bmap[i], []).append(rets_slip)
        line = f"    {era_name:<8}"
        for b in ("low", "mid", "high"):
            rets = by_bucket.get(b, [])
            if not rets:
                line += f" {b}=n/a"
                continue
            pf = pf_of(rets)
            pf_s = f"{pf:.2f}" if pf != float("inf") else "inf"
            line += f" {b}(n={len(rets)})=PF{pf_s}"
        print(line)


def main():
    print("Cargando 10 años...")
    days = load_days(range(2016, 2027))

    print("\nEscaneando S4 SWP con features de entrada...")
    s4 = scan_with_features(days, sweep_reclaim(("r", 0.5))(), c4=True, system="S4")
    print(f"{len(s4)} trades.")
    base_rets = [resolve_slip(t["path"], 1.0, t["tp_r"], t["risk"]) for t in s4]
    print(f"BASELINE S4 (SL=1.0R TP=0.5R, slip=$0.02): PF={pf_of(base_rets):.2f}")
    for feat_key in ("time_of_day", "rvol", "vwap_slope", "rsi14", "day_gain_so_far", "sweep_depth"):
        analyze_feature("S4", s4, feat_key)
    print("\n  -- above_vwap (binario) --")
    for era_name, era_years in (("full", None), ("recent", RECENT_YEARS)):
        by_b = {True: [], False: []}
        for t in s4:
            if era_years is not None and t["day"][:4] not in era_years:
                continue
            if t["feat"]["above_vwap"] is None:
                continue
            by_b[t["feat"]["above_vwap"]].append(resolve_slip(t["path"], 1.0, t["tp_r"], t["risk"]))
        line = f"    {era_name:<8}"
        for k in (True, False):
            rets = by_b[k]
            pf = pf_of(rets) if rets else None
            pf_s = f"{pf:.2f}" if pf and pf != float("inf") else "n/a"
            line += f" above_vwap={k}(n={len(rets)})=PF{pf_s}"
        print(line)

    print("\n\nEscaneando LWR con features de entrada...")
    lwr = scan_with_features(days, wick_reversal(("r", 0.5), wick_thresh=0.60, min_rvol=3.0)(), c4=False, system="LWR")
    print(f"{len(lwr)} trades.")
    base_rets = [resolve_slip(t["path"], 1.0, t["tp_r"], t["risk"]) for t in lwr]
    print(f"BASELINE LWR (SL=1.0R TP=0.5R, slip=$0.02): PF={pf_of(base_rets):.2f}")
    for feat_key in ("time_of_day", "rvol", "vwap_slope", "rsi14", "day_gain_so_far", "wick_ratio", "range_size"):
        analyze_feature("LWR", lwr, feat_key)

    # ============================================================
    # 2. TP = SL (R:R 1:1) con slippage, SL actual de cada sistema
    # ============================================================
    print("\n\n" + "#" * 70 + "\n# TP = SL (R:R 1:1) -- re-medido con slippage\n" + "#" * 70)
    for name, trades in (("S4 SWP", s4), ("LWR", lwr)):
        print(f"\n=== {name} ===")
        for tp_r in (0.5, 0.8, 1.0, 1.2):
            for slip in (0.0, 0.01, 0.02):
                rets = [resolve_slip(t["path"], 1.0, tp_r, t["risk"], slip) for t in trades]
                pf = pf_of(rets)
                hit = sum(1 for r in rets if r > 0) / len(rets) * 100
                pf_s = f"{pf:.2f}" if pf != float("inf") else "inf"
                print(f"  TP={tp_r}R SL=1.0R slip=${slip:.2f}: n={len(rets)} hit={hit:.1f}% "
                      f"PF={pf_s} pnl_total={sum(rets):+.1f}R")
        # año-por-año para TP=1.0R (SL=SL, "TP=SL" literal) con slip=$0.02
        print(f"\n  Año-por-año TP=1.0R=SL, slip=$0.02:")
        by_year = {}
        for t in trades:
            by_year.setdefault(t["day"][:4], []).append(t)
        for year in sorted(by_year):
            rets_y = [resolve_slip(t["path"], 1.0, 1.0, t["risk"], 0.02) for t in by_year[year]]
            pf_y = pf_of(rets_y)
            pf_s = f"{pf_y:.2f}" if pf_y != float("inf") else "inf"
            print(f"    {year}: n={len(rets_y):>4} PF={pf_s:>5} pnl={sum(rets_y):+7.1f}R")


if __name__ == "__main__":
    main()
