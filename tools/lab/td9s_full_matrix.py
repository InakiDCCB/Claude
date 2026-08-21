"""Búsqueda EXHAUSTIVA de TD9S/RUUT Cyclone, pedido explícito del usuario ("revisemos TODOS de
TODAS las maneras posibles"). La config LIVE (S9P short + RSI14>=60) ya se descartó (nunca cruza
PF=1.0 en ningún SL/TP/slippage, ver project_td9s... / shadow_full_history_check.py). Esta corrida
prueba TODA la matriz original de `td_backtest.py` (kind x filtro x dirección, 36 combos) contra
los 10 años completos (no los 61 sesiones originales) CON slippage=$0.02, para ver si alguna
combinación distinta a la que ya está en shadow tiene edge real.

kinds: S9+9P (setup 9 crudo + perfeccionado), 9P (solo perfeccionado), C13 (countdown 13)
filtros: raw, rsi (14<=30 buy/>=70 sell), ema (200), mtf (momentum 15min), rsi+ema, rsi_soft (40/60)
sides: long, short

Uso: python td9s_full_matrix.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from td_backtest import rsi as td_rsi, ema as td_ema, atr as td_atr, td_signals  # noqa: E402

DATA_1MIN_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"
RECENT_YEARS = {"2023", "2024", "2025", "2026"}


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


def simulate_1min(bydate, day, i1, side, entry, sl, tp, slip):
    bs = bydate[day]
    fi = None
    for j in range(i1 + 1, min(i1 + 4, len(bs))):
        if (side == "long" and bs[j]["l"] <= entry) or (side == "short" and bs[j]["h"] >= entry):
            fi = j
            break
    if fi is None:
        return None
    cutoff = len(bs) - 5
    for j in range(fi, len(bs)):
        b = bs[j]
        op = entry if j == fi else b["o"]
        if side == "long":
            if b["l"] <= sl:
                px = (op if op <= sl else sl) - slip
                return px - entry
            if b["h"] >= tp:
                px = (op if op >= tp else tp) - slip
                return px - entry
        else:
            if b["h"] >= sl:
                px = (op if op >= sl else sl) + slip
                return entry - px
            if b["l"] <= tp:
                px = (op if op <= tp else tp) + slip
                return entry - px
        if j >= cutoff:
            return ((b["c"] - slip) - entry) if side == "long" else (entry - (b["c"] + slip))
    b = bs[-1]
    return ((b["c"] - slip) - entry) if side == "long" else (entry - (b["c"] + slip))


def pf_of(rets):
    gw = sum(r for r in rets if r > 0)
    gl = -sum(r for r in rets if r <= 0)
    return gw / gl if gl > 0 else float("inf")


def main():
    print("Cargando 10 años...")
    bydate = load_bydate(range(2016, 2027))
    blocks = build_5min_blocks(bydate)
    closes = [b["c"] for b in blocks]
    r14 = td_rsi(closes)
    e200 = td_ema(closes, 200)
    a14 = td_atr(blocks)
    m15 = [blocks[i]["c"] for i in range(2, len(blocks), 3)]

    def mtf_bull(i):
        k = (i - 2) // 3
        return k >= 4 and m15[min(k, len(m15) - 1)] > m15[min(k, len(m15) - 1) - 4]

    sigs = td_signals(blocks)
    print(f"{len(blocks)} bloques, señales TD crudas: {len(sigs)}")

    FILTERS = {
        "raw": lambda s, i: True,
        "rsi": lambda s, i: r14[i] is not None and (r14[i] <= 30 if s == "long" else r14[i] >= 70),
        "ema": lambda s, i: e200[i] is not None and ((closes[i] > e200[i]) if s == "long" else (closes[i] < e200[i])),
        "mtf": lambda s, i: mtf_bull(i) if s == "long" else not mtf_bull(i),
        "rsi+ema": lambda s, i: (r14[i] is not None and (r14[i] <= 30 if s == "long" else r14[i] >= 70))
                                  and (e200[i] is not None and ((closes[i] > e200[i]) if s == "long" else (closes[i] < e200[i]))),
        "rsi_soft": lambda s, i: r14[i] is not None and (r14[i] <= 40 if s == "long" else r14[i] >= 60),
    }

    results = []
    for side in ("long", "short"):
        for kinds, kn in ((("S9", "S9P"), "S9+9P"), (("S9P",), "9P"), (("C13",), "C13")):
            for fname, ffn in FILTERS.items():
                rets_all, rets_recent = [], []
                by_year = {}
                for s in sigs:
                    if s["side"] != side or s["kind"] not in kinds:
                        continue
                    i = s["i"]
                    if a14[i] is None or not ffn(side, i):
                        continue
                    b = blocks[i]
                    entry = b["c"]
                    if side == "long":
                        sl, tp = entry - 2 * a14[i], entry + 3 * a14[i]
                    else:
                        sl, tp = entry + 2 * a14[i], entry - 3 * a14[i]
                    r = simulate_1min(bydate, b["d"], b["i1"], side, entry, sl, tp, 0.02)
                    if r is None:
                        continue
                    rets_all.append(r)
                    by_year.setdefault(b["d"][:4], []).append(r)
                    if b["d"][:4] in RECENT_YEARS:
                        rets_recent.append(r)
                if len(rets_all) < 30:
                    continue
                pf_all = pf_of(rets_all)
                pf_recent = pf_of(rets_recent) if len(rets_recent) >= 15 else None
                years_pos = sum(1 for y, rs in by_year.items() if pf_of(rs) > 1.0)
                results.append({"side": side, "kind": kn, "filter": fname, "n": len(rets_all),
                                "pf": pf_all, "pf_recent": pf_recent, "n_recent": len(rets_recent),
                                "years_pos": years_pos, "n_years": len(by_year)})

    results.sort(key=lambda r: r["pf"], reverse=True)
    print(f"\n{'side':<7}{'kind':<8}{'filter':<10}{'n':>6}{'PF_pool':>9}{'n_rec':>7}{'PF_rec':>9}{'años+':>8}")
    for r in results:
        pf_s = f"{r['pf']:.2f}" if r['pf'] != float('inf') else "inf"
        pfr_s = f"{r['pf_recent']:.2f}" if r['pf_recent'] is not None and r['pf_recent'] != float('inf') else "n/a"
        print(f"{r['side']:<7}{r['kind']:<8}{r['filter']:<10}{r['n']:>6}{pf_s:>9}{r['n_recent']:>7}{pfr_s:>9}{r['years_pos']:>5}/{r['n_years']}")

    print(f"\nTotal combos con n>=30: {len(results)}. Mejor PF pool: {results[0]['pf']:.2f} ({results[0]['side']} {results[0]['kind']} {results[0]['filter']})")
    survivors = [r for r in results if r["pf"] > 1.0 and r["pf_recent"] is not None and r["pf_recent"] > 1.0]
    print(f"Combos con PF>1.0 en AMBAS ventanas (pool y reciente): {len(survivors)}")
    for r in survivors:
        print(f"  {r['side']} {r['kind']} {r['filter']}: pool={r['pf']:.2f} recent={r['pf_recent']:.2f} años+={r['years_pos']}/{r['n_years']}")


if __name__ == "__main__":
    main()
