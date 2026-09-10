"""Optimizador BBWP Squeeze + No-confirmacion sobre BTC/USD (barras diarias).

Replica en Python, bar a bar, la misma logica que tools/lab/pine/bbwp_squeeze_nonconfirm.pine
(y bbwp_squeeze_study.pine): squeeze de volatilidad (BBWP) + tendencia bajista + no-confirmacion
de RSI/momentum -> long, con SL por ATR y TP expresado como multiplo del riesgo (R:R). Una
operacion a la vez, igual que la estrategia (pyramiding=0).

Uso pedido por el usuario: barrer inputs sobre BTCUSD buscando el maximo retorno compuesto con
la restriccion R:R > 1.8 SIEMPRE (todos los rrTarget del grid son > 1.8). El resto de
"requisitos" de la estrategia completa (sizing, prop-firm, sesiones, filtros de dia/fecha) NO
aplica en esta prueba: aqui solo se mide la logica de entrada + SL/TP, sin costes ni limites de
cuenta -- es la misma cota superior que ya advierte bbwp_squeeze_study.pine, ahora barrida.

DATOS: agrega a barras DIARIAS los 1-min de tools/data/btc_1min/*.csv (fetch_btc.py --rth-only),
que cubren la ventana 13:30-20:00 UTC de TODOS los dias de la semana (BTC cotiza 24/7; el filtro
es solo de horario, no de dia -- verificado: 365/365 dias en 2021 estan presentes). Alpaca no
tiene historia de BTC/USD anterior a 2021-01-01 (2018/2019/2020 devuelven 0 barras): el maximo
historico disponible es ~5.7 anios (2021-01-01 -> hoy), no los 8 pedidos. Se deja constancia de
esto en la salida del script en vez de fabricar mas historia.

Uso:
    python bbwp_btc_optimizer.py                    # grid completo, top 15
    python bbwp_btc_optimizer.py --top 25
    python bbwp_btc_optimizer.py --since 2021-06-01 --until 2025-01-01   # partir la muestra
"""
from __future__ import annotations

import argparse
import bisect
import csv
import itertools
import math
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data" / "btc_1min"


# ── carga y agregacion a diario ────────────────────────────────────────────────

def load_daily_bars(since: str | None, until: str | None):
    """Agrega los 1-min RTH-window en barras diarias (open=primero, close=ultimo,
    high/low=extremos, volume=suma). Descarta dias con menos del 70% de las barras
    esperadas (huecos de datos), para no ensuciar ATR/EMA con dias truncados."""
    days: dict[str, list] = {}
    for path in sorted(DATA_DIR.glob("*.csv")):
        with path.open() as f:
            for row in csv.DictReader(f):
                d = row["t"][:10]
                days.setdefault(d, []).append(row)

    dates = sorted(days)
    if since:
        dates = [d for d in dates if d >= since]
    if until:
        dates = [d for d in dates if d <= until]

    EXPECTED = 390  # 6.5h de barras 1-min
    out_d, out_o, out_h, out_l, out_c, out_v = [], [], [], [], [], []
    for d in dates:
        bars = days[d]
        if len(bars) < EXPECTED * 0.7:
            continue
        out_d.append(d)
        out_o.append(float(bars[0]["o"]))
        out_h.append(max(float(b["h"]) for b in bars))
        out_l.append(min(float(b["l"]) for b in bars))
        out_c.append(float(bars[-1]["c"]))
        out_v.append(sum(float(b["v"]) for b in bars))
    return out_d, out_o, out_h, out_l, out_c, out_v


# ── indicadores (mismas formulas que el .pine, ver comentarios) ───────────────

def sma(vals, n):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema_series(vals, n):
    """EMA con seed = SMA de los primeros n valores (seed convencional; a diferencia de
    Wilder RSI/ATR, la EMA no necesita seed de dos fases -- ver feedback-wilder-two-phase-seed
    en la memoria del proyecto, que aplica solo a promedios Wilder-smoothed)."""
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    s = sum(vals[:n]) / n
    out[n - 1] = s
    k = 2 / (n + 1)
    for i in range(n, len(vals)):
        s = vals[i] * k + s * (1 - k)
        out[i] = s
    return out


