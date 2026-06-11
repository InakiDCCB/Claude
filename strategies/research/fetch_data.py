"""Fetch QQQ 1-min SIP bars for backtest window + safety check (positions/open orders).
Saves bars to strategies/research/data/qqq_1min.json. Prints compact summary only.
"""
import json
import urllib.request
import urllib.parse
from pathlib import Path

_env = json.loads((Path(__file__).parents[2] / ".mcp.json").read_text())["mcpServers"]["alpaca"]["env"]
HEADERS = {"APCA-API-KEY-ID": _env["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": _env["ALPACA_SECRET_KEY"]}

DATA_BASE = "https://data.alpaca.markets"
TRADE_BASE = "https://paper-api.alpaca.markets"

OUT_DIR = Path(__file__).parent / "data"
OUT_DIR.mkdir(exist_ok=True)


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    # --- Safety check ---
    clock = get(TRADE_BASE + "/v2/clock")
    positions = get(TRADE_BASE + "/v2/positions")
    orders = get(TRADE_BASE + "/v2/orders?status=open&limit=100")
    print(f"CLOCK: now={clock['timestamp'][:19]} is_open={clock['is_open']}")
    print(f"POSITIONS: {len(positions)}")
    for p in positions:
        print(f"  !! {p['symbol']} qty={p['qty']} avg={p['avg_entry_price']} pl={p['unrealized_pl']}")
    print(f"OPEN ORDERS: {len(orders)}")
    for o in orders:
        print(f"  !! {o['symbol']} {o['side']} {o['order_type']} qty={o['qty']} id={o['id'][:8]}")

    # --- Account snapshot ---
    acct = get(TRADE_BASE + "/v2/account")
    print(f"EQUITY: {acct['equity']}")

    # --- Bars: 1-min QQQ, full RTH window 06-01..06-10 (UTC 13:30-20:00) ---
    all_bars = []
    params = {
        "symbols": "QQQ",
        "timeframe": "1Min",
        "start": "2026-04-20T13:30:00Z",
        "end": "2026-06-10T20:00:00Z",
        "limit": "10000",
        "feed": "sip",
        "adjustment": "raw",
    }
    token = None
    pages = 0
    while True:
        q = dict(params)
        if token:
            q["page_token"] = token
        url = DATA_BASE + "/v2/stocks/bars?" + urllib.parse.urlencode(q)
        resp = get(url)
        bars = resp.get("bars", {}).get("QQQ", [])
        all_bars.extend(bars)
        pages += 1
        token = resp.get("next_page_token")
        if not token:
            break

    # Keep RTH only (13:30 <= t < 20:00 UTC)
    rth = [b for b in all_bars if "13:30:00" <= b["t"][11:19] or True]  # filter below properly
    rth = [b for b in all_bars if b["t"][11:16] >= "13:30" and b["t"][11:16] < "20:00"]
    days = sorted({b["t"][:10] for b in rth})
    out = OUT_DIR / "qqq_1min.json"
    out.write_text(json.dumps(rth))
    print(f"BARS: {len(rth)} RTH 1-min bars across {len(days)} days ({pages} pages)")
    for d in days:
        n = sum(1 for b in rth if b["t"][:10] == d)
        print(f"  {d}: {n}")


if __name__ == "__main__":
    main()
