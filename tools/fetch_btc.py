"""Fetch BTC/USD 1-min bars from Alpaca crypto feed (v1beta3).

Guarda un CSV por año en tools/data/btc_1min/YYYY.csv con columnas t,o,h,l,c,v.
Por defecto descarga datos completos 24/7; --rth-only filtra a la ventana NY (09:30-16:00 ET
= 13:30-20:00 UTC) para comparabilidad directa con QQQ.

Uso:
    python fetch_btc.py                          # 2020-hoy, 24/7
    python fetch_btc.py --since 2018             # desde 2018
    python fetch_btc.py --rth-only               # solo ventana NY
    python fetch_btc.py --skip-existing          # saltar años ya descargados
"""
import argparse
import csv
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_env = json.loads((Path(__file__).parents[1] / ".mcp.json").read_text())["mcpServers"]["alpaca"]["env"]
HEADERS = {"APCA-API-KEY-ID": _env["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": _env["ALPACA_SECRET_KEY"]}
DATA_BASE = "https://data.alpaca.markets"
SYMBOL = "BTC/USD"
OUT_DIR = Path(__file__).parent / "data" / "btc_1min"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def get(url, retries=5):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise


def fetch_year(year, end_cap, rth_only=False):
    start = f"{year}-01-01T00:00:00Z"
    end = min(f"{year}-12-31T23:59:59Z", end_cap)
    params = {
        "symbols": SYMBOL,
        "timeframe": "1Min",
        "start": start,
        "end": end,
        "limit": "10000",
    }
    token, n, pages = None, 0, 0
    out_path = OUT_DIR / f"{year}.csv"
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "o", "h", "l", "c", "v"])
        while True:
            q = dict(params)
            if token:
                q["page_token"] = token
            url = DATA_BASE + "/v1beta3/crypto/us/bars?" + urllib.parse.urlencode(q)
            resp = get(url)
            bars = resp.get("bars", {}).get(SYMBOL, [])
            for b in bars:
                if rth_only:
                    hm = b["t"][11:16]
                    if not ("13:30" <= hm < "20:00"):
                        continue
                w.writerow([b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]])
                n += 1
            token = resp.get("next_page_token")
            pages += 1
            if not token:
                break
            time.sleep(0.1)   # crypto feed generous pero evitar 429 en años con muchas páginas
    return n, pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=2020)
    ap.add_argument("--until", type=int, default=dt.datetime.now(dt.timezone.utc).year)
    ap.add_argument("--rth-only", action="store_true", help="Solo ventana NY 09:30-16:00 ET")
    ap.add_argument("--skip-existing", action="store_true")
    a = ap.parse_args()

    end_cap = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

    total = 0
    for year in range(a.since, a.until + 1):
        out_path = OUT_DIR / f"{year}.csv"
        if a.skip_existing and out_path.exists():
            size = out_path.stat().st_size
            print(f"{year}: skip (exists, {size//1024}KB)")
            continue
        t0 = time.time()
        try:
            n, pages = fetch_year(year, end_cap, rth_only=a.rth_only)
        except Exception as e:
            print(f"{year}: ERROR {e}")
            continue
        total += n
        print(f"{year}: {n:>8} bars  {pages:>4} pages  {time.time()-t0:>6.1f}s  -> {out_path}")

    mode = "RTH-only" if a.rth_only else "24/7"
    print(f"\nTOTAL: {total:,} bars ({mode}) -> {OUT_DIR}")


if __name__ == "__main__":
    main()