def wilder_rsi(closes, n):
    """Wilder RSI con seed de dos fases: promedio simple de las primeras n variaciones,
    recien despues recursion (feedback-wilder-two-phase-seed)."""
    rsi = [None] * len(closes)
    if len(closes) < n + 1:
        return rsi
    gains = losses = 0.0
    for k in range(1, n + 1):
        d = closes[k] - closes[k - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / n, losses / n
    rsi[n] = 100 - 100 / (1 + (ag / al if al else 1e9))
    for k in range(n + 1, len(closes)):
        d = closes[k] - closes[k - 1]
        ag = (ag * (n - 1) + max(d, 0.0)) / n
        al = (al * (n - 1) + max(-d, 0.0)) / n
        rsi[k] = 100 - 100 / (1 + (ag / al if al else 1e9))
    return rsi


def wilder_atr(h, l, c, n):
    m = len(c)
    atr = [None] * m
    trs = [h[0] - l[0]] + [
        max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(1, m)
    ]
    if m <= n:
        return atr
    a = sum(trs[1 : n + 1]) / n
    atr[n] = a
    for k in range(n + 1, m):
        a = (a * (n - 1) + trs[k]) / n
        atr[k] = a
    return atr


def bbwp_series(closes, basis_len, lookback):
    """Percentile rank del ancho de banda de Bollinger, calculado EXACTAMENTE como
    f_bbwp() en el .pine: buffer FIFO ordenado, percentil contra el historial ACUMULADO
    HASTA lookback muestras, excluyendo el valor actual del calculo del percentil
    (se inserta despues de leer el rank). No usa binary_search_rightmost de Pine porque
    aqui basta bisect.insort de la libreria estandar -- mismo resultado, sin necesidad
    de optimizar para tiempo de ejecucion como si hace el Pine original."""
    n = len(closes)
    basis = sma(closes, basis_len)
    bbw = [None] * n
    for i in range(basis_len - 1, n):
        window = closes[i - basis_len + 1 : i + 1]
        mean = basis[i]
        var = sum((x - mean) ** 2 for x in window) / basis_len  # poblacional, como ta.stdev
        sd = math.sqrt(var)
        b = mean if mean != 0 else None
        bbw[i] = (2 * sd / abs(b)) if b else None

    out = [None] * n
    raw: list[float] = []
    sorted_buf: list[float] = []
    for i in range(n):
        if i >= basis_len - 1 and bbw[i] is not None:
            cnt = bisect.bisect_right(sorted_buf, bbw[i])
            out[i] = cnt * 100.0 / len(sorted_buf) if sorted_buf else None
            raw.append(bbw[i])
            bisect.insort(sorted_buf, bbw[i])
            if len(raw) > lookback:
                old = raw.pop(0)
                sorted_buf.pop(bisect.bisect_left(sorted_buf, old))
    return out


def rolling_lowest_lag1(vals, window):
    """ta.lowest(vals, window)[1]: minimo de los `window` valores ANTERIORES a la barra
    actual (no incluye la barra actual)."""
    n = len(vals)
    out = [None] * n
    for i in range(n):
        lo = i - window
        hi = i  # exclusivo: [lo, i)
        if lo < 0:
            continue
        seg = [v for v in vals[lo:hi] if v is not None]
        if len(seg) == window:
            out[i] = min(seg)
    return out


def rolling_highest_incl(vals, window):
    """ta.highest(vals, window): maximo de las `window` barras QUE INCLUYEN la actual."""
    n = len(vals)
    out = [None] * n
    for i in range(n):
        lo = max(0, i - window + 1)
        seg = [v for v in vals[lo : i + 1] if v is not None]
        if len(seg) == (i - lo + 1):
            out[i] = max(seg)
    return out


# ── simulacion de una operacion a la vez ───────────────────────────────────────

def simulate(o, h, l, c, sqz_ok, bear_trend, non_confirm, ready, atr, sl_atr, rr_target,
             use_time, max_bars):
    """Misma mecanica que el motor de estudio: entra al cierre de la barra de senal
    (una operacion a la vez), SL/TP fijados con el ATR congelado al entrar, SL revisado
    antes que TP en caso de empate en la misma barra (supuesto conservador)."""
    n = len(c)
    trades = []  # lista de retornos % netos por operacion
    in_trade = False
    entry_px = sl_px = tp_px = 0.0
    entry_bar = 0

    for i in range(n):
        if in_trade and i > entry_bar:
            hit_sl = l[i] <= sl_px
            hit_tp = h[i] >= tp_px
            hit_time = use_time and (i - entry_bar) >= max_bars
            if hit_sl or hit_tp or hit_time:
                exit_px = sl_px if hit_sl else (tp_px if hit_tp else c[i])
                trades.append((exit_px - entry_px) / entry_px * 100.0)
                in_trade = False

        if (not in_trade and ready[i] and sqz_ok[i] and bear_trend[i] and non_confirm[i]
                and atr[i] is not None and atr[i] > 0):
            in_trade = True
            entry_px = c[i]
            entry_bar = i
            risk = sl_atr * atr[i]
            sl_px = entry_px - risk
            tp_px = entry_px + rr_target * risk

    return trades


def trade_stats(trades):
    n = len(trades)
    if n == 0:
        return dict(n=0, win_pct=None, pf=None, total_ret=0.0, max_dd=0.0)
    wins = [t for t in trades if t > 0]
    losses = [-t for t in trades if t < 0]
    pf = (sum(wins) / sum(losses)) if losses else math.inf if wins else None
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for t in trades:
        equity *= (1 + t / 100.0)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100.0)
    total_ret = (equity - 1) * 100.0
    return dict(n=n, win_pct=len(wins) / n * 100.0, pf=pf, total_ret=total_ret, max_dd=max_dd)


