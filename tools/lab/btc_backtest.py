"""BTC/USD intraday backtest — todos los indicadores del motor QQQ adaptados a BTC.

Adaptaciones clave vs. backtest.py / backtest_short.py:
  - Datos: CSVs de tools/data/btc_1min/ (fetch_btc.py --rth-only)
  - Sesión: ventana NY 09:30-16:00 ET (13:30-20:00 UTC), misma que QQQ → comparabilidad directa
  - Thresholds de precio: todos en fracción de ATR o precio (escalan a BTC sin ajuste manual)
  - Dirección: LONG + SHORT sin restricción (BTC no tiene long-only)
  - FORCED bar 385 (15:55 ET equivalente dentro de la ventana de 390 barras)
  - Métricas en % del precio de entrada (escala-neutral) además de $ absoluto

Uso:
    python btc_backtest.py                       # todos los datos disponibles
    python btc_backtest.py --since 2022-01-01    # desde fecha
    python btc_backtest.py --long-only           # solo sistemas long
    python btc_backtest.py --short-only          # solo sistemas short
    python btc_backtest.py --top 20              # mostrar solo top N por PF
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data" / "btc_1min"
ENTRY_MIN = 30        # bar 30 = 10:00 ET (30 min después de open 09:30)
ENTRY_MAX = 375       # bar 375 = 15:45 ET
FORCED    = 385       # bar 385 = 15:55 ET → forced close


# ── indicadores ───────────────────────────────────────────────────────────────

def wilder_rsi(closes, n):
    rsi = [None] * len(closes)
    if len(closes) < n + 1:
        return rsi
    gains = losses = 0.0
    for k in range(1, n + 1):
        d = closes[k] - closes[k - 1]
        gains += max(d, 0); losses += max(-d, 0)
    ag, al = gains / n, losses / n
    rsi[n] = 100 - 100 / (1 + (ag / al if al else 1e9))
    for k in range(n + 1, len(closes)):
        d = closes[k] - closes[k - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        rsi[k] = 100 - 100 / (1 + (ag / al if al else 1e9))
    return rsi


def wilder_atr(h, l, c, n=14):
    m = len(c)
    atr = [None] * m
    trs = [h[0] - l[0]] + [max(h[k] - l[k], abs(h[k] - c[k-1]), abs(l[k] - c[k-1]))
                            for k in range(1, m)]
    if m <= n:
        return atr
    a = sum(trs[1:n+1]) / n
    atr[n] = a
    for k in range(n+1, m):
        a = (a * (n - 1) + trs[k]) / n
        atr[k] = a
    return atr


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


# ── clase Day ─────────────────────────────────────────────────────────────────

class Day:
    def __init__(self, date: str, bars: list, prev: "Day | None" = None):
        self.date = date
        self.o = [b["o"] for b in bars]
        self.h = [b["h"] for b in bars]
        self.l = [b["l"] for b in bars]
        self.c = [b["c"] for b in bars]
        self.v = [b["v"] for b in bars]
        n = self.n = len(bars)

        # VWAP + sigma intrasesión (ancla = primer bar de la ventana NY)
        sv = spv = sp2v = 0.0
        self.vwap = [None] * n
        self.sigma = [None] * n
        for i in range(n):
            tp = (self.h[i] + self.l[i] + self.c[i]) / 3
            sv += self.v[i]; spv += tp * self.v[i]; sp2v += tp * tp * self.v[i]
            if sv > 0:
                m = spv / sv
                self.vwap[i] = m
                self.sigma[i] = math.sqrt(max(sp2v / sv - m * m, 0.0))
            else:
                self.vwap[i] = tp
                self.sigma[i] = 0.0

        self.ema9  = ema(self.c, 9)
        self.rsi14 = wilder_rsi(self.c, 14)
        self.atr   = wilder_atr(self.h, self.l, self.c, 14)

        self.avgv20 = [None] * n
        self.avgv5  = [None] * n
        for i in range(n):
            if i >= 20: self.avgv20[i] = sum(self.v[i-20:i]) / 20
            if i >= 5:  self.avgv5[i]  = sum(self.v[i-5:i]) / 5

        self.prev_low  = [None] * n
        self.prev_high = [None] * n
        lo, hi = float("inf"), float("-inf")
        for i in range(n):
            self.prev_low[i]  = lo if lo != float("inf") else None
            self.prev_high[i] = hi if hi != float("-inf") else None
            lo = min(lo, self.l[i]); hi = max(hi, self.h[i])

        self.or_high = max(self.h[:30]) if n >= 30 else max(self.h)
        self.or_low  = min(self.l[:30]) if n >= 30 else min(self.l)

        # Barras 5-min por resampleo
        f_h, f_l, f_c = [], [], []
        for k in range(0, n - 4, 5):
            f_h.append(max(self.h[k:k+5]))
            f_l.append(min(self.l[k:k+5]))
            f_c.append(self.c[k+4])
        self.f_h, self.f_l, self.f_c = f_h, f_l, f_c
        self.f_rsi2 = wilder_rsi(f_c, 2)
        self.f_atr  = wilder_atr(f_h, f_l, f_c, 14)

        # Datos del día anterior (para VPOC approx, PDH/PDL/PDC)
        if prev is not None:
            pv = sum((prev.h[i] + prev.l[i] + prev.c[i]) / 3 * prev.v[i] for i in range(prev.n))
            vw = pv / sum(prev.v)
            ph, pl = max(prev.h), min(prev.l)
            self.y_vpoc = vw
            self.y_vah  = vw + 0.34 * (ph - pl)
            self.y_val  = vw - 0.34 * (ph - pl)
            self.pdh, self.pdl, self.pdc = ph, pl, prev.c[-1]
        else:
            self.y_vpoc = self.y_vah = self.y_val = self.pdh = self.pdl = self.pdc = None

        self.slope30 = [None] * n
        for i in range(30, n):
            self.slope30[i] = self.vwap[i] - self.vwap[i-30]

        self.prior3_vw: list[float] = []   # lo rellenan en main() después de construir todos los días


# ── motores de simulación ─────────────────────────────────────────────────────

def _simulate_long(day, entry_i, entry_px, sl, tp_spec, be_at_r=None, time_stop=None):
    risk = entry_px - sl
    tp_abs = None
    if tp_spec[0] == "r":
        tp_abs = entry_px + tp_spec[1] * risk
    elif tp_spec[0] == "abs":
        tp_abs = tp_spec[1]
    cur_sl = sl
    for j in range(entry_i, min(day.n, FORCED + 1)):
        op = entry_px if j == entry_i else day.o[j]
        if j >= FORCED:
            return j, day.o[j], "TIME"
        if day.l[j] <= cur_sl:
            return j, (op if op <= cur_sl else cur_sl), "SL"
        tp = tp_abs
        if tp_spec[0] == "vwap":
            tp = day.vwap[j] if day.vwap[j] and day.vwap[j] > entry_px else None
        if tp is not None and day.h[j] >= tp:
            return j, (op if op >= tp else tp), "TP"
        if tp_spec[0] == "fpc" and j > entry_i and day.c[j] > entry_px:
            return j, day.c[j], "TP"
        if time_stop is not None and j - entry_i >= time_stop:
            return j, day.c[j], "TIME"
        if be_at_r is not None and day.h[j] >= entry_px + be_at_r * risk:
            cur_sl = max(cur_sl, entry_px)
    return day.n - 1, day.c[-1], "TIME"


def _simulate_short(day, entry_i, entry_px, sl, tp_spec, time_stop=None):
    risk = sl - entry_px
    tp_abs = None
    if tp_spec[0] == "r":
        tp_abs = entry_px - tp_spec[1] * risk
    elif tp_spec[0] == "abs":
        tp_abs = tp_spec[1]
    for j in range(entry_i, min(day.n, FORCED + 1)):
        op = entry_px if j == entry_i else day.o[j]
        if j >= FORCED:
            return j, day.o[j], "TIME"
        if day.h[j] >= sl:
            return j, (op if op >= sl else sl), "SL"
        tp = tp_abs
        if tp_spec[0] == "vwap":
            tp = day.vwap[j] if day.vwap[j] and day.vwap[j] < entry_px else None
        if tp is not None and day.l[j] <= tp:
            return j, (op if op <= tp else tp), "TP"
        if tp_spec[0] == "fpc" and j > entry_i and day.c[j] < entry_px:
            return j, day.c[j], "TP"
        if time_stop is not None and j - entry_i >= time_stop:
            return j, day.c[j], "TIME"
    return day.n - 1, day.c[-1], "TIME"


def _make_trade(day, e, entry, sl, tp, be_at_r, time_stop, short=False):
    if short:
        xi, xp, xt = _simulate_short(day, e, entry, sl, tp, time_stop)
        raw_pnl = entry - xp
    else:
        xi, xp, xt = _simulate_long(day, e, entry, sl, tp, be_at_r, time_stop)
        raw_pnl = xp - entry
    pnl_pct = raw_pnl / entry * 100
    return {"day": day.date, "ei": e, "entry": entry, "sl": sl,
            "xi": xi, "xp": xp, "xt": xt, "pnl": raw_pnl, "pnl_pct": pnl_pct}


def run_market(days, signal_fn, c4=False, short=False):
    trades = []
    for day in days:
        pos_until = -1; consec_sl = 0
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
            if "sl_abs" in sig:
                sl = sig["sl_abs"]
            else:
                a = sig.get("atr5") if sig.get("atr5") is not None else day.atr[i]
                if a is None:
                    continue
                sl = (entry + sig["sl_atr"] * a) if short else (entry - sig["sl_atr"] * a)
            tp = sig["tp"]
            if tp[0] == "atrx":
                tp = ("abs", (entry - tp[1] * tp[2]) if short else (entry + tp[1] * tp[2]))
            if short and sl <= entry:
                continue
            if not short and sl >= entry:
                continue
            t = _make_trade(day, e, entry, sl, tp, sig.get("be_at_r"), sig.get("time_stop"), short)
            trades.append(t)
            pos_until = t["xi"]
            consec_sl = consec_sl + 1 if t["pnl_pct"] <= 0 else 0
    return trades


def run_fvg(days, filter_fn=None, c4=False, expiry=60, max_fills=None, short=False):
    """FVG long (gap alcista) o short (gap bajista). SL = 2 ticks del gap (ATR-relativo)."""
    trades = []
    for day in days:
        pending = None; pos_until = -1; consec_sl = 0; fills = 0
        tick = day.c[0] * 0.0001   # 0.01% del precio de open = ~$6 en BTC@60K
        for i in range(day.n):
            if i <= pos_until:
                pending = None; continue
            if pending is not None:
                filled = (not short and day.l[i] <= pending["px"]) or \
                         (short     and day.h[i] >= pending["px"])
                if filled:
                    entry = (min(day.o[i], pending["px"]) if not short
                             else max(day.o[i], pending["px"]))
                    sl = pending["sl"]
                    valid = (sl < entry) if not short else (sl > entry)
                    if valid:
                        t = _make_trade(day, i, entry, sl, ("r", 2.0), None, None, short)
                        trades.append(t)
                        pos_until = t["xi"]; fills += 1
                        consec_sl = consec_sl + 1 if t["pnl_pct"] <= 0 else 0
                    pending = None; continue
                expired = (i - pending["placed"] >= expiry) or (i > ENTRY_MAX + 10)
                cancel = (not short and (day.c[i] < pending["sl"] or expired)) or \
                         (short     and (day.c[i] > pending["sl"] or expired))
                if cancel:
                    pending = None
            if c4 and consec_sl >= 2:
                continue
            if max_fills is not None and fills >= max_fills:
                continue
            if pending is None and i >= 2 and ENTRY_MIN <= i + 1 <= ENTRY_MAX:
                if not short and day.l[i] > day.h[i-2]:   # gap alcista → long
                    if filter_fn is not None and not filter_fn(day, i):
                        continue
                    mid = (day.l[i] + day.h[i-2]) / 2
                    sl  = day.l[i-2] - 2 * tick
                    pending = {"px": mid, "sl": sl, "placed": i}
                elif short and day.h[i] < day.l[i-2]:      # gap bajista → short
                    if filter_fn is not None and not filter_fn(day, i):
                        continue
                    mid = (day.h[i] + day.l[i-2]) / 2
                    sl  = day.h[i-2] + 2 * tick
                    pending = {"px": mid, "sl": sl, "placed": i}
    return trades


# ── signal factories ──────────────────────────────────────────────────────────

def rsi2_dip(tp_mode, thresh=10, sl_mult=2.0, time_stop=45, require_above_pdl=False):
    def factory():
        def fn(day, i):
            if (i + 1) % 5 != 0: return None
            k = (i + 1) // 5 - 1
            if k < 15 or day.f_rsi2[k] is None or day.f_rsi2[k] >= thresh or day.f_atr[k] is None:
                return None
            if require_above_pdl and (day.pdl is None or day.c[i] <= day.pdl):
                return None
            a5 = day.f_atr[k]
            tp = ("fpc",) if tp_mode == "fpc" else ("atrx", tp_mode, a5)
            return {"sl_atr": sl_mult, "atr5": a5, "tp": tp, "time_stop": time_stop}
        return fn
    return factory


def rsi2_pop(tp_mode, thresh=85, sl_mult=1.0, time_stop=45, require_below_pdh=False):
    def factory():
        def fn(day, i):
            if (i + 1) % 5 != 0: return None
            k = (i + 1) // 5 - 1
            if k < 15 or day.f_rsi2[k] is None or day.f_rsi2[k] <= thresh or day.f_atr[k] is None:
                return None
            if require_below_pdh and (day.pdh is None or day.c[i] >= day.pdh):
                return None
            a5 = day.f_atr[k]
            tp = ("fpc",) if tp_mode == "fpc" else ("atrx", tp_mode, a5)
            return {"sl_atr": sl_mult, "atr5": a5, "tp": tp, "time_stop": time_stop}
        return fn
    return factory


def ibs_5m(tp_mode, thresh=0.15, sl_mult=2.0, time_stop=45):
    def factory():
        def fn(day, i):
            if (i + 1) % 5 != 0: return None
            k = (i + 1) // 5 - 1
            if k < 15 or day.f_atr[k] is None: return None
            rng = day.f_h[k] - day.f_l[k]
            if rng <= 0 or rng < day.f_atr[k]: return None
            if (day.f_c[k] - day.f_l[k]) / rng >= thresh: return None
            a5 = day.f_atr[k]
            tp = ("fpc",) if tp_mode == "fpc" else ("atrx", tp_mode, a5)
            return {"sl_atr": sl_mult, "atr5": a5, "tp": tp, "time_stop": time_stop}
        return fn
    return factory


def sweep_reclaim(tp, min_depth_atr=0.05, within=3):
    """SWP long: sweep session-low + reclaim con volumen. SL escalado a ATR."""
    def factory():
        def fn(day, i):
            if i < 5 or day.avgv5[i] is None or day.atr[i] is None: return None
            min_depth = min_depth_atr * day.atr[i]
            for j in range(max(1, i - within), i):
                pl = day.prev_low[j]
                if pl is None or day.l[j] >= pl - min_depth: continue
                sweep_low = min(day.l[j:i+1])
                if day.c[i] > pl and day.v[i] >= 1.5 * day.avgv5[i] and day.c[i] > day.o[i]:
                    buf = day.atr[i] * 0.05
                    return {"sl_abs": sweep_low - buf, "tp": tp}
            return None
        return fn
    return factory


def sweep_rejection(tp, min_depth_atr=0.05, within=3):
    """SWP short: sweep session-high + rejection con volumen."""
    def factory():
        def fn(day, i):
            if i < 5 or day.avgv5[i] is None or day.atr[i] is None: return None
            min_depth = min_depth_atr * day.atr[i]
            for j in range(max(1, i - within), i):
                ph = day.prev_high[j]
                if ph is None or day.h[j] <= ph + min_depth: continue
                sweep_high = max(day.h[j:i+1])
                if day.c[i] < ph and day.v[i] >= 1.5 * day.avgv5[i] and day.c[i] < day.o[i]:
                    buf = day.atr[i] * 0.05
                    return {"sl_abs": sweep_high + buf, "tp": tp}
            return None
        return fn
    return factory


def wick_reversal(tp, wick_thresh=0.6, sl_atr_frac=0.05, min_range_atr=0.1, min_rvol=None):
    def factory():
        def fn(day, i):
            if day.atr[i] is None: return None
            rng = day.h[i] - day.l[i]
            if rng < min_range_atr * day.atr[i]: return None
            if min_rvol is not None:
                if day.avgv5[i] is None or day.v[i] < min_rvol * day.avgv5[i]: return None
            lower_wick = min(day.o[i], day.c[i]) - day.l[i]
            if lower_wick / rng < wick_thresh: return None
            return {"sl_abs": day.l[i] - sl_atr_frac * day.atr[i], "tp": tp}
        return fn
    return factory


def wick_rejection_fade(tp, wick_thresh=0.6, sl_atr_frac=0.05, min_range_atr=0.1, min_rvol=None):
    def factory():
        def fn(day, i):
            if day.atr[i] is None: return None
            rng = day.h[i] - day.l[i]
            if rng < min_range_atr * day.atr[i]: return None
            if min_rvol is not None:
                if day.avgv5[i] is None or day.v[i] < min_rvol * day.avgv5[i]: return None
            upper_wick = day.h[i] - max(day.o[i], day.c[i])
            if upper_wick / rng < wick_thresh: return None
            return {"sl_abs": day.h[i] + sl_atr_frac * day.atr[i], "tp": tp}
        return fn
    return factory


def red_run(tp, run_len=5):
    def factory():
        def fn(day, i):
            if i < run_len + 1 or day.avgv20[i] is None or day.atr[i] is None: return None
            if not (day.c[i] > day.o[i] and day.v[i] >= day.avgv20[i]): return None
            for k in range(i - run_len, i):
                if day.c[k] >= day.o[k]: return None
            return {"sl_abs": min(day.l[i-run_len:i+1]) - 0.05 * day.atr[i], "tp": tp}
        return fn
    return factory


def vol_climax(tp):
    def factory():
        def fn(day, i):
            if day.avgv20[i] is None or day.atr[i] is None: return None
            rng = day.h[i] - day.l[i]
            if rng < day.atr[i] or day.v[i] < 4 * day.avgv20[i]: return None
            if min(day.o[i], day.c[i]) - day.l[i] < 0.55 * rng: return None
            if (day.c[i] - day.l[i]) / rng < 0.5: return None
            return {"sl_abs": day.l[i] - 0.05 * day.atr[i], "tp": tp}
        return fn
    return factory


def ema9_reclaim(tp):
    def factory():
        def fn(day, i):
            if (i < 31 or day.ema9[i] is None or day.ema9[i-1] is None
                    or day.slope30[i] is None or day.atr[i] is None): return None
            if day.slope30[i] <= 0 or day.c[i] <= day.vwap[i]: return None
            if day.c[i-1] < day.ema9[i-1] and day.c[i] > day.ema9[i]:
                return {"sl_atr": 2.0, "tp": tp}
            return None
        return fn
    return factory


def gap_fill(min_gap_frac=-0.003):
    """Gap-down vs PDC → long hacia PDC. min_gap_frac = fracción del precio."""
    def factory():
        fired = set()
        def fn(day, i):
            if day.pdc is None or day.date in fired or i < ENTRY_MIN: return None
            if (day.o[0] - day.pdc) / day.pdc > min_gap_frac: return None
            if day.ema9[i] is None or day.c[i] <= day.ema9[i] or day.c[i] >= day.pdc: return None
            fired.add(day.date)
            buf = (day.atr[i] or day.c[i] * 0.002) * 0.1
            return {"sl_abs": min(day.l[:i+1]) - buf, "tp": ("abs", day.pdc)}
        return fn
    return factory


def gap_fade(min_gap_frac=0.003):
    """Gap-up vs PDC → short hacia PDC."""
    def factory():
        fired = set()
        def fn(day, i):
            if day.pdc is None or day.date in fired or i < ENTRY_MIN: return None
            if (day.o[0] - day.pdc) / day.pdc < min_gap_frac: return None
            if day.ema9[i] is None or day.c[i] >= day.ema9[i] or day.c[i] <= day.pdc: return None
            fired.add(day.date)
            buf = (day.atr[i] or day.c[i] * 0.002) * 0.1
            return {"sl_abs": max(day.h[:i+1]) + buf, "tp": ("abs", day.pdc)}
        return fn
    return factory


def vwap_pullback(rsi_lo, rsi_hi, tp=("r", 1.0), be_at_r=None):
    def factory():
        def fn(day, i):
            if i < 15 or day.rsi14[i] is None or day.atr[i] is None: return None
            if day.c[i] <= day.vwap[i] or day.l[i] > day.vwap[i] * 1.001: return None
            if day.c[i] <= day.o[i] or not (rsi_lo <= day.rsi14[i] <= rsi_hi): return None
            return {"sl_atr": 2.0, "tp": tp, "be_at_r": be_at_r}
        return fn
    return factory


def vwap_rejection(rsi_lo, rsi_hi, tp=("r", 1.0)):
    def factory():
        def fn(day, i):
            if i < 15 or day.rsi14[i] is None or day.atr[i] is None: return None
            if day.c[i] >= day.vwap[i] or day.h[i] < day.vwap[i] * 0.999: return None
            if day.c[i] >= day.o[i] or not (rsi_lo <= day.rsi14[i] <= rsi_hi): return None
            return {"sl_atr": 2.0, "tp": tp}
        return fn
    return factory


def vwap_band(mult, tp):
    def factory():
        def fn(day, i):
            if i < 21 or day.sigma[i] is None or day.atr[i] is None: return None
            if day.sigma[i] < 0.005 * day.atr[i]: return None   # sigma mínimo ATR-relativo
            lb_prev = day.vwap[i-1] - mult * day.sigma[i-1]
            lb = day.vwap[i] - mult * day.sigma[i]
            if day.c[i-1] < lb_prev and day.c[i] > lb:
                buf = 0.05 * day.atr[i]
                return {"sl_abs": min(day.l[i-1], day.l[i]) - buf, "tp": tp}
            return None
        return fn
    return factory


def level_bounce(level_fn, buffer_sl_atr=0.1, tp=("r", 1.0), upper_frac=0.5,
                 cooldown=10, be_at_r=None):
    """Rebote en nivel clave (VPOC, VAL, PDL, PDC, VWAP 3d…). SL escalado a ATR."""
    def factory():
        last_sig: dict = {}
        def fn(day, i):
            levels = level_fn(day)
            rng = day.h[i] - day.l[i]
            if not levels or rng <= 0 or day.atr[i] is None: return None
            buf = buffer_sl_atr * day.atr[i]
            for lvv in levels:
                if lvv is None: continue
                key = round(lvv / day.c[i], 8)
                if (day.l[i] < lvv < day.c[i]
                        and (day.c[i] - day.l[i]) / rng >= upper_frac):
                    if key in last_sig and i - last_sig[key] < cooldown: continue
                    last_sig[key] = i
                    return {"sl_abs": min(day.l[i], lvv) - buf, "tp": tp, "be_at_r": be_at_r}
            return None
        return fn
    return factory


# ── estadísticas ──────────────────────────────────────────────────────────────

def stats(trades):
    """Métricas sobre pnl_pct (P/L en %, escala-neutral para BTC)."""
    n = len(trades)
    if n == 0: return None
    vals = [t["pnl_pct"] for t in trades]
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v <= 0]
    pnl = sum(vals)
    aw = sum(wins) / len(wins) if wins else 0.0
    al = sum(losses) / len(losses) if losses else 0.0
    pf = -sum(wins) / sum(losses) if losses else float("inf")
    mll = cur = 0
    for v in vals:
        cur = cur + 1 if v <= 0 else 0
        mll = max(mll, cur)
    mean = pnl / n
    var = sum((v - mean) ** 2 for v in vals) / n if n > 1 else 0.0
    se = math.sqrt(var / n) if n > 1 else 0.0
    return {"n": n, "w": len(wins), "hit": 100 * len(wins) / n,
            "pnl": pnl, "aw": aw, "al": al, "pf": pf, "mll": mll, "mean": mean, "se": se}


# ── carga de datos ────────────────────────────────────────────────────────────

def load_days(since: str = "2020-01-01") -> list[Day]:
    if not DATA_DIR.exists() or not list(DATA_DIR.glob("*.csv")):
        raise FileNotFoundError(
            f"Sin datos en {DATA_DIR}.\n"
            "Ejecuta primero: python tools/fetch_btc.py --rth-only"
        )
    bydate: dict[str, list] = {}
    for csv_path in sorted(DATA_DIR.glob("*.csv")):
        with csv_path.open() as f:
            for row in csv.DictReader(f):
                t = row["t"]
                if t[:10] < since: continue
                hm = t[11:16]
                if not ("13:30" <= hm < "20:00"): continue
                bydate.setdefault(t[:10], []).append({
                    "t": t, "o": float(row["o"]), "h": float(row["h"]),
                    "l": float(row["l"]), "c": float(row["c"]), "v": float(row["v"]),
                })
    days: list[Day] = []
    prev = None
    for d in sorted(bydate):
        bars = sorted(bydate[d], key=lambda b: b["t"])
        if len(bars) < 60: continue   # sesiones truncadas (holidays parciales) → skip
        day = Day(d, bars, prev)
        days.append(day); prev = day
    return days


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2020-01-01")
    ap.add_argument("--long-only",  action="store_true")
    ap.add_argument("--short-only", action="store_true")
    ap.add_argument("--top",  type=int, default=0, help="Mostrar top N por PF (0=todos)")
    ap.add_argument("--c4",        action="store_true")
    ap.add_argument("--portfolio", action="store_true", help="Analisis de portfolio RSI2+SWPs")
    a = ap.parse_args()

    print(f"Cargando BTC 1-min desde {DATA_DIR}/ (since={a.since})…")
    days = load_days(a.since)
    if not days:
        print("Sin sesiones. Revisa fetch_btc.py --rth-only")
        return
    print(f"Sesiones: {len(days)}  ({days[0].date} -> {days[-1].date})\n")

    # VWAP de los 3 días previos para level-bounce Y3VW
    for idx, day in enumerate(days):
        vws = []
        for pd_ in days[max(0, idx-3):idx]:
            pv = sum((pd_.h[i] + pd_.l[i] + pd_.c[i]) / 3 * pd_.v[i] for i in range(pd_.n))
            vws.append(pv / sum(pd_.v))
        day.prior3_vw = vws

    # ── roster de sistemas ──────────────────────────────────────────────────
    systems: list[tuple[str, str, object]] = []   # (name, side, runner_fn)

    def add_long(name, runner):
        if not a.short_only: systems.append((name, "L", runner))

    def add_short(name, runner):
        if not a.long_only: systems.append((name, "S", runner))

    def lmk(fac):
        """Envuelve un factory en un runner que acepta c4."""
        return lambda c4, f=fac: run_market(days, f(), c4)

    def smk(fac):
        return lambda c4, f=fac: run_market(days, f(), c4, short=True)

    # FVG
    add_long("FVG_base",   lambda c4: run_fvg(days, None, c4))
    add_long("FVG_trend",  lambda c4: run_fvg(
        days, lambda d, i: d.slope30[i] is not None and d.slope30[i] > 0 and d.c[i] > d.vwap[i], c4))
    add_long("FVG_f1",     lambda c4: run_fvg(days, None, c4, max_fills=1))
    add_long("FVG_f2",     lambda c4: run_fvg(days, None, c4, max_fills=2))
    add_long("FVG_f3",     lambda c4: run_fvg(days, None, c4, max_fills=3))
    add_short("FVGs_base", lambda c4: run_fvg(days, None, c4, short=True))
    add_short("FVGs_f2",   lambda c4: run_fvg(days, None, c4, max_fills=2, short=True))

    # RSI2
    for th in (5, 10, 15, 20):
        for sl in (1.0, 1.5, 2.0):
            add_long(f"RSI2_th{th}_sl{sl:.1f}x", lmk(rsi2_dip(0.5, thresh=th, sl_mult=sl)))
    add_long("RSI2_fpc",      lmk(rsi2_dip("fpc")))
    add_long("RSI2_fpc_ts15", lmk(rsi2_dip("fpc", sl_mult=1.5, time_stop=15)))
    add_long("RSI2_pdl_t05",  lmk(rsi2_dip(0.5, sl_mult=1.5, require_above_pdl=True)))
    for th in (80, 85, 90, 95):
        for sl in (1.0, 1.5, 2.0):
            add_short(f"RSI2p_th{th}_sl{sl:.1f}x", smk(rsi2_pop(0.5, thresh=th, sl_mult=sl)))
    add_short("RSI2p_fpc", smk(rsi2_pop("fpc")))

    # IBS
    add_long("IBS_fpc",      lmk(ibs_5m("fpc")))
    add_long("IBS_t05_s15",  lmk(ibs_5m(0.5, sl_mult=1.5)))
    add_long("IBS_t025_s10", lmk(ibs_5m(0.25, sl_mult=1.0)))

    # SWP long + short
    for depth in (0.05, 0.1, 0.3):
        for tp_r in (("fpc",), ("r", 0.5), ("r", 1.0)):
            tag = f"fpc" if tp_r[0] == "fpc" else f"{tp_r[1]:.1f}R"
            add_long( f"SWP_d{depth:.2f}_{tag}", lmk(sweep_reclaim(tp_r, depth)))
            add_short(f"SWPs_d{depth:.2f}_{tag}", smk(sweep_rejection(tp_r, depth)))

    # Wick reversal
    add_long( "WICK_1R",  lmk(wick_reversal(("r", 1.0))))
    add_long( "WICK_05R", lmk(wick_reversal(("r", 0.5))))
    add_short("WICKs_1R",  smk(wick_rejection_fade(("r", 1.0))))
    add_short("WICKs_05R", smk(wick_rejection_fade(("r", 0.5))))

    # Red run / vol climax / EMA9
    add_long("RED5_fpc",  lmk(red_run(("fpc",))))
    add_long("RED5_05R",  lmk(red_run(("r", 0.5))))
    add_long("VCW_vwap",  lmk(vol_climax(("vwap",))))
    add_long("E9RC_1R",   lmk(ema9_reclaim(("r", 1.0))))
    add_long("E9RC_05R",  lmk(ema9_reclaim(("r", 0.5))))

    # Gap fill / fade
    add_long( "GAPFILL", lmk(gap_fill()))
    add_short("GAPFADE",  smk(gap_fade()))

    # VWAP pullback/rejection
    add_long( "VWAPPB_45_65", lmk(vwap_pullback(45, 65)))
    add_long( "VWAPPB_be05",  lmk(vwap_pullback(45, 65, tp=("r", 1.0), be_at_r=0.5)))
    add_long( "VWAPPB_075R",  lmk(vwap_pullback(45, 65, tp=("r", 0.75))))
    add_short("VWAPrej_35_55", smk(vwap_rejection(35, 55)))
    add_short("VWAPrej_45_65", smk(vwap_rejection(45, 65)))

    # VWAP band
    add_long("VB20_1R",  lmk(vwap_band(2.0, ("r", 1.0))))
    add_long("VB20_05R", lmk(vwap_band(2.0, ("r", 0.5))))

    # Level bounces
    lv_fns = {
        "VAL":  lambda d: [d.y_val],
        "VPOC": lambda d: [d.y_vpoc],
        "PDL":  lambda d: [d.pdl],
        "PDC":  lambda d: [d.pdc],
        "KEY":  lambda d: [d.y_val, d.y_vpoc, d.pdl, d.pdc],
        "Y3VW": lambda d: d.prior3_vw,
    }
    for lvname, lvfn in lv_fns.items():
        for tp_r in (("r", 1.0), ("r", 0.5)):
            tag = f"{tp_r[1]:.1f}R"
            add_long(f"{lvname}_b_{tag}", lmk(level_bounce(lvfn, tp=tp_r)))

    # ── ejecución ──────────────────────────────────────────────────────────
    rows = []
    for name, side, runner in systems:
        try:
            t0 = runner(False)
            t4 = runner(True) if a.c4 else runner(True)
        except Exception as exc:
            print(f"  ERROR {name}: {exc}")
            continue
        s0, s4 = stats(t0), stats(t4)
        if s0 is None: continue
        rows.append((name, side, s0, s4))

    rows.sort(key=lambda r: (-(r[2]["pf"] if r[2]["pf"] != float("inf") else 999), -r[2]["n"]))
    if a.top:
        rows = rows[:a.top]

    hdr = (f"{'SYSTEM':<22}{'S':>2}{'N':>5}{'HIT%':>7}{'pnl%':>9}{'mean%':>8}"
           f"{'se':>6}{'avgW%':>7}{'avgL%':>7}{'PF':>6}{'mLL':>4}"
           f"  {'C4:N':>5}{'HIT%':>7}{'pnl%':>8}")
    print(hdr); print("-" * len(hdr))
    for name, side, s0, s4 in rows:
        pf_s = f"{s0['pf']:5.2f}" if s0["pf"] != float("inf") else "  inf"
        c4s = f"{s4['n']:>5}{s4['hit']:>7.1f}{s4['pnl']:>8.2f}" if s4 else "     -      -       -"
        print(f"{name:<22}{side:>2}{s0['n']:>5}{s0['hit']:>7.1f}{s0['pnl']:>9.2f}"
              f"{s0['mean']:>8.3f}{s0['se']:>6.3f}"
              f"{s0['aw']:>7.3f}{s0['al']:>7.3f}{pf_s}{s0['mll']:>4}"
              f"  {c4s}")

    print(f"\nTotal: {len(rows)} sistemas  |  pnl% = suma P/L en % (escala-neutral BTC)")
    print("PF = Profit Factor  |  mLL = max losing streak  |  C4 = con kill tras 2 perdidas\n")

    # ── grids de calibración (top candidatos LONG con PF>1, n≥30) ──────────
    cands_long = [r for r in rows if r[1] == "L" and r[2]["pf"] > 1.0 and r[2]["n"] >= 30]
    if cands_long:
        print("-- RSI2 grid BTC (umbral vs sl_mult, tp=0.5R) -------------------")
        print(f"  {'thresh':>8}", end="")
        for sl in (1.0, 1.5, 2.0):
            print(f"   sl={sl:.1f}:hit/pnl%/N", end="")
        print()
        for th in (5, 10, 15, 20):
            print(f"  th<{th:<4}", end="")
            for sl in (1.0, 1.5, 2.0):
                t = run_market(days, rsi2_dip(0.5, thresh=th, sl_mult=sl)(), False)
                s = stats(t)
                if s: print(f"   {s['hit']:5.1f}{s['pnl']:>+7.2f}{s['n']:>4}", end="")
                else:  print(f"       -      -   0", end="")
            print()

        print("\n-- SWP grid BTC (min_depth_atr vs tp) ---------------------------")
        print(f"  {'depth':>7}", end="")
        for tp_lbl, tp_val in (("fpc", ("fpc",)), ("0.5R", ("r", 0.5)), ("1.0R", ("r", 1.0))):
            print(f"   tp={tp_lbl}:hit/pnl%/N", end="")
        print()
        for depth in (0.05, 0.1, 0.3, 0.5):
            print(f"  d={depth:.2f} ", end="")
            for tp_lbl, tp_val in (("fpc", ("fpc",)), ("0.5R", ("r", 0.5)), ("1.0R", ("r", 1.0))):
                t = run_market(days, sweep_reclaim(tp_val, min_depth_atr=depth)(), False)
                s = stats(t)
                if s: print(f"   {s['hit']:5.1f}{s['pnl']:>+7.2f}{s['n']:>4}", end="")
                else:  print(f"       -      -   0", end="")
            print()

    if a.portfolio:
        portfolio_analysis(days)


def portfolio_analysis(days):
    """Combina RSI2-long + SWPs-short y evalúa el portfolio conjunto.

    Permite posiciones simultáneas (long + short a la vez) — en BTC no hay
    restricción long/short. Mide: PF combinado, correlación diaria, drawdown.
    """
    # Configuraciones candidatas
    configs_long  = [
        ("RSI2_th5_sl2",  rsi2_dip(0.5, thresh=5,  sl_mult=2.0)()),
        ("RSI2_th10_sl2", rsi2_dip(0.5, thresh=10, sl_mult=2.0)()),
        ("RSI2_th15_sl2", rsi2_dip(0.5, thresh=15, sl_mult=2.0)()),
        ("IBS_t05_s15",   ibs_5m(0.5, sl_mult=1.5)()),
    ]
    configs_short = [
        ("SWPs_d030_fpc", sweep_rejection(("fpc",), min_depth_atr=0.30)()),
        ("SWPs_d010_fpc", sweep_rejection(("fpc",), min_depth_atr=0.10)()),
    ]

    print("\n" + "=" * 70)
    print("PORTFOLIO ANALYSIS: RSI2/IBS long + SWPs short (posiciones simultaneas)")
    print("=" * 70)
    print(f"\n{'LONG':>18}  +  {'SHORT':<18}  {'N_L':>5}{'N_S':>5}{'N_tot':>6}"
          f"{'HIT%':>7}{'PF':>6}{'pnl%':>8}{'maxDD%':>8}{'overlap%':>9}")
    print("-" * 95)

    best_pf = 0.0
    best_combo = None

    for lname, lfn in configs_long:
        lt = run_market(days, lfn, c4=False)
        for sname, sfn in configs_short:
            st = run_market(days, sfn, c4=False, short=True)

            # Construir serie de P/L diaria (permite simultaneidad)
            all_trades = lt + st
            if not all_trades:
                continue
            all_trades.sort(key=lambda t: (t["day"], t["ei"]))

            # Overlap: fracción de días donde ambos sistemas tienen trades
            days_l  = {t["day"] for t in lt}
            days_s  = {t["day"] for t in st}
            overlap = len(days_l & days_s) / max(len(days_l | days_s), 1) * 100

            # Stats combinadas (por trade, no por día)
            sc = stats(all_trades)
            if sc is None:
                continue

            # Max drawdown en % acumulado
            cumulative = 0.0
            peak = 0.0
            max_dd = 0.0
            for t in all_trades:
                cumulative += t["pnl_pct"]
                peak = max(peak, cumulative)
                max_dd = max(max_dd, peak - cumulative)

            pf_s = f"{sc['pf']:5.2f}" if sc["pf"] != float("inf") else "  inf"
            print(f"{lname:>18}  +  {sname:<18}  {len(lt):>5}{len(st):>5}{sc['n']:>6}"
                  f"{sc['hit']:>7.1f}{pf_s}{sc['pnl']:>8.2f}{max_dd:>8.2f}{overlap:>9.1f}")

            if sc["pf"] > best_pf and sc["n"] >= 200:
                best_pf = sc["pf"]; best_combo = (lname, sname, lt, st, sc, max_dd)

    # Detalle día-a-día del mejor combo
    if best_combo:
        lname, sname, lt, st, sc, max_dd = best_combo
        print(f"\n>> Mejor combo: {lname} + {sname}  PF={sc['pf']:.2f}  n={sc['n']}")
        print(f"   Hit={sc['hit']:.1f}%  pnl%={sc['pnl']:+.2f}  maxDD={max_dd:.2f}%  mLL={sc['mll']}")

        # Correlación por día: ¿pierden los mismos días?
        daily_l: dict = {}
        daily_s: dict = {}
        for t in lt:  daily_l.setdefault(t["day"], []).append(t["pnl_pct"])
        for t in st:  daily_s.setdefault(t["day"], []).append(t["pnl_pct"])
        common_days = sorted(daily_l.keys() & daily_s.keys())
        if len(common_days) >= 10:
            pairs = [(sum(daily_l[d]), sum(daily_s[d])) for d in common_days]
            ml = sum(p[0] for p in pairs) / len(pairs)
            ms = sum(p[1] for p in pairs) / len(pairs)
            cov = sum((p[0] - ml) * (p[1] - ms) for p in pairs) / len(pairs)
            sl_ = math.sqrt(sum((p[0] - ml)**2 for p in pairs) / len(pairs))
            ss_ = math.sqrt(sum((p[1] - ms)**2 for p in pairs) / len(pairs))
            corr = cov / (sl_ * ss_) if sl_ > 0 and ss_ > 0 else 0.0
            print(f"   Correlacion diaria (dias con ambos activos, n={len(common_days)}): r={corr:+.3f}")
            if corr < -0.1:
                print("   -> Complementarios: el short compensa perdidas del long")
            elif corr < 0.1:
                print("   -> Independientes: sin correlacion significativa")
            else:
                print("   -> Positivamente correlacionados (riesgo conjunto)")

        # Resumen por año
        print(f"\n   Breakdown por año (long={lname}, short={sname}):")
        print(f"   {'Año':>6}  {'N_L':>5}{'N_S':>5}  {'pnl_L%':>8}{'pnl_S%':>8}{'pnl_tot%':>10}{'PF_tot':>8}")
        for yr in range(2021, 2027):
            ys = str(yr)
            tl_y = [t for t in lt if t["day"][:4] == ys]
            ts_y = [t for t in st if t["day"][:4] == ys]
            ta_y = tl_y + ts_y
            if not ta_y: continue
            sl_y = stats(tl_y); ss_y = stats(ts_y); sa_y = stats(ta_y)
            pnl_l = sl_y["pnl"] if sl_y else 0.0
            pnl_s = ss_y["pnl"] if ss_y else 0.0
            pf_y  = f"{sa_y['pf']:.2f}" if sa_y and sa_y["pf"] != float("inf") else "inf"
            print(f"   {ys:>6}  {len(tl_y):>5}{len(ts_y):>5}  "
                  f"{pnl_l:>+8.2f}{pnl_s:>+8.2f}{pnl_l+pnl_s:>+10.2f}{pf_y:>8}")


if __name__ == "__main__":
    main()
