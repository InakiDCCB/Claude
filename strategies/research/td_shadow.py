"""TD Cyclone shadow (RUUT) — batch diario para /post-close (2026-07-16).

Config ÚNICA con edge coherente hallada en el estudio (`td_backtest.py`, 61 sesiones, 23 configs):
**TD Setup 9P SHORT + RSI14(5m) ≥ 60** · SL = high+2×ATR14(5m) · TP = close−3×ATR14(5m).
PF 1.13 (mitades 1.11/1.17) — BAJO el listón 1.5: shadow a petición del usuario, criterio de
muerte: PF<1.2 a n≥25. Long y diario = anti-hallazgo (PF 0.4-0.8 / 0 pasan TRAIN).

Uso: python td_shadow.py 2026-07-17 --json
Fetchea 1-min IEX de los últimos ~6 días (las cadenas TD cruzan días) + resuelve secuencial.
"""
import argparse
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

from td_backtest import rsi, atr, td_signals

RSI_MIN = 60


def fetch_days(date):
    env = json.loads((Path(__file__).parents[2] / ".mcp.json").read_text())["mcpServers"]["alpaca"]["env"]
    hdr = {"APCA-API-KEY-ID": env["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": env["ALPACA_SECRET_KEY"]}
    d0 = (dt.date.fromisoformat(date) - dt.timedelta(days=6)).isoformat()
    params = {"symbols": "QQQ", "timeframe": "1Min", "start": f"{d0}T13:30:00Z",
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


def build_blocks(bars):
    byday = {}
    for b in bars:
        byday.setdefault(b["t"][:10], []).append(b)
    blocks = []
    for d in sorted(byday):
        bs = byday[d]
        for i0 in range(0, len(bs), 5):
            grp = bs[i0:i0 + 5]
            blocks.append({"d": d, "i1": min(i0 + len(grp) - 1, len(bs) - 1),
                           "o": grp[0]["o"], "h": max(x["h"] for x in grp),
                           "l": min(x["l"] for x in grp), "c": grp[-1]["c"],
                           "v": sum(x["v"] for x in grp)})
    return byday, blocks


def sim_short(bs, i1, entry, sl, tp):
    """Fill (high>=entry, <=3 barras) -> SL-first -> TP -> cierre 15:55. Devuelve (outcome, pnl, exit_j)."""
    fi = None
    for j in range(i1 + 1, min(i1 + 4, len(bs))):
        if bs[j]["h"] >= entry:
            fi = j; break
    if fi is None:
        return "MISS", 0.0, i1 + 3
    cutoff = len(bs) - 5
    for j in range(fi, len(bs)):
        b = bs[j]
        if b["h"] >= sl:
            return "SL", entry - sl, j
        if b["l"] <= tp:
            return "TP", entry - tp, j
        if j >= cutoff:
            return "TIME", entry - b["c"], j
    return "TIME", entry - bs[-1]["c"], len(bs) - 1


def td9s_shadow(date):
    bars = fetch_days(date)
    byday, blocks = build_blocks(bars)
    if date not in byday:
        return []
    closes = [b["c"] for b in blocks]
    r14 = rsi(closes)
    a14 = atr(blocks)
    bs = byday[date]
    out, busy_until = [], -1
    for s in td_signals(blocks):
        b = blocks[s["i"]]
        if b["d"] != date or s["side"] != "short" or s["kind"] != "S9P":
            continue
        if r14[s["i"]] is None or r14[s["i"]] < RSI_MIN or a14[s["i"]] is None:
            continue
        if b["i1"] <= busy_until:
            out.append({"sys": "TD9S", "dir": "short", "date": date, "entry": round(b["c"], 2),
                        "outcome": "skip_overlap", "pnl_ps": 0.0,
                        "note": f"TD9S 9P rsi={r14[s['i']]:.0f} solapada"})
            continue
        entry = b["c"]; sl = b["h"] + 2 * a14[s["i"]]; tp = b["c"] - 3 * a14[s["i"]]
        outcome, pnl, xj = sim_short(bs, b["i1"], entry, sl, tp)
        busy_until = xj
        out.append({"sys": "TD9S", "dir": "short", "date": date, "entry": round(entry, 2),
                    "sl": round(sl, 2), "tp": round(tp, 2), "outcome": outcome,
                    "pnl_ps": round(pnl, 3), "note": f"TD9S 9P rsi={r14[s['i']]:.0f} -> {outcome}"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = td9s_shadow(a.date)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print(f"TD9S shadow {a.date}: {len(out)} señales")
    for o in out:
        print(f"  {o['note']} pnl={o['pnl_ps']:+.2f}/sh")


if __name__ == "__main__":
    main()
