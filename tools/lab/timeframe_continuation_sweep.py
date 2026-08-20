"""Research exploratorio: barrido de continuación/reversión de retorno across temporalidades
(1,3,5,10,15,30,65-min intradía + diario), 10 años QQQ (tools/data/qqq_1min/ + qqq_daily_full.json).

Objetivo (pedido del usuario 2026-08-19): "buscar coincidencias en temporalidades, no importa si
prueba o contradice teoría -- siempre se puede operar en la dirección de mayor probabilidad de
continuación." Reporta, para cada temporalidad, %continuación real (barra actual misma dirección
que la próxima) con n y un z-score aproximado contra la hipótesis nula 50% (paseo aleatorio), sin
filtrar por si el resultado "debería" ser momentum o reversión -- se reporta lo que sea, en la
dirección que sea. Intradía resetea cada día (sin gaps overnight); diario usa close-to-close.

Uso: python timeframe_continuation_sweep.py
"""
import csv
import json
import math
from pathlib import Path

DATA_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"
DAILY_PATH = Path(__file__).parents[1] / "data" / "qqq_daily_full.json"
YEARS = range(2016, 2027)


def iter_day_bars(years=None):
    for year in (years or YEARS):
        path = DATA_DIR / f"{year}.csv"
        if not path.exists():
            continue
        cur_date, cur_bars = None, []
        with path.open() as f:
            for row in csv.DictReader(f):
                date = row["t"][:10]
                if date != cur_date:
                    if cur_bars:
                        yield cur_bars
                    cur_date, cur_bars = date, []
                cur_bars.append(row)
            if cur_bars:
                yield cur_bars


def make_windows(bars, n):
    windows = []
    for i in range(0, len(bars) - n + 1, n):
        chunk = bars[i:i + n]
        windows.append({"o": float(chunk[0]["o"]), "c": float(chunk[-1]["c"])})
    return windows


def zscore(p, n):
    """z de (p - 0.5) bajo H0: Bernoulli(0.5), n observaciones."""
    se = 0.5 / math.sqrt(n)
    return (p - 0.5) / se


def sweep_intraday(window_min, years=None):
    n_total, continue_n = 0, 0
    fwd_ret_sum, fwd_ret_sumsq = 0.0, 0.0
    cont_abs_sum, rev_abs_sum = 0.0, 0.0
    for bars in iter_day_bars(years):
        w = make_windows(bars, window_min)
        if len(w) < 3:
            continue
        for i in range(len(w) - 1):
            cur_ret = w[i]["c"] - w[i]["o"]
            if cur_ret == 0:
                continue
            fwd_ret = (w[i + 1]["c"] - w[i + 1]["o"])
            sign = 1 if cur_ret > 0 else -1
            fwd_signed = fwd_ret * sign / w[i]["o"]
            n_total += 1
            fwd_ret_sum += fwd_signed
            fwd_ret_sumsq += fwd_signed * fwd_signed
            if fwd_signed > 0:
                continue_n += 1
                cont_abs_sum += fwd_signed
            else:
                rev_abs_sum += -fwd_signed
    if n_total == 0:
        return None
    p = continue_n / n_total
    mean = fwd_ret_sum / n_total
    var = fwd_ret_sumsq / n_total - mean * mean
    se_mean = (var / n_total) ** 0.5 if var > 0 else 0.0
    t_stat = mean / se_mean if se_mean > 0 else 0.0
    revert_n = n_total - continue_n
    return {"n": n_total, "pct_continue": p * 100, "z": zscore(p, n_total),
            "fwd_ret_mean_bps": 10000 * mean, "t_stat": t_stat,
            "avg_move_continue_bps": 10000 * cont_abs_sum / continue_n if continue_n else None,
            "avg_move_revert_bps": 10000 * rev_abs_sum / revert_n if revert_n else None}


def sweep_daily(horizons):
    bars = json.loads(DAILY_PATH.read_text())
    bars.sort(key=lambda b: b["t"])
    closes = [b["c"] for b in bars]
    daily_ret = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]

    results = {}
    for h in horizons:
        n_total, continue_n, fwd_sum = 0, 0, 0.0
        for i in range(len(daily_ret) - h):
            cur = daily_ret[i]
            if cur == 0:
                continue
            fwd = sum(daily_ret[i + 1:i + 1 + h])  # retorno acumulado de los próximos h días
            sign = 1 if cur > 0 else -1
            fwd_signed = fwd * sign
            n_total += 1
            fwd_sum += fwd_signed
            if fwd_signed > 0:
                continue_n += 1
        if n_total:
            p = continue_n / n_total
            results[h] = {"n": n_total, "pct_continue": p * 100, "z": zscore(p, n_total),
                          "fwd_ret_mean_bps": 10000 * fwd_sum / n_total}
    return results


def main():
    print("=== Intradía: %continuación barra actual -> barra siguiente, MISMA temporalidad ===")
    print("(z = significancia de la FRECUENCIA de continuación vs 50%; t_stat = significancia de "
          "la EXPECTANCY -- media de fwd_ret firmado -- vs 0. Son preguntas distintas.)")
    print(f"{'ventana':<8}{'n':>9}{'%cont':>8}{'z(freq)':>9}{'fwd_bps':>10}{'t(exp)':>8}"
          f"{'move|cont':>11}{'move|rev':>10}")
    for wmin in (1, 2, 3, 5, 10, 15, 20, 30, 65):
        r = sweep_intraday(wmin)
        if r:
            print(f"{str(wmin)+'min':<8}{r['n']:>9}{r['pct_continue']:>7.2f}%{r['z']:>9.1f}"
                  f"{r['fwd_ret_mean_bps']:>10.3f}{r['t_stat']:>8.1f}"
                  f"{r['avg_move_continue_bps']:>11.3f}{r['avg_move_revert_bps']:>10.3f}")

    print("\n=== Diario: %continuación retorno de hoy -> retorno acumulado de los próximos h días ===")
    print(f"{'horizonte':<12}{'n':>10}{'%continuación':>15}{'z-score':>10}{'fwd_ret medio(bps)':>20}")
    daily_res = sweep_daily((1, 2, 3, 5, 10, 20))
    for h, r in daily_res.items():
        print(f"{str(h)+'d':<12}{r['n']:>10}{r['pct_continue']:>14.2f}%{r['z']:>10.1f}"
              f"{r['fwd_ret_mean_bps']:>20.3f}")

    print("\n(z-score: |z|>~2 sugiere que no es casualidad para UNA sola prueba; con ~15 pruebas en"
          " este barrido, usar |z|>~3 como umbral más conservador contra falsos positivos por"
          " comparaciones múltiples. Signo de %continuación: >50% = momentum, <50% = reversión.)")

    print("\n=== Robustez: ventana de 10min (la de mejor t-stat de expectancy) año por año ===")
    print("(¿es un efecto estable, o lo arrastra un solo período?)")
    print(f"{'año':<6}{'n':>8}{'%cont':>8}{'fwd_bps':>10}{'t(exp)':>8}")
    for year in range(2016, 2027):
        r = sweep_intraday(10, years=[year])
        if r and r["n"] > 100:
            print(f"{year:<6}{r['n']:>8}{r['pct_continue']:>7.2f}%{r['fwd_ret_mean_bps']:>10.3f}"
                  f"{r['t_stat']:>8.1f}")


if __name__ == "__main__":
    main()
