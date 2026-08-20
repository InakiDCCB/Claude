"""Research exploratorio: replica el concepto de BBWP (Bollinger Band Width Percentile, ver
indicador Pine Script de The_Caretaker que trajo el usuario 2026-08-19) sobre QQQ 1-min 2016-2026
(tools/data/qqq_1min/, ya cacheado -- ver tools/fetch_1min_full.py) y prueba la hipótesis clásica
detrás del indicador: "squeeze" (BBW en percentil bajo vs su propia historia reciente) predice
expansión de volatilidad / ruptura direccional en las barras siguientes.

BBW = 2*stdev(closes, basisLen) / SMA(closes, basisLen)   -- ancho de banda de Bollinger
BBWP = percentil de BBW actual contra los últimos `lookback` valores de BBW (0-100)

Streaming, pure-stdlib, por-día (reset diario -- evita contaminar con el gap overnight), igual
patrón que micro_pattern_mining.py: nunca carga más de un día de barras 1-min en memoria.

Uso: python bbwp_squeeze_analysis.py [--since 2016] [--until 2026] [--window 5]
                                       [--basis-len 7] [--lookback 100] [--forward 6]
"""
import argparse
import csv
import statistics
from pathlib import Path

DATA_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"


def iter_day_bars(year):
    path = DATA_DIR / f"{year}.csv"
    if not path.exists():
        return
    cur_date, cur_bars = None, []
    with path.open() as f:
        for row in csv.DictReader(f):
            date = row["t"][:10]
            if date != cur_date:
                if cur_bars:
                    yield cur_date, cur_bars
                cur_date, cur_bars = date, []
            cur_bars.append(row)
        if cur_bars:
            yield cur_date, cur_bars


def make_windows(bars, n):
    windows = []
    for i in range(0, len(bars) - n + 1, n):
        chunk = bars[i:i + n]
        o = float(chunk[0]["o"])
        c = float(chunk[-1]["c"])
        h = max(float(b["h"]) for b in chunk)
        l = min(float(b["l"]) for b in chunk)
        windows.append({"o": o, "h": h, "l": l, "c": c})
    return windows


def population_stdev(values):
    m = sum(values) / len(values)
    return (sum((x - m) ** 2 for x in values) / len(values)) ** 0.5


def percentile_rank(window, x):
    """% de valores en `window` (incluyendo x, ya insertado) que son <= x."""
    return 100.0 * sum(1 for v in window if v <= x) / len(window)


class Acc:
    def __init__(self):
        self.n = 0
        self.s = 0.0

    def add(self, x):
        self.n += 1
        self.s += x

    def mean(self):
        return self.s / self.n if self.n else None


def bucket(bbwp, lo, hi):
    return "squeeze" if bbwp <= lo else ("expanded" if bbwp >= hi else "normal")


def run(years, n, basis_len, lookback, fwd, lo_thr, hi_thr):
    # stats por bucket: n, forward |return|, forward range, % continuación
    stats = {b: {"n": 0, "fwd_abs_ret": Acc(), "fwd_range": Acc(), "continue_n": 0} for b in
              ("squeeze", "normal", "expanded")}
    baseline_abs_ret = Acc()
    baseline_range = Acc()

    for year in years:
        for date, bars in iter_day_bars(year):
            w = make_windows(bars, n)
            if len(w) < basis_len + fwd + 2:
                continue
            closes = [x["c"] for x in w]
            bbw_hist = []  # FIFO, tamaño <= lookback

            for i in range(basis_len - 1, len(w) - fwd - 1):
                window_closes = closes[i - basis_len + 1:i + 1]
                basis = sum(window_closes) / basis_len
                sd = population_stdev(window_closes)
                if basis <= 0:
                    continue
                bbw = 2 * sd / basis

                bbw_hist.append(bbw)
                if len(bbw_hist) > lookback:
                    bbw_hist.pop(0)
                bbwp = percentile_rank(bbw_hist, bbw)

                b = bucket(bbwp, lo_thr, hi_thr)

                px_now = w[i]["c"]
                px_fwd = w[i + fwd]["c"]
                fwd_ret = (px_fwd - px_now) / px_now
                fwd_hi = max(x["h"] for x in w[i + 1:i + fwd + 1])
                fwd_lo = min(x["l"] for x in w[i + 1:i + fwd + 1])
                fwd_range = (fwd_hi - fwd_lo) / px_now

                cur_ret = (w[i]["c"] - w[i]["o"]) / w[i]["o"]

                stats[b]["n"] += 1
                stats[b]["fwd_abs_ret"].add(abs(fwd_ret))
                stats[b]["fwd_range"].add(fwd_range)
                if cur_ret != 0:
                    sign = 1 if cur_ret > 0 else -1
                    if fwd_ret * sign > 0:
                        stats[b]["continue_n"] += 1

                baseline_abs_ret.add(abs(fwd_ret))
                baseline_range.add(fwd_range)

    return stats, baseline_abs_ret, baseline_range


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=2016)
    ap.add_argument("--until", type=int, default=2026)
    ap.add_argument("--window", type=int, default=5, help="tamaño de ventana en barras 1-min")
    ap.add_argument("--basis-len", type=int, default=7)
    ap.add_argument("--lookback", type=int, default=100)
    ap.add_argument("--forward", type=int, default=6, help="ventanas hacia adelante a medir")
    ap.add_argument("--lo", type=float, default=20.0, help="umbral squeeze (BBWP <=)")
    ap.add_argument("--hi", type=float, default=80.0, help="umbral expanded (BBWP >=)")
    a = ap.parse_args()
    years = list(range(a.since, a.until + 1))

    print(f"BBWP squeeze analysis: {years[0]}-{years[-1]}, ventana={a.window}min, "
          f"basis_len={a.basis_len}, lookback={a.lookback}, forward={a.forward} ventanas "
          f"({a.forward * a.window}min)")
    stats, base_abs, base_range = run(years, a.window, a.basis_len, a.lookback, a.forward, a.lo, a.hi)

    total_n = sum(s["n"] for s in stats.values())
    print(f"\nn total = {total_n}")
    print(f"Baseline (todas las barras): fwd |ret| medio={base_abs.mean()*100:.4f}%  "
          f"fwd range medio={base_range.mean()*100:.4f}%")

    print(f"\n{'bucket':<12}{'n':>10}{'%muestra':>10}{'fwd|ret|':>12}{'fwd_range':>12}{'%continuación':>15}")
    for b in ("squeeze", "normal", "expanded"):
        s = stats[b]
        if s["n"] == 0:
            continue
        pct_sample = 100 * s["n"] / total_n
        fwd_abs = s["fwd_abs_ret"].mean() * 100
        fwd_rng = s["fwd_range"].mean() * 100
        pct_cont = 100 * s["continue_n"] / s["n"]
        print(f"{b:<12}{s['n']:>10}{pct_sample:>9.1f}%{fwd_abs:>11.4f}%{fwd_rng:>11.4f}%{pct_cont:>14.1f}%")

    sq, ex = stats["squeeze"], stats["expanded"]
    if sq["n"] and ex["n"]:
        print(f"\nRatio fwd_range squeeze/baseline: {sq['fwd_range'].mean()/base_range.mean():.3f}x")
        print(f"Ratio fwd_range expanded/baseline: {ex['fwd_range'].mean()/base_range.mean():.3f}x")
        print("(>1x = el bucket precede a MÁS rango que el promedio; <1x = precede a MENOS)")


if __name__ == "__main__":
    main()
