"""Fetch QQQ full 1-min history (SIP, RTH only) year by year, since Alpaca's data starts
2016-01-04 (verified empirically -- see tools/fetch_daily_full.py). Saves one CSV per year to
tools/data/qqq_1min/YYYY.csv (t,o,h,l,c,v,vw) -- gitignored, regenerable, streamable (no single
huge JSON blob to load into memory).

Uso: python fetch_1min_full.py [--since 2016] [--until 2026] [--skip-existing]
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
OUT_DIR = Path(__file__).parent / "data" / "qqq_1min"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def get(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            raise


def fetch_year(symbol, year, end_cap):
    start = f"{year}-01-01T00:00:00Z"
    end = min(f"{year}-12-31T23:59:59Z", end_cap)
    params = {"symbols": symbol, "timeframe": "1Min", "start": start, "end": end,
              "limit": "10000", "feed": "sip", "adjustment": "split"}
    token, n, pages = None, 0, 0
    out_path = OUT_DIR / f"{year}.csv"
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "o", "h", "l", "c", "v", "vw"])
        while True:
            q = dict(params)
            if token:
                q["page_token"] = token
            url = DATA_BASE + "/v2/stocks/bars?" + urllib.parse.urlencode(q)
            resp = get(url)
            bars = resp.get("bars", {}).get(symbol, [])
            for b in bars:
                # RTH only (13:30-20:00 UTC) -- pre/post market is noise for this research
                hm = b["t"][11:16]
                if "13:30" <= hm < "20:00":
                    w.writerow([b["t"], b["o"], b["h"], b["l"], b["c"], b["v"], b.get("vw", "")])
                    n += 1
            token = resp.get("next_page_token")
            pages += 1
            if not token:
                break
    return n, pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=2016)
    ap.add_argument("--until", type=int, default=dt.datetime.now(dt.timezone.utc).year)
    ap.add_argument("--skip-existing", action="store_true")
    a = ap.parse_args()

    end_cap = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=16)).strftime("%Y-%m-%dT%H:%M:%SZ")

    total = 0
    for year in range(a.since, a.until + 1):
        out_path = OUT_DIR / f"{year}.csv"
        if a.skip_existing and out_path.exists():
            print(f"{year}: skip (exists)")
            continue
        t0 = time.time()
        n, pages = fetch_year("QQQ", year, end_cap)
        total += n
        print(f"{year}: {n} bars, {pages} pages, {time.time()-t0:.1f}s -> {out_path}")

    print(f"TOTAL: {total} bars across {a.until - a.since + 1} years -> {OUT_DIR}")


if __name__ == "__main__":
    main()
