"""BTC shadow batch — IBS_btc_v1 (long) + SWPs_btc_v1 (short) para /post-close.

Config validada en backtest 2021-2026 (2073 sesiones, ventana NY 09:30-16:00 ET):
  IBS_btc_v1:  IBS(5m) < 0.15 (close en fondo del rango) -> long. sl=1.5xATR5m, ts=45min.
               PF=1.34, hit=75.1%, n=7524 sesiones (promedio ~3.6 señales/día).
  SWPs_btc_v1: sweep session-high + rechazo con volumen >= 1.5x avgv5. tp=FPC.
               PF=1.24, hit=73.0%, min_depth=0.30xATR.
  Portfolio combinado: PF=1.33, r=-0.016 (independientes), positivo 5/6 años.

Pnl reportado en % del precio de entrada (escala-neutral BTC).

Uso:
    python btc_shadow.py 2026-09-04 --json
    python btc_shadow.py 2026-09-04            # output legible
"""
import argparse
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

# ── config única validada ─────────────────────────────────────────────────────
IBS_THRESH     = 0.15     # close dentro del 15% inferior del rango de la vela 5m
IBS_SL_MULT    = 1.5      # SL = entry - 1.5 × ATR5m
IBS_TP_MULT    = 0.5      # TP = entry + 0.5 × ATR5m  (atrx)
IBS_TIME_STOP  = 45       # barras 1-min máx en posición
SWPS_MIN_DEPTH = 0.30     # sweep depth mínimo = 0.30 × ATR
SWPS_WITHIN    = 3        # barras 1-min de ventana para buscar el sweep
SWPS_VOL_MULT  = 1.5      # volumen mínimo del bar de rechazo = 1.5 × avgv5

ENTRY_MIN = 30            # bar 30 = 10:00 ET
ENTRY_MAX = 375           # bar 375 = 15:45 ET
FORCED    = 385           # bar 385 = 15:55 ET (forced close)


# ── fetch ─────────────────────────────────────────────────────────────────────

def fetch_btc_bars(date: str) -> list:
    env = json.loads((Path(__file__).parents[1] / ".mcp.json").read_text()
                     )["mcpServers"]["alpaca"]["env"]
    hdr = {"APCA-API-KEY-ID": env["ALPACA_API_KEY"],
           "APCA-API-SECRET-KEY": env["ALPACA_SECRET_KEY"]}
    params = {"symbols": "BTC/USD", "timeframe": "1Min",
              "start": f"{date}T13:30:00Z", "end": f"{date}T20:00:00Z",
              "limit": "10000"}
    bars, token = [], None
    while True:
        q = dict(params)
        if token:
            q["page_token"] = token
        url = "https://data.alpaca.markets/v1beta3/crypto/us/bars?" + urllib.parse.urlencode(q)
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=hdr), timeout=30) as r:
            resp = json.loads(r.read())
        bars += resp.get("bars", {}).get("BTC/USD", [])
        token = resp.get("next_page_token")
        if not token:
            break
    return [b for b in bars if "13:30" <= b["t"][11:16] < "20:00"]


# ── indicadores mínimos ───────────────────────────────────────────────────────

def _wilder_rsi(closes, n):
    if len(closes) < n + 1:
        return [None] * len(closes)
    rsi = [None] * len(closes)
    gains = losses = 0.0
    for k in range(1, n + 1):
        d = closes[k] - closes[k-1]
        gains += max(d, 0); losses += max(-d, 0)
    ag, al = gains / n, losses / n
    rsi[n] = 100 - 100 / (1 + (ag / al if al else 1e9))
    for k in range(n+1, len(closes)):
        d = closes[k] - closes[k-1]
        ag = (ag * (n-1) + max(d, 0)) / n
        al = (al * (n-1) + max(-d, 0)) / n
        rsi[k] = 100 - 100 / (1 + (ag / al if al else 1e9))
    return rsi


def _wilder_atr(h, l, c, n=14):
    m = len(c)
    atr = [None] * m
    trs = [h[0] - l[0]] + [max(h[k]-l[k], abs(h[k]-c[k-1]), abs(l[k]-c[k-1]))
                            for k in range(1, m)]
    if m <= n:
        return atr
    a = sum(trs[1:n+1]) / n
    atr[n] = a
    for k in range(n+1, m):
        a = (a * (n-1) + trs[k]) / n
        atr[k] = a
    return atr


