"""GT-0 — Fundación de datos Golden Ticket (2026-07-03, decisión usuario: 20 años).

Dos niveles (la realidad de los datos, documentada en golden_ticket_research.md):
  - DIARIO 20+ años (QQQ desde 1999 + SPY/TLT/VIX como FEATURES — solo QQQ es operable):
    Stooq CSV público (sin API key). -> data/gt_daily_<sym>.csv
  - INTRADÍA 1-min QQQ: todo lo que Alpaca tiene (SIP histórico, ~2016+), paginado.
    -> data/gt_qqq_1min_<year>.csv.gz  (t,o,h,l,c,v)

Uso:  python gt_fetch_data.py --daily        (rápido, ~4 requests)
      python gt_fetch_data.py --intraday     (~100+ páginas, correr en background)
"""
import argparse
import csv
import gzip
import io
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)

_env = json.loads((Path(__file__).parents[2] / ".mcp.json").read_text())["mcpServers"]["alpaca"]["env"]
HEADERS = {"APCA-API-KEY-ID": _env["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": _env["ALPACA_SECRET_KEY"]}
DATA_BASE = "https://data.alpaca.markets"

# Yahoo chart v8 (Stooq quedó tras un muro JS 07-03). period1=922000000 ≈ 1999-03.
YAHOO = {"qqq": "QQQ", "spy": "SPY", "tlt": "TLT", "vix": "%5EVIX"}


def fetch_daily():
    import datetime
    for name, sym in YAHOO.items():
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
               f"?period1=922000000&period2={int(time.time())}&interval=1d")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.loads(r.read().decode())["chart"]["result"][0]
        except Exception as e:
            print(f"{name}: FALLO ({e}) — features de {name} quedarán fuera")
            continue
        ts, q = res["timestamp"], res["indicators"]["quote"][0]
        lines = ["date,open,high,low,close,volume"]
        for i, t in enumerate(ts):
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            if None in (o, h, l, c):
                continue
            d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date()
            v = q["volume"][i] or 0
            lines.append(f"{d},{o:.4f},{h:.4f},{l:.4f},{c:.4f},{v}")
        if len(lines) < 100:
            print(f"{name}: respuesta sospechosa ({len(lines)} filas)")
            continue
        p = OUT / f"gt_daily_{name}.csv"
        p.write_text("\n".join(lines) + "\n")
        print(f"{name}: {len(lines)-1} filas diarias ({lines[1][:10]} -> {lines[-1][:10]}) -> {p.name}")
        time.sleep(1)


def fetch_intraday(start="2016-01-01"):
    total, year_rows, cur_year = 0, [], None

    def flush(year, rows):
        if not rows:
            return
        p = OUT / f"gt_qqq_1min_{year}.csv.gz"
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["t", "o", "h", "l", "c", "v"])
        w.writerows(rows)
        with gzip.open(p, "wt", newline="") as f:
            f.write(buf.getvalue())
        print(f"  {year}: {len(rows)} barras -> {p.name}", flush=True)

    token = None
    while True:
        q = {"symbols": "QQQ", "timeframe": "1Min", "start": f"{start}T09:00:00Z",
             "limit": "10000", "feed": "sip", "adjustment": "split"}
        if token:
            q["page_token"] = token
        url = DATA_BASE + "/v2/stocks/bars?" + urllib.parse.urlencode(q)
        req = urllib.request.Request(url, headers=HEADERS)
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.loads(r.read().decode())
                break
            except Exception as e:
                if attempt == 3:
                    raise
                time.sleep(3 * (attempt + 1))
        bars = data.get("bars", {}).get("QQQ", [])
        for b in bars:
            y = b["t"][:4]
            if cur_year is None:
                cur_year = y
            if y != cur_year:
                flush(cur_year, year_rows)
                year_rows, cur_year = [], y
            year_rows.append([b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]])
        total += len(bars)
        token = data.get("next_page_token")
        if not token:
            break
        time.sleep(0.35)   # margen sobre el rate limit
    flush(cur_year, year_rows)
    print(f"TOTAL: {total} barras 1-min QQQ (SIP, desde {start})", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--intraday", action="store_true")
    ap.add_argument("--start", default="2016-01-01")
    a = ap.parse_args()
    if a.daily:
        fetch_daily()
    if a.intraday:
        fetch_intraday(a.start)
