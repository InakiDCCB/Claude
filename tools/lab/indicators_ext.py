"""Indicadores nuevos para ampliar el universo de señales probadas (pedido usuario 2026-08-28,
"busquemos mayor amplitud y mas indicadores"). Ninguno de estos vive en tools/backtest.py -- son
research puro, calculados aqui sobre los mismos Day objects (misma convencion del proyecto: cada
sesion se calcula FRESCA desde la barra 0, sin arrastre overnight, igual que ema9/rsi14/atr en
Day.__init__). NO tocan produccion.

Indicadores: MACD(12,26,9), Bollinger Bands(20,2), Stochastic(14,3,3), ADX(14)+DI.
Señales (mismo contrato signal_fn(day,i)->dict|None que tools/backtest.py, enchufables directo a
run_market/run_market_short):
  - macd_cross_long/short: cruce de linea MACD sobre/bajo señal, saliendo de terreno negativo/
    positivo (evita cruces en medio de una tendencia ya extendida).
  - bb_reversion_long/short: mecha que perfora la banda de Bollinger y cierra de vuelta adentro
    (reversion a la media, distinto de wick_reversal que usa nivel de sesion no banda estadistica).
  - stoch_reversal_long/short: %K cruza %D saliendo de sobreventa/sobrecompra (<20 / >80).
  - ADX no es señal standalone (fuerza de tendencia, no direccion) -- se usa como FILTRO opcional
    vía `adx_filter(day, i, min_adx=None, max_adx=None)`, combinable con cualquier señal existente.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from backtest import ema  # reusa la misma EMA que el resto del proyecto


def macd(day, fast=12, slow=26, signal=9):
    ef = ema(day.c, fast)
    es = ema(day.c, slow)
    n = day.n
    macd_line = [None] * n
    for i in range(n):
        if ef[i] is not None and es[i] is not None:
            macd_line[i] = ef[i] - es[i]
    vals = [v for v in macd_line if v is not None]
    sig_line = [None] * n
    if len(vals) >= signal:
        start = next(i for i in range(n) if macd_line[i] is not None)
        s = sum(macd_line[start:start + signal]) / signal
        sig_line[start + signal - 1] = s
        k = 2 / (signal + 1)
        for i in range(start + signal, n):
            if macd_line[i] is None:
                continue
            s = macd_line[i] * k + s * (1 - k)
            sig_line[i] = s
    hist = [None] * n
    for i in range(n):
        if macd_line[i] is not None and sig_line[i] is not None:
            hist[i] = macd_line[i] - sig_line[i]
    return macd_line, sig_line, hist


def bollinger(day, n=20, k=2.0):
    c = day.c
    m = day.n
    mid = [None] * m
    upper = [None] * m
    lower = [None] * m
    for i in range(n - 1, m):
        window = c[i - n + 1:i + 1]
        avg = sum(window) / n
        var = sum((x - avg) ** 2 for x in window) / n
        sd = var ** 0.5
        mid[i] = avg
        upper[i] = avg + k * sd
        lower[i] = avg - k * sd
    return mid, upper, lower


def stochastic(day, n=14, smooth_k=3, smooth_d=3):
    h, l, c = day.h, day.l, day.c
    m = day.n
    raw_k = [None] * m
    for i in range(n - 1, m):
        hh = max(h[i - n + 1:i + 1])
        ll = min(l[i - n + 1:i + 1])
        raw_k[i] = 100 * (c[i] - ll) / (hh - ll) if hh > ll else 50.0
    k_line = [None] * m
    for i in range(m):
        if i >= n - 1 + smooth_k - 1:
            vals = [raw_k[j] for j in range(i - smooth_k + 1, i + 1) if raw_k[j] is not None]
            if len(vals) == smooth_k:
                k_line[i] = sum(vals) / smooth_k
    d_line = [None] * m
    for i in range(m):
        if i >= n - 1 + smooth_k - 1 + smooth_d - 1:
            vals = [k_line[j] for j in range(i - smooth_d + 1, i + 1) if k_line[j] is not None]
            if len(vals) == smooth_d:
                d_line[i] = sum(vals) / smooth_d
    return k_line, d_line


def adx(day, n=14):
    h, l, c = day.h, day.l, day.c
    m = day.n
    plus_dm = [0.0] * m
    minus_dm = [0.0] * m
    tr = [0.0] * m
    for i in range(1, m):
        up = h[i] - h[i - 1]
        dn = l[i - 1] - l[i]
        plus_dm[i] = up if (up > dn and up > 0) else 0.0
        minus_dm[i] = dn if (dn > up and dn > 0) else 0.0
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    adx_out = [None] * m
    plus_di = [None] * m
    minus_di = [None] * m
    if m <= n + n:
        return adx_out, plus_di, minus_di
    atr = sum(tr[1:n + 1]) / n
    pdm = sum(plus_dm[1:n + 1]) / n
    mdm = sum(minus_dm[1:n + 1]) / n
    dx_vals = []

    def _di(pdm, mdm, atr):
        if atr == 0:
            return 0.0, 0.0
        return 100 * pdm / atr, 100 * mdm / atr

    pdi, mdi = _di(pdm, mdm, atr)
    plus_di[n], minus_di[n] = pdi, mdi
    dx_vals.append(100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0.0)
    for i in range(n + 1, m):
        atr = (atr * (n - 1) + tr[i]) / n
        pdm = (pdm * (n - 1) + plus_dm[i]) / n
        mdm = (mdm * (n - 1) + minus_dm[i]) / n
        pdi, mdi = _di(pdm, mdm, atr)
        plus_di[i], minus_di[i] = pdi, mdi
        dx = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0.0
        dx_vals.append(dx)
        if len(dx_vals) == n:
            adx_out[i] = sum(dx_vals) / n
        elif len(dx_vals) > n:
            adx_out[i] = (adx_out[i - 1] * (n - 1) + dx) / n
    return adx_out, plus_di, minus_di


# ----------------------- señales (contrato signal_fn(day,i)) -----------------------

def macd_cross(direction, tp, sl_atr=1.5):
    """direction: 'long' (cruce alcista MACD>signal viniendo de hist<0) o 'short' (espejo)."""
    def factory():
        def fn(day, i):
            _, _, hist = day.ext_macd
            if i < 1 or hist[i] is None or hist[i - 1] is None or day.atr[i] is None:
                return None
            if direction == "long" and hist[i - 1] <= 0 < hist[i]:
                return {"sl_atr": sl_atr, "tp": tp}
            if direction == "short" and hist[i - 1] >= 0 > hist[i]:
                return {"sl_atr": sl_atr, "tp": tp}
            return None
        return fn
    return factory


def bb_reversion(direction, tp, n=20, k=2.0, buffer_sl=0.05):
    def factory():
        def fn(day, i):
            _, upper, lower = day.ext_bb
            if direction == "long":
                if lower[i] is None or day.l[i] >= lower[i] or day.c[i] <= lower[i]:
                    return None
                return {"sl_abs": round(day.l[i] - buffer_sl, 2), "tp": tp}
            if upper[i] is None or day.h[i] <= upper[i] or day.c[i] >= upper[i]:
                return None
            return {"sl_abs": round(day.h[i] + buffer_sl, 2), "tp": tp}
        return fn
    return factory


def stoch_reversal(direction, tp, sl_atr=1.5, oversold=20, overbought=80):
    def factory():
        def fn(day, i):
            k_line, d_line = day.ext_stoch
            if i < 1 or k_line[i] is None or d_line[i] is None or k_line[i - 1] is None or d_line[i - 1] is None:
                return None
            if day.atr[i] is None:
                return None
            window = [v for v in k_line[max(0, i - 5):i + 1] if v is not None]
            if direction == "long":
                if k_line[i - 1] <= d_line[i - 1] and k_line[i] > d_line[i] and k_line[i] < oversold + 15:
                    if window and min(window) < oversold:
                        return {"sl_atr": sl_atr, "tp": tp}
                return None
            if k_line[i - 1] >= d_line[i - 1] and k_line[i] < d_line[i] and k_line[i] > overbought - 15:
                if window and max(window) > overbought:
                    return {"sl_atr": sl_atr, "tp": tp}
            return None
        return fn
    return factory


def with_adx_filter(base_factory, min_adx=None, max_adx=None):
    """Envuelve cualquier signal_fn con un filtro de ADX (fuerza de tendencia, no direccion)."""
    def factory():
        base_fn = base_factory()

        def fn(day, i):
            adx_line, _, _ = day.ext_adx
            if adx_line[i] is None:
                return None
            if min_adx is not None and adx_line[i] < min_adx:
                return None
            if max_adx is not None and adx_line[i] > max_adx:
                return None
            return base_fn(day, i)
        return fn
    return factory


def attach_ext_indicators(days):
    """Precomputa MACD/BB/Stoch/ADX sobre cada Day y los cachea como atributos -- evita
    recalcularlos por cada llamada a signal_fn (serian O(n^2) si no)."""
    for day in days:
        if not hasattr(day, "ext_macd"):
            day.ext_macd = macd(day)
            day.ext_bb = bollinger(day)
            day.ext_stoch = stochastic(day)
            day.ext_adx = adx(day)
    return days