# ── grid search ─────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None)
    ap.add_argument("--until", default=None)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--min-n", type=int, default=5,
                     help="Operaciones minimas para listar un config (default 5; subir esto "
                          "es el primer control de sobreajuste: con miles de combos probados, "
                          "los 'mejores' resultados con pocas operaciones suelen ser ruido.")
    args = ap.parse_args()

    dates, o, h, l, c, v = load_daily_bars(args.since, args.until)
    n = len(dates)
    if n < 100:
        print(f"Solo {n} barras diarias utilizables -- insuficiente para un grid confiable.")
        return
    print(f"Barras diarias: {n}  ({dates[0]} -> {dates[-1]})  "
          f"= {n/365.25:.2f} anios de historia disponible en Alpaca para BTC/USD.\n")

    # --- parametros FIJOS en los defaults del indicador (no forman parte del barrido;
    #     el barrido se concentra en los parametros que mas mueven la aguja: umbral y
    #     sostenibilidad del squeeze, longitudes de BBWP/tendencia/divergencia, y la
    #     pareja SL/TP). Las tres patas de la tesis (EMA+ROC bajista, nuevo minimo,
    #     no-confirmacion de RSI y de momentum) se mantienen SIEMPRE activas: apagarlas
    #     seria otra estrategia, no una variante de esta.
    RSI_LEN, RSI_MARGIN, RSI_ZONE_MAX = 14, 2.0, 50.0
    SLOPE_LOOK, ROC_LOOK = 5, 10
    MACD_FAST, MACD_SLOW, MACD_SIG = 12, 26, 9

    # --- grid barrido
    basis_lens  = [5, 7, 10]
    lookbacks   = [60, 100, 150]
    sqz_maxs    = [5, 10, 15, 20, 25]
    sqz_bars_l  = [1, 2, 3]
    trend_lens  = [20, 50, 100]
    div_looks   = [10, 20, 30]
    sl_atrs     = [1.0, 1.5, 2.0]
    rr_targets  = [2.0, 2.5, 3.0, 4.0, 5.0]     # todos > 1.8, restriccion del usuario
    max_bars_l  = [10, 20]

    total_combos = (len(basis_lens) * len(lookbacks) * len(sqz_maxs) * len(sqz_bars_l)
                    * len(trend_lens) * len(div_looks) * len(sl_atrs) * len(rr_targets)
                    * len(max_bars_l))
    print(f"Combinaciones a evaluar: {total_combos:,}\n")

    rsi = wilder_rsi(c, RSI_LEN)
    atr14 = None  # ATR se calcula por sl_atr? no: ATR no depende de sl_atr, solo de atr_len fijo
    ATR_LEN = 14
    atr = wilder_atr(h, l, c, ATR_LEN)

    ema12 = ema_series(c, MACD_FAST)
    ema26 = ema_series(c, MACD_SLOW)
    macd_line = [(a - b) if a is not None and b is not None else None
                 for a, b in zip(ema12, ema26)]
    # senal MACD sobre la serie ya alineada (huecos None al principio)
    first_valid = next(i for i, x in enumerate(macd_line) if x is not None)
    sig_tail = ema_series(macd_line[first_valid:], MACD_SIG)
    macd_sig = [None] * first_valid + sig_tail
    mom = [(ml - sg) if ml is not None and sg is not None else None
           for ml, sg in zip(macd_line, macd_sig)]

    prior_low_rsi = {dl: rolling_lowest_lag1(rsi, dl) for dl in div_looks}
    prior_low_mom = {dl: rolling_lowest_lag1(mom, dl) for dl in div_looks}
    prior_low_px  = {dl: rolling_lowest_lag1(l, dl) for dl in div_looks}

    bbwp_cache = {(bl, lb): bbwp_series(c, bl, lb) for bl in basis_lens for lb in lookbacks}
    ready_cache = {(bl, lb): [x is not None and i >= lb + bl for i, x in
                               enumerate(bbwp_cache[(bl, lb)])]
                   for bl in basis_lens for lb in lookbacks}

    ema_cache = {tl: ema_series(c, tl) for tl in trend_lens}

    results = []
    evaluated = 0
    max_n_seen = 0
    for bl, lb in itertools.product(basis_lens, lookbacks):
        bbwp = bbwp_cache[(bl, lb)]
        ready_base = ready_cache[(bl, lb)]
        for sqz_bars in sqz_bars_l:
            bbwp_maxn = rolling_highest_incl(bbwp, sqz_bars)
            for sqz_max in sqz_maxs:
                sqz_ok = [r and (bm is not None) and bm <= sqz_max
                          for r, bm in zip(ready_base, bbwp_maxn)]
                for tl in trend_lens:
                    ema = ema_cache[tl]
                    bear_trend = [
                        (ema[i] is not None and i >= SLOPE_LOOK and ema[i - SLOPE_LOOK] is not None
                         and c[i] < ema[i] and ema[i] < ema[i - SLOPE_LOOK])
                        and (i >= ROC_LOOK and c[i] < c[i - ROC_LOOK])
                        for i in range(n)
                    ]
                    for dl in div_looks:
                        plpx, plrsi, plmom = prior_low_px[dl], prior_low_rsi[dl], prior_low_mom[dl]
                        non_confirm = [
                            (plpx[i] is not None and l[i] <= plpx[i])
                            and (plrsi[i] is not None and rsi[i] is not None
                                 and rsi[i] > plrsi[i] + RSI_MARGIN)
                            and (plmom[i] is not None and mom[i] is not None
                                 and mom[i] > plmom[i])
                            and (rsi[i] is not None and rsi[i] <= RSI_ZONE_MAX)
                            for i in range(n)
                        ]
                        for sl_atr, rr, mb in itertools.product(sl_atrs, rr_targets, max_bars_l):
                            trades = simulate(o, h, l, c, sqz_ok, bear_trend, non_confirm,
                                               ready_base, atr, sl_atr, rr, True, mb)
                            evaluated += 1
                            st = trade_stats(trades)
                            max_n_seen = max(max_n_seen, st["n"])
                            if st["n"] >= args.min_n:
                                results.append(dict(basis_len=bl, lookback=lb, sqz_bars=sqz_bars,
                                                     sqz_max=sqz_max, trend_len=tl, div_look=dl,
                                                     sl_atr=sl_atr, rr_target=rr, max_bars=mb,
                                                     **st))

    print(f"Evaluadas: {evaluated:,}   Con n>={args.min_n} operaciones: {len(results):,}"
          f"   (n maximo visto en TODO el grid: {max_n_seen})\n")
    results.sort(key=lambda r: r["total_ret"], reverse=True)

    hdr = (f"{'#':>3} {'ret%':>9} {'n':>4} {'win%':>6} {'PF':>6} {'maxDD%':>7}  "
           f"basisLen lookback sqzMax sqzBars trendLen divLook slATR RR maxBars")
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(results[: args.top], 1):
        pf_s = f"{r['pf']:.2f}" if isinstance(r["pf"], float) and math.isfinite(r["pf"]) else "inf"
        print(f"{i:>3} {r['total_ret']:>8.1f}% {r['n']:>4} {r['win_pct']:>5.1f}% {pf_s:>6} "
              f"{r['max_dd']:>6.1f}%  {r['basis_len']:>7} {r['lookback']:>8} {r['sqz_max']:>6} "
              f"{r['sqz_bars']:>7} {r['trend_len']:>8} {r['div_look']:>7} {r['sl_atr']:>5} "
              f"{r['rr_target']:>4} {r['max_bars']:>7}")


if __name__ == "__main__":
    main()