class _Day:
    """Precomputa solo lo necesario para IBS y SWPs."""
    def __init__(self, date, bars):
        self.date = date
        self.o = [b["o"] for b in bars]
        self.h = [b["h"] for b in bars]
        self.l = [b["l"] for b in bars]
        self.c = [b["c"] for b in bars]
        self.v = [b["v"] for b in bars]
        self.n = n = len(bars)
        # ATR 1-min (para SWPs min_depth)
        self.atr = _wilder_atr(self.h, self.l, self.c, 14)
        # avgv5 1-min (volumen promedio 5 barras)
        self.avgv5 = [None] * n
        for i in range(5, n):
            self.avgv5[i] = sum(self.v[i-5:i]) / 5
        # session_high / prev_high acumulado (para SWPs)
        self.prev_high = [None] * n
        hi = float("-inf")
        for i in range(n):
            self.prev_high[i] = hi if hi != float("-inf") else None
            hi = max(hi, self.h[i])
        # barras 5-min por resampleo
        fh, fl, fc = [], [], []
        for k in range(0, n - 4, 5):
            fh.append(max(self.h[k:k+5]))
            fl.append(min(self.l[k:k+5]))
            fc.append(self.c[k+4])
        self.f_h, self.f_l, self.f_c = fh, fl, fc
        self.f_atr = _wilder_atr(fh, fl, fc, 14)
        self.nf = len(fc)


# ── simulación ────────────────────────────────────────────────────────────────

def _sim_long(day, entry_i, entry_px, sl, tp_spec, time_stop=None):
    risk = entry_px - sl
    tp_abs = None
    if tp_spec[0] == "r":
        tp_abs = entry_px + tp_spec[1] * risk
    elif tp_spec[0] == "abs":
        tp_abs = tp_spec[1]
    for j in range(entry_i, min(day.n, FORCED + 1)):
        op = entry_px if j == entry_i else day.o[j]
        if j >= FORCED:
            return j, day.o[j], "TIME"
        if day.l[j] <= sl:
            return j, (op if op <= sl else sl), "SL"
        if tp_abs is not None and day.h[j] >= tp_abs:
            return j, (op if op >= tp_abs else tp_abs), "TP"
        if tp_spec[0] == "fpc" and j > entry_i and day.c[j] > entry_px:
            return j, day.c[j], "TP"
        if time_stop is not None and j - entry_i >= time_stop:
            return j, day.c[j], "TIME"
    return day.n - 1, day.c[-1], "TIME"


def _sim_short(day, entry_i, entry_px, sl, tp_spec, time_stop=None):
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
        if tp_abs is not None and day.l[j] <= tp_abs:
            return j, (op if op <= tp_abs else tp_abs), "TP"
        if tp_spec[0] == "fpc" and j > entry_i and day.c[j] < entry_px:
            return j, day.c[j], "TP"
        if time_stop is not None and j - entry_i >= time_stop:
            return j, day.c[j], "TIME"
    return day.n - 1, day.c[-1], "TIME"


# ── señales ───────────────────────────────────────────────────────────────────

