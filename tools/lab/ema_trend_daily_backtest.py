"""Backtest de estrategia de tendencia EMA diaria (pedido usuario 2026-08-19): comprar cuando el
cierre diario está arriba de la EMA(N), vender/shortear cuando está abajo -- probado para N=200 y
N=100 por separado, sobre los ~10.6 años de historia diaria disponible (tools/data/qqq_daily_full.json).

Metodología: la posición del día D+1 se decide con el cierre de D vs EMA(N) calculada con datos
HASTA D inclusive (sin look-ahead -- lección de la sesión, ver feedback_lookahead_bias_research.md).
Reversal system: siempre en mercado, long si close>EMA, short si close<EMA (cambia de lado en el
cruce). Se reporta equity curve completa: retorno total, CAGR, nº de flips (trades), win rate,
Wilson LB, max drawdown, y comparación contra buy&hold del mismo período.

Uso: python ema_trend_daily_backtest.py
"""
import datetime as dt
import json
from pathlib import Path

DAILY_PATH = Path(__file__).parents[1] / "data" / "qqq_daily_full.json"


def ema(values, n):
    out = [None] * len(values)
    if len(values) < n:
        return out
    s = sum(values[:n]) / n
    out[n - 1] = s
    k = 2 / (n + 1)
    for i in range(n, len(values)):
        s = values[i] * k + s * (1 - k)
        out[i] = s
    return out


def wilson_lb(wins, n, z=1.96):
    if n == 0:
        return None
    p = wins / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (center - margin) / denom


def backtest_ema_trend(dates, closes, ema_period):
    e = ema(closes, ema_period)
    trades = []       # cada trade: {"side","entry_i","exit_i","pnl_pct"}
    equity = [1.0]
    pos = None         # "long" | "short" | None
    entry_px = None
    entry_i = None

    for i in range(ema_period, len(closes) - 1):
        if e[i] is None:
            equity.append(equity[-1])
            continue
        desired = "long" if closes[i] > e[i] else "short"
        if pos is None:
            pos, entry_px, entry_i = desired, closes[i], i
        elif desired != pos:
            exit_px = closes[i]
            pnl_pct = (exit_px / entry_px - 1) if pos == "long" else (entry_px / exit_px - 1)
            trades.append({"side": pos, "entry_i": entry_i, "exit_i": i, "pnl_pct": pnl_pct,
                           "entry_date": dates[entry_i], "exit_date": dates[i]})
            pos, entry_px, entry_i = desired, closes[i], i

        # retorno diario de mañana (i+1 close vs i close) aplicado según la posición decidida HOY
        day_ret = (closes[i + 1] / closes[i] - 1)
        applied = day_ret if pos == "long" else -day_ret
        equity.append(equity[-1] * (1 + applied))

    # cerrar posición abierta al final
    if pos is not None:
        exit_px = closes[-1]
        pnl_pct = (exit_px / entry_px - 1) if pos == "long" else (entry_px / exit_px - 1)
        trades.append({"side": pos, "entry_i": entry_i, "exit_i": len(closes) - 1,
                       "pnl_pct": pnl_pct, "entry_date": dates[entry_i], "exit_date": dates[-1]})

    return trades, equity


def max_drawdown(equity):
    peak = equity[0]
    mdd = 0.0
    for x in equity:
        peak = max(peak, x)
        dd = (x / peak - 1)
        mdd = min(mdd, dd)
    return mdd


def report(name, dates, closes, ema_period):
    trades, equity = backtest_ema_trend(dates, closes, ema_period)
    n_years = (dt.date.fromisoformat(dates[-1]) - dt.date.fromisoformat(dates[ema_period])).days / 365.25
    total_ret = equity[-1] - 1
    cagr = (equity[-1] ** (1 / n_years) - 1) if n_years > 0 else None
    wins = [t for t in trades if t["pnl_pct"] > 0]
    mdd = max_drawdown(equity)

    bh_total = closes[-1] / closes[ema_period] - 1
    bh_cagr = ((closes[-1] / closes[ema_period]) ** (1 / n_years) - 1) if n_years > 0 else None

    print(f"\n=== {name} (EMA{ema_period}, {n_years:.1f} años, {dates[ema_period]}..{dates[-1]}) ===")
    print(f"  Estrategia: retorno total={total_ret*100:+.1f}%  CAGR={cagr*100:+.2f}%  "
          f"maxDD={mdd*100:.1f}%  trades={len(trades)}  "
          f"win%={100*len(wins)/len(trades):.1f}%  wilsonLB={wilson_lb(len(wins), len(trades))*100:.1f}%")
    print(f"  Buy&Hold:   retorno total={bh_total*100:+.1f}%  CAGR={bh_cagr*100:+.2f}%")

    print("  Últimos 8 trades:")
    for t in trades[-8:]:
        print(f"    {t['entry_date']} -> {t['exit_date']}  {t['side']:<5}  pnl={t['pnl_pct']*100:+.2f}%")

    # desglose por año calendario (¿la estrategia gana consistentemente o depende de un período?)
    by_year = {}
    for idx in range(ema_period, len(closes) - 1):
        yr = dates[idx][:4]
        by_year.setdefault(yr, []).append(idx)
    print("  Retorno acumulado por año calendario (aplicando la posición decidida cada día):")
    e = ema(closes, ema_period)
    pos = "long" if closes[ema_period] > e[ema_period] else "short"
    for yr in sorted(by_year):
        idxs = by_year[yr]
        yr_equity = 1.0
        for i in idxs:
            if e[i] is not None:
                pos = "long" if closes[i] > e[i] else "short"
            day_ret = (closes[i + 1] / closes[i] - 1)
            yr_equity *= (1 + (day_ret if pos == "long" else -day_ret))
        print(f"    {yr}: {(yr_equity-1)*100:+7.2f}%")


def main():
    bars = json.loads(DAILY_PATH.read_text())
    bars.sort(key=lambda b: b["t"])
    dates = [b["t"][:10] for b in bars]
    closes = [b["c"] for b in bars]

    report("EMA200 trend (long>EMA / short<EMA)", dates, closes, 200)
    report("EMA100 trend (long>EMA / short<EMA)", dates, closes, 100)


if __name__ == "__main__":
    main()
