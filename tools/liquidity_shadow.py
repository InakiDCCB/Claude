"""Liquidity Wick Reversal (LWR) shadow — batch diario para /post-close (2026-07-31).

LONG only (SHORT descartado en calibracion: KILLED en las 96 celdas del grid con y sin
gate de volumen — ver tools/calibrate_lwr.py). Config unica candidata: mecha inferior
>= 0.60*range de la vela + volumen >= 3x avgv5(1min) -> fade alcista. SL = low de la
vela de rechazo - 0.05 ; TP = 0.5R. Calibracion (72 sesiones 2026-04-20..07-31):
n=79, hit 72.2%, PF 1.49, Horizon Score 60.1/100 (PAPER — bajo el listón DEPLOY 65,
n delgado). Detalle y decision de alcance en memoria project_liquidity_wick_reversal.

A diferencia de TD9S, la señal opera directo sobre 1-min crudo del DIA (no cruza
sesiones) — solo hace falta fetchear el dia objetivo.

Uso: python liquidity_shadow.py 2026-07-31 --json
"""
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

from backtest import Day, simulate

WICK_THRESH = 0.60
MIN_RVOL = 3.0
MIN_RANGE = 0.02
TP_R = 0.5
SL_BUFFER = 0.05


def fetch_bars(date):
    env = json.loads((Path(__file__).parents[1] / ".mcp.json").read_text())["mcpServers"]["alpaca"]["env"]
    hdr = {"APCA-API-KEY-ID": env["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": env["ALPACA_SECRET_KEY"]}
    params = {"symbols": "QQQ", "timeframe": "1Min", "start": f"{date}T13:30:00Z",
              "end": f"{date}T20:00:00Z", "limit": "10000", "feed": "iex", "adjustment": "raw"}
    bars, token = [], None
    while True:
        q = dict(params)
        if token:
            q["page_token"] = token
        url = "https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(q)
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=30) as r:
            resp = json.loads(r.read())
        bars += resp.get("bars", {}).get("QQQ", [])
        token = resp.get("next_page_token")
        if not token:
            break
    return [b for b in bars if "13:30" <= b["t"][11:16] < "20:00"]


def lwr_shadow(date):
    bars = fetch_bars(date)
    if not bars:
        return []
    day = Day(date, bars, prev=None)
    out, busy_until = [], -1
    for i in range(day.n - 1):
        rng = day.h[i] - day.l[i]
        if rng < MIN_RANGE:
            continue
        if day.avgv5[i] is None or day.v[i] < MIN_RVOL * day.avgv5[i]:
            continue
        lower_wick = min(day.o[i], day.c[i]) - day.l[i]
        wr = lower_wick / rng
        if wr < WICK_THRESH:
            continue
        e = i + 1
        rvol = day.v[i] / day.avgv5[i]
        if e <= busy_until:
            out.append({"sys": "LWR", "dir": "long", "date": date, "entry": round(day.o[e], 2),
                        "outcome": "skip_overlap", "pnl_ps": 0.0,
                        "note": f"LWR wick={wr:.2f} rvol={rvol:.1f}x solapada"})
            continue
        entry = day.o[e]
        sl = round(day.l[i] - SL_BUFFER, 2)
        if sl >= entry:
            continue
        tp = round(entry + TP_R * (entry - sl), 2)
        xi, xp, xt = simulate(day, e, entry, sl, ("abs", tp))
        busy_until = xi
        out.append({"sys": "LWR", "dir": "long", "date": date, "entry": round(entry, 2),
                    "sl": sl, "tp": tp, "outcome": xt, "pnl_ps": round(xp - entry, 3),
                    "note": f"LWR wick={wr:.2f} rvol={rvol:.1f}x -> {xt}"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    out = lwr_shadow(a.date)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print(f"LWR shadow {a.date}: {len(out)} señales")
    for o in out:
        print(f"  {o['note']} pnl={o['pnl_ps']:+.2f}/sh")


if __name__ == "__main__":
    main()
