"""Fetch QQQ full daily history (SIP, split-adjusted) -- as far back as Alpaca's data goes.
Saves to tools/data/qqq_daily_full.json. Alpaca's equities history starts 2016-01-04 regardless
of start date requested (data-vendor limit, not an account-tier one -- verified empirically).

Uso: python fetch_daily_full.py
"""
import json
import urllib.request
import urllib.parse
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


def fetch_daily(symbol, start, end):
    params = {"symbols": symbol, "timeframe": "1Day", "start": start, "end": end,
              "limit": "10000", "feed": "sip", "adjustment": "split"}
    all_bars, token = [], None
    while True:
        q = dict(params)
        if token:
            q["page_token"] = token
        url = DATA_BASE + "/v2/stocks/bars?" + urllib.parse.urlencode(q)
        resp = get(url)
        bars = resp.get("bars", {}).get(symbol, [])
        all_bars.extend(bars)
        token = resp.get("next_page_token")
        print(f"  +{len(bars)} (total {len(all_bars)})")
        if not token:
            break
    return all_bars


def main():
    import datetime as dt
    # SIP free tier blocks the most recent ~15min (403) -- same fix as tools/fetch_data.py
    end = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=16)).strftime("%Y-%m-%dT%H:%M:%SZ")
    bars = fetch_daily("QQQ", "1999-01-01T00:00:00Z", end)
    out = OUT_DIR / "qqq_daily_full.json"
    out.write_text(json.dumps(bars))
    print(f"TOTAL: {len(bars)} daily bars, {bars[0]['t'][:10]} .. {bars[-1]['t'][:10]} -> {out}")


if __name__ == "__main__":
    main()