def _ibs_signals(day):
    """IBS_btc_v1: IBS(5m) < THRESH, sl=SL_MULT*ATR5m, tp=TP_MULT*ATR5m, ts=TIME_STOP."""
    trades = []
    busy_until = -1
    for k in range(day.nf):
        i = k * 5 + 4     # barra 1-min sellada del bloque 5-min
        if not (ENTRY_MIN <= i + 1 <= ENTRY_MAX):
            continue
        if day.f_atr[k] is None:
            continue
        rng = day.f_h[k] - day.f_l[k]
        if rng <= 0 or rng < day.f_atr[k]:
            continue
        ibs = (day.f_c[k] - day.f_l[k]) / rng
        if ibs >= IBS_THRESH:
            continue
        e = i + 1
        if e <= busy_until:
            trades.append({"sys": "IBS_BTC", "dir": "long", "date": day.date,
                           "entry": round(day.o[e], 2),
                           "outcome": "skip_overlap", "pnl_pct": 0.0,
                           "note": f"IBS_BTC ibs={ibs:.3f} solapada"})
            continue
        entry = day.o[e]
        a5 = day.f_atr[k]
        sl = entry - IBS_SL_MULT * a5
        if sl >= entry:
            continue
        xi, xp, xt = _sim_long(day, e, entry, sl, ("abs", entry + IBS_TP_MULT * a5),
                                time_stop=IBS_TIME_STOP)
        busy_until = xi
        pnl_pct = round((xp - entry) / entry * 100, 4)
        trades.append({"sys": "IBS_BTC", "dir": "long", "date": day.date,
                       "entry": round(entry, 2), "sl": round(sl, 2),
                       "tp": round(entry + IBS_TP_MULT * a5, 2),
                       "outcome": xt, "pnl_pct": pnl_pct,
                       "note": f"IBS_BTC ibs={ibs:.3f} atr5={a5:.1f} -> {xt}"})
    return trades


def _swps_signals(day):
    """SWPs_btc_v1: sweep session-high + rechazo (vol >= 1.5xavgv5). tp=FPC."""
    trades = []
    busy_until = -1
    for i in range(5, day.n - 1):
        if not (ENTRY_MIN <= i + 1 <= ENTRY_MAX):
            continue
        if day.avgv5[i] is None or day.atr[i] is None:
            continue
        min_depth = SWPS_MIN_DEPTH * day.atr[i]
        swept = False
        sweep_high = float("-inf")
        for j in range(max(1, i - SWPS_WITHIN), i):
            ph = day.prev_high[j]
            if ph is None or day.h[j] <= ph + min_depth:
                continue
            # sweep confirmado: h[j] supera prev_high + min_depth
            sweep_high = max(sweep_high, max(day.h[j:i+1]))
            swept = True
            break
        if not swept:
            continue
        # rechazo: bar actual cierra debajo del prev_high previo, roja, con volumen
        ph_now = day.prev_high[i]
        if ph_now is None:
            continue
        if not (day.c[i] < ph_now and day.v[i] >= SWPS_VOL_MULT * day.avgv5[i]
                and day.c[i] < day.o[i]):
            continue
        e = i + 1
        if e <= busy_until:
            trades.append({"sys": "SWPS_BTC", "dir": "short", "date": day.date,
                           "entry": round(day.o[e], 2),
                           "outcome": "skip_overlap", "pnl_pct": 0.0,
                           "note": f"SWPS_BTC sweep_high={sweep_high:.1f} solapada"})
            continue
        entry = day.o[e]
        buf = day.atr[i] * 0.05
        sl = sweep_high + buf
        if sl <= entry:
            continue
        xi, xp, xt = _sim_short(day, e, entry, sl, ("fpc",))
        busy_until = xi
        pnl_pct = round((entry - xp) / entry * 100, 4)
        trades.append({"sys": "SWPS_BTC", "dir": "short", "date": day.date,
                       "entry": round(entry, 2), "sl": round(sl, 2),
                       "outcome": xt, "pnl_pct": pnl_pct,
                       "note": f"SWPS_BTC sweep={sweep_high:.1f} -> {xt}"})
    return trades


# ── main ──────────────────────────────────────────────────────────────────────

def btc_shadow(date: str) -> list:
    bars = fetch_btc_bars(date)
    if not bars:
        return []
    day = _Day(date, bars)
    return _ibs_signals(day) + _swps_signals(day)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", help="YYYY-MM-DD (ET)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    out = btc_shadow(a.date)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    ibs = [o for o in out if o["sys"] == "IBS_BTC" and o["outcome"] != "skip_overlap"]
    swps = [o for o in out if o["sys"] == "SWPS_BTC" and o["outcome"] != "skip_overlap"]
    print(f"BTC shadow {a.date}: {len(ibs)} IBS + {len(swps)} SWPS senales")
    for o in out:
        skip = " (skip)" if o["outcome"] == "skip_overlap" else ""
        pct = f"pnl={o['pnl_pct']:+.3f}%" if o.get("pnl_pct") is not None else ""
        print(f"  {o['note']}{skip} {pct}")


if __name__ == "__main__":
    main()
