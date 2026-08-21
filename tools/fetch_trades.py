"""Fetch QQQ 1-min tick-level trades (feed=iex) for Order Flow Indicator (OFI) calibration.
Saves to tools/data/qqq_trades.json — list of {t,p,s,x,c} per trade, RTH only (13:30-20:00 UTC).

Uso: python fetch_trades.py [--since 2026-04-20] [--until 2026-08-11]
"""
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

_env = json.loads((Path(__file__).parents[1] / ".mcp.json").read_text())["mcpServers"]["alpaca"]["env"]
HEADERS = {"APCA-API-KEY-ID": _env["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": _env["ALPACA_SECRET_KEY"]}
DATA_BASE = "https://data.alpaca.markets"
OUT_DIR = Path(__file__).parent / "data"
OUT_DIR.mkdir(exist_ok=True)


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def fetch(since, until):
    params = {"symbols": "QQQ", "start": f"{since}T13:30:00Z", "end": f"{until}T20:00:00Z",
              "limit": "10000", "feed": "iex"}
    all_trades, token, pages = [], None, 0
    while True:
        q = dict(params)
        if token:
            q["page_token"] = token
        url = DATA_BASE + "/v2/stocks/trades?" + urllib.parse.urlencode(q)
        resp = get(url)
        trades = resp.get("trades", {}).get("QQQ", [])
        all_trades.extend(trades)
        pages += 1
        token = resp.get("next_page_token")
        print(f"  page {pages}: +{len(trades)} (total {len(all_trades)})")
        if not token:
            break
    return all_trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-04-20")
    ap.add_argument("--until", default="2026-08-11")
    a = ap.parse_args()

    trades = fetch(a.since, a.until)
    rth = [{"t": t["t"], "p": t["p"], "s": t["s"], "x": t["x"], "c": t.get("c", [])}
           for t in trades if t["t"][11:16] >= "13:30" and t["t"][11:16] < "20:00"]
    days = sorted({t["t"][:10] for t in rth})
    out = OUT_DIR / "qqq_trades.json"
    out.write_text(json.dumps(rth))
    size_mb = out.stat().st_size / 1e6
    print(f"TRADES: {len(rth)} across {len(days)} days -> {out} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
