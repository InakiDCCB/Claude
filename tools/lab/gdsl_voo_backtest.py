"""gdsl_voo_backtest.py
Backtest completo de GDSL (Gap Down Sin Llenar) sobre VOO.
Misma lógica que gdsl_shadow.py pero parametrizable por símbolo.

Uso:
    uv run python tools/lab/gdsl_voo_backtest.py
    uv run python tools/lab/gdsl_voo_backtest.py --symbol SPY
    uv run python tools/lab/gdsl_voo_backtest.py --symbol QQQ   # control
"""
from __future__ import annotations
import argparse, csv, json, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

_env = json.loads(
    (Path(__file__).parents[2] / ".mcp.json").read_text()
)["mcpServers"]["alpaca"]["env"]
HEADERS = {
    "APCA-API-KEY-ID":     _env["ALPACA_API_KEY"],
    "APCA-API-SECRET-KEY": _env["ALPACA_SECRET_KEY"],
}
DATA_URL = "https://data.alpaca.markets/v2"
HOLD = 5
SINCE_YEAR = 2015


def _get(url, params, retries=5):
    full = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(full, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(5 * (attempt + 1)); continue
            raise


def fetch_bars(symbol: str) -> list[dict]:
    cache = Path(__file__).parent.parent / "data" / f"{symbol.lower()}_1day.csv"
    cache.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    if cache.exists():
        with open(cache, newline="") as f:
            rows = list(csv.DictReader(f))
        last  = rows[-1]["date"] if rows else f"{SINCE_YEAR}-01-01"
        today = datetime.now(timezone.utc).date().isoformat()
        if last >= today:
            return rows
        start, end = last + "T00:00:00Z", today + "T23:59:59Z"
    else:
        start = f"{SINCE_YEAR}-01-01T00:00:00Z"
        end   = datetime.now(timezone.utc).date().isoformat() + "T23:59:59Z"

    cap = (datetime.now(timezone.utc) - timedelta(minutes=16)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = min(end, cap)
    params = {
        "symbols": symbol, "timeframe": "1Day",
        "start": start, "end": end,
        "limit": "10000", "feed": "sip",
        "adjustment": "split", "sort": "asc",
    }
    seen = {r["date"] for r in rows}
    while True:
        data = _get(f"{DATA_URL}/stocks/bars", params)
        batch = data.get("bars", {}).get(symbol, [])
        for b in batch:
            d = b["t"][:10]
            if d not in seen:
                rows.append({"date": d, "o": b["o"], "h": b["h"],
                             "l": b["l"], "c": b["c"], "v": b["v"],
                             "vw": b.get("vw") or b["c"]})
                seen.add(d)
        npt = data.get("next_page_token")
        if not npt: break
        params["page_token"] = npt

    rows.sort(key=lambda r: r["date"])
    with open(cache, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date","o","h","l","c","v","vw"])
        w.writeheader(); w.writerows(rows)
    return rows


def _ema(vals, n):
    out = [None] * len(vals)
    if len(vals) < n: return out
    s = sum(vals[:n]) / n; out[n-1] = s; k = 2 / (n + 1)
    for i in range(n, len(vals)):
        s = vals[i] * k + s * (1 - k); out[i] = s
    return out


def _yoy(closes):
    n = len(closes); out = [None] * n
    for i in range(252, n):
        out[i] = closes[i] / closes[i - 252] - 1
    return out


def _wilder_atr(highs, lows, closes, n=14):
    m = len(closes)
    trs = [highs[0] - lows[0]] + [
        max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        for i in range(1, m)]
    atr = [None] * m
    if m <= n: return atr
    atr[n] = sum(trs[1:n+1]) / n
    for i in range(n+1, m):
        atr[i] = (atr[i-1] * (n-1) + trs[i]) / n
    return atr


def _atr_pct(atr_arr, window=60):
    out = [None] * len(atr_arr)
    for i in range(len(atr_arr)):
        if atr_arr[i] is None: continue
        start = max(0, i - window + 1)
        vals = [v for v in atr_arr[start:i+1] if v is not None]
        if len(vals) < 5: continue
        out[i] = sum(1 for v in vals if v <= atr_arr[i]) / len(vals)
    return out


def run_backtest(symbol: str) -> dict:
    rows  = fetch_bars(symbol)
    dates = [r["date"] for r in rows]
    opens  = [float(r["o"]) for r in rows]
    closes = [float(r["c"]) for r in rows]
    highs  = [float(r["h"]) for r in rows]
    lows   = [float(r["l"]) for r in rows]

    ema200 = _ema(closes, 200)
    yoy    = _yoy(closes)
    atr14  = _wilder_atr(highs, lows, closes, 14)
    apct   = _atr_pct(atr14, 60)

    # detectar señales brutas
    raw_v1, raw_v2 = [], []
    for i in range(1, len(rows)):
        if opens[i] < lows[i-1] and closes[i] < lows[i-1]:
            if ema200[i] is not None and closes[i] > ema200[i]:
                if yoy[i] is not None and yoy[i] > 0:
                    raw_v1.append(i)
                    if apct[i] is not None and apct[i] < 0.50:
                        raw_v2.append(i)

    # slot filter
    def _slot(sigs):
        accepted, last_exit = [], -1
        for s in sigs:
            if s + 1 > last_exit:
                accepted.append(s); last_exit = s + HOLD
        return accepted

    v1_acc = _slot(raw_v1)
    v2_set = set(raw_v2) & set(v1_acc)

    def _trades(sig_set, label):
        trades = []
        for si in sig_set:
            ei = si + 1; xi = si + HOLD
            if ei >= len(dates) or xi >= len(dates): continue
            ep = opens[ei]; xp = closes[xi]
            pct = (xp / ep - 1) * 100
            trades.append({
                "sig_date": dates[si], "entry_date": dates[ei], "exit_date": dates[xi],
                "entry": ep, "exit": xp, "pnl_pct": round(pct, 4),
                "win": pct > 0, "year": int(dates[si][:4]),
            })
        return trades

    t1 = _trades(v1_acc, "v1")
    t2 = _trades(sorted(v2_set), "v2")

    def _stats(trades):
        if not trades: return {}
        n = len(trades); wins = sum(t["win"] for t in trades)
        gross_w = sum(t["pnl_pct"] for t in trades if t["win"])
        gross_l = abs(sum(t["pnl_pct"] for t in trades if not t["win"]))
        pf = round(gross_w / gross_l, 3) if gross_l else float("inf")
        avg = round(sum(t["pnl_pct"] for t in trades) / n, 4)
        return {"n": n, "wins": wins, "wr": round(wins/n*100, 1),
                "pf": pf, "avg_pct": avg,
                "gross_w": round(gross_w, 2), "gross_l": round(gross_l, 2)}

    def _by_year(trades):
        years = {}
        for t in trades:
            y = t["year"]
            years.setdefault(y, []).append(t)
        out = {}
        for y, ts in sorted(years.items()):
            n = len(ts); w = sum(t["win"] for t in ts)
            pct = sum(t["pnl_pct"] for t in ts)
            out[y] = {"n": n, "wins": w, "wr": round(w/n*100, 1),
                      "sum_pct": round(pct, 2), "pos": pct > 0}
        return out

    return {
        "symbol": symbol,
        "bars_range": f"{dates[0]} -> {dates[-1]}",
        "n_bars": len(rows),
        "v1": {**_stats(t1), "by_year": _by_year(t1), "raw_signals": len(raw_v1),
               "skipped_overlap": len(raw_v1) - len(v1_acc)},
        "v2": {**_stats(t2), "by_year": _by_year(t2), "raw_signals": len(raw_v2),
               "skipped_overlap": len(raw_v2) - len(v2_set)},
    }


def _bar(label, stats, by_year):
    print(f"\n  {label}: n={stats.get('n',0)} | wr={stats.get('wr',0)}% | "
          f"PF={stats.get('pf','—')} | avg={stats.get('avg_pct',0):+.3f}%/trade")
    for yr, s in by_year.items():
        sign = "+" if s["pos"] else "-"
        print(f"    {yr}: {s['n']:3d} trades  {s['wins']:3d}W  "
              f"wr={s['wr']:5.1f}%  sum={s['sum_pct']:+6.2f}%  [{sign}]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="VOO")
    args = ap.parse_args()

    sym = args.symbol.upper()
    print(f"\nFetcheando barras para {sym} ...", flush=True)
    r = run_backtest(sym)

    print(f"\n{'='*60}")
    print(f"GDSL Backtest — {sym}  ({r['bars_range']})")
    print(f"{'='*60}")
    _bar("v1 (EMA200+YoY)", r["v1"], r["v1"].get("by_year", {}))
    print(f"    raw_signals={r['v1']['raw_signals']}  skipped_overlap={r['v1']['skipped_overlap']}")
    _bar("v2 (EMA200+YoY+ATRpct<0.5)", r["v2"], r["v2"].get("by_year", {}))
    print(f"    raw_signals={r['v2']['raw_signals']}  skipped_overlap={r['v2']['skipped_overlap']}")
    print()


if __name__ == "__main__":
    main()
