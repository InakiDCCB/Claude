"""Tratamiento completo de TD9S (S9P short + RSI14(5m)>=60, config LIVE de `td_shadow.py`), espejo
del que mató a S4/LWR: MFE/MAE, grid de SL/TP con slippage realista, filtro de entrada por
contexto, y TP=SL. Usa el mismo mecanismo de fill+resolución 1-min de `td_backtest.py::simulate`
(entry=close del bloque 5-min de la señal, ventana de fill de 3 barras, forced-close ~15:55) para
ser consistente con el PF=0.87 pool / 0.90 reciente ya reportado (shadow_full_history_check.py).

Truco para reusar toda la matemática LONG existente en un sistema SHORT: se graba el camino
"espejado" (mirror_r = (entry - precio)/risk en vez de (precio-entry)/risk) -- con esa transformación
un short se comporta matemáticamente igual que un long, así que TODA la maquinaria de MFE/MAE/grid/
slippage/filtros ya construida para S4/LWR se reutiliza sin cambios de lógica.

Uso: python td9s_full_treatment.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from td_backtest import rsi as td_rsi, atr as td_atr, td_signals  # noqa: E402

DATA_1MIN_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"
RECENT_YEARS = {"2023", "2024", "2025", "2026"}
FORCED_CUTOFF_FROM_END = 5  # td_backtest.py: cutoff = len(bs) - 5 (~15:55)


def load_bydate(years):
    bydate = {}
    for year in years:
        path = DATA_1MIN_DIR / f"{year}.csv"
        if not path.exists():
            continue
        with path.open() as f:
            for row in csv.DictReader(f):
                date = row["t"][:10]
                bydate.setdefault(date, []).append(
                    {"t": row["t"], "o": float(row["o"]), "h": float(row["h"]),
                     "l": float(row["l"]), "c": float(row["c"]), "v": float(row["v"])})
    return {d: bars for d, bars in bydate.items() if len(bars) >= 300}


def build_5min_blocks(bydate):
    blocks = []
    for d in sorted(bydate):
        bs = bydate[d]
        for i0 in range(0, len(bs), 5):
            grp = bs[i0:i0 + 5]
            blocks.append({"d": d, "i1": min(i0 + len(grp) - 1, len(bs) - 1),
                           "o": grp[0]["o"], "h": max(x["h"] for x in grp),
                           "l": min(x["l"] for x in grp), "c": grp[-1]["c"]})
    return blocks


def find_fill_and_record_path(bydate, day, i1, entry_px):
    """Replica el fill-search de td_backtest.py::simulate (SHORT: fillea si el HIGH de una de las
    3 barras siguientes toca entry_px) y graba el camino MIRROR-R (short) desde el fill hasta
    forced-close (~15:55), SIN truncar en ningun SL/TP -- permite re-escanear despues."""
    bs = bydate[day]
    fi = None
    for j in range(i1 + 1, min(i1 + 4, len(bs))):
        if bs[j]["h"] >= entry_px:
            fi = j
            break
    if fi is None:
        return None
    cutoff = len(bs) - FORCED_CUTOFF_FROM_END
    path = []
    for j in range(fi, len(bs)):
        b = bs[j]
        o_eff = entry_px if j == fi else b["o"]
        # mirror: para SHORT, "l_r" (favorable extremo, como en LONG) usa el LOW real (precio cae);
        # "h_r" (adverso, dispara SL) usa el HIGH real (precio sube).
        o_r = (entry_px - o_eff) / 1.0  # se normaliza a risk despues
        adverse_r = entry_px - b["h"]
        favorable_r = entry_px - b["l"]
        close_r = entry_px - b["c"]
        path.append((j - fi, o_r, adverse_r, favorable_r, close_r))
        if j >= cutoff:
            break
    return path, entry_px


def normalize_path(raw_path, risk):
    return [(off, o / risk, adv / risk, fav / risk, c / risk) for off, o, adv, fav, c in raw_path]


def resolve(path, sl_r, tp_r):
    for offset, o_r, l_r, h_r, c_r in path:
        if l_r <= -sl_r:
            base = o_r if o_r <= -sl_r else -sl_r
            return "SL", offset, base
        if h_r >= tp_r:
            base = o_r if o_r >= tp_r else tp_r
            return "TP", offset, base
    last = path[-1]
    return "TIME", last[0], last[4]


def resolve_slip(path, sl_r, tp_r, risk, slip_dollars):
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


def main():
    print("Cargando 10 años...")
    bydate = load_bydate(range(2016, 2027))
    blocks = build_5min_blocks(bydate)
    print(f"{len(blocks)} bloques 5-min.")
    closes = [b["c"] for b in blocks]
    r14 = td_rsi(closes)
    a14 = td_atr(blocks)
    sigs = td_signals(blocks)

    trades = []
    for s in sigs:
        if s["side"] != "short" or s["kind"] != "S9P":
            continue
        i = s["i"]
        if a14[i] is None or r14[i] is None or r14[i] < 60:
            continue
        b = blocks[i]
        entry = b["c"]
        sl = entry + 2 * a14[i]
        tp = entry - 3 * a14[i]
        risk = sl - entry
        if risk <= 0:
            continue
        tp_r = (entry - tp) / risk  # ~1.5 con la config actual (2xATR sl, 3xATR tp)
        result = find_fill_and_record_path(bydate, b["d"], b["i1"], entry)
        if result is None:
            continue
        raw_path, _ = result
        path = normalize_path(raw_path, risk)
        _, offset, exit_r = resolve(path, 1.0, tp_r)
        # features de contexto a la hora de la señal
        block_min = i * 5  # aprox minutos desde apertura del bloque en la serie continua -- no usar cross-day
        trades.append({"day": b["d"], "risk": risk, "tp_r": tp_r, "path": path,
                       "exit_r": exit_r, "rsi14": r14[i], "atr": a14[i]})

    print(f"{len(trades)} trades con fill confirmado (config LIVE: SL=1.0R TP~{trades[0]['tp_r']:.2f}R).\n")

    # ============================================================
    # 1. MFE/MAE
    # ============================================================
    print("=" * 70 + "\n1. MFE/MAE\n" + "=" * 70)
    winners = [t for t in trades if t["exit_r"] > 0]
    losers = [t for t in trades if t["exit_r"] <= 0]
    print(f"Ganadoras: {len(winners)} ({len(winners)/len(trades)*100:.1f}%)  Perdedoras: {len(losers)} ({len(losers)/len(trades)*100:.1f}%)")
    for label, group in (("GANADORAS", winners), ("PERDEDORAS", losers)):
        if not group:
            continue
        mfes = sorted(max(h for _, _, _, h, _ in t["path"]) for t in group)
        maes = sorted(min(l for _, _, l, _, _ in t["path"]) for t in group)
        n = len(group)
        print(f"  {label} (n={n}): MFE mediana={mfes[n//2]:+.2f}R  MAE mediana={maes[n//2]:+.2f}R")

    # ============================================================
    # 2. Grid SL/TP con slippage (config actual: SL=1.0R, TP~1.5R)
    # ============================================================
    print("\n" + "=" * 70 + f"\n2. Grid SL x TP con slippage (actual: SL=1.0R TP={trades[0]['tp_r']:.2f}R)\n" + "=" * 70)
    sl_grid = (0.5, 0.7, 1.0, 1.3)
    tp_grid = (0.8, 1.0, 1.2, 1.5, 2.0)
    for slip in (0.0, 0.01, 0.02):
        print(f"\n-- slippage=${slip:.2f} --")
        print(f"  {'SL\\TP':<8}" + "".join(f"{tp:>7.1f}" for tp in tp_grid))
        for sl_r in sl_grid:
            row = []
            for tp_r in tp_grid:
                rets = [resolve_slip(t["path"], sl_r, tp_r, t["risk"], slip) for t in trades]
                row.append(pf_of(rets))
            print(f"  {sl_r:<8.1f}" + "".join(f"{pf:>7.2f}" if pf != float('inf') else f"{'inf':>7}" for pf in row))

    rets_actual = [resolve_slip(t["path"], 1.0, trades[0]["tp_r"], t["risk"], 0.02) for t in trades]
    print(f"\nACTUAL (SL=1.0R TP={trades[0]['tp_r']:.2f}R) con slip=$0.02: PF={pf_of(rets_actual):.2f} pnl={sum(rets_actual):+.1f}R")

    # ============================================================
    # 3. Filtro de entrada por contexto (rsi14 magnitud, ATR regime)
    # ============================================================
    print("\n" + "=" * 70 + "\n3. Filtro de entrada (RSI14 magnitud, régimen de ATR)\n" + "=" * 70)
    for feat_key in ("rsi14", "atr"):
        vals = sorted((t[feat_key], idx) for idx, t in enumerate(trades))
        n = len(vals)
        lo, hi = vals[n // 3][0], vals[2 * n // 3][0]
        buckets = {"low": [], "mid": [], "high": []}
        for v, idx in vals:
            b = "low" if v < lo else ("high" if v > hi else "mid")
            buckets[b].append(resolve_slip(trades[idx]["path"], 1.0, trades[idx]["tp_r"], trades[idx]["risk"], 0.02))
        print(f"  -- {feat_key} -- lo={lo:.2f} hi={hi:.2f}")
        for b in ("low", "mid", "high"):
            rets = buckets[b]
            if rets:
                print(f"    {b}: n={len(rets)} PF={pf_of(rets):.2f}")

    # ============================================================
    # 4. TP = SL (R:R 1:1)
    # ============================================================
    print("\n" + "=" * 70 + "\n4. TP = SL (R:R 1:1)\n" + "=" * 70)
    for tp_r in (0.8, 1.0, 1.2, trades[0]["tp_r"]):
        for slip in (0.0, 0.02):
            rets = [resolve_slip(t["path"], 1.0, tp_r, t["risk"], slip) for t in trades]
            hit = sum(1 for r in rets if r > 0) / len(rets) * 100
            print(f"  TP={tp_r:.2f}R SL=1.0R slip=${slip:.2f}: n={len(rets)} hit={hit:.1f}% PF={pf_of(rets):.2f} pnl={sum(rets):+.1f}R")

    # año-por-año actual
    print("\nAño-por-año, config ACTUAL (SL=1.0R TP={:.2f}R), slip=$0.02:".format(trades[0]["tp_r"]))
    by_year = {}
    for t in trades:
        by_year.setdefault(t["day"][:4], []).append(t)
    for year in sorted(by_year):
        rets_y = [resolve_slip(t["path"], 1.0, trades[0]["tp_r"], t["risk"], 0.02) for t in by_year[year]]
        pf_y = pf_of(rets_y)
        pf_s = f"{pf_y:.2f}" if pf_y != float("inf") else "inf"
        print(f"    {year}: n={len(rets_y):>4} PF={pf_s:>5} pnl={sum(rets_y):+7.1f}R")


if __name__ == "__main__":
    main()
