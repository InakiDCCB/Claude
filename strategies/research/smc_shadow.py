"""SMC shadow — computa las señales SMC (Order Block v1) de UN día sobre datos REALES, para
validación shadow SIN órdenes (solo guarda precios y niveles: entry/SL/TP/outcome).

Decisión 2026-06-18: el shadow SMC se computa en /post-close sobre las barras del día (detección
CAUSAL = mismas señales que en vivo), NO en cada ciclo → cero coste de latencia por ciclo. Reusa la
lógica de smc_backtest.py. El usuario prefiere validación sobre datos reales en vez de backtest.

Uso:
  python smc_shadow.py 2026-06-16            # un día desde qqq_1min.json
  python smc_shadow.py 2026-06-16 --json     # salida JSON lista para loggear a shadow_signals
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from backtest import Day
from smc_backtest import run_ob

DATA = Path(__file__).parent / "data" / "qqq_1min.json"


def _fetch_alpaca_day(date):
    """Barras 1-min IEX (RTH) de QQQ para `date` desde Alpaca (keys de .mcp.json)."""
    import urllib.request
    import urllib.parse
    env = json.loads((Path(__file__).parents[2] / ".mcp.json").read_text())["mcpServers"]["alpaca"]["env"]
    headers = {"APCA-API-KEY-ID": env["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": env["ALPACA_SECRET_KEY"]}
    params = {"symbols": "QQQ", "timeframe": "1Min", "start": f"{date}T13:30:00Z",
              "end": f"{date}T20:00:00Z", "limit": "10000", "feed": "iex", "adjustment": "raw"}
    url = "https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read().decode())
    return [b for b in resp.get("bars", {}).get("QQQ", []) if "13:30" <= b["t"][11:16] < "20:00"]


def day_obj(date):
    """Day del `date`. Usa qqq_1min.json si lo tiene; si no (p.ej. HOY), fetchea de Alpaca.
    OB solo usa estructura intradía → prev=None es válido cuando se fetchea."""
    bars = json.loads(DATA.read_text())
    bydate = {}
    for b in bars:
        bydate.setdefault(b["t"][:10], []).append(b)
    if date in bydate:
        dates = sorted(bydate)
        idx = dates.index(date)
        prev = Day(dates[idx - 1], bydate[dates[idx - 1]]) if idx > 0 else None
        return Day(date, bydate[date], prev)
    day_bars = _fetch_alpaca_day(date)
    if not day_bars:
        raise SystemExit(f"sin barras para {date} (ni en cache ni en Alpaca)")
    return Day(date, day_bars, None)


def _killzone(i):
    """Killzone ET por índice de barra 1-min desde 9:30 — DATO (decisión E.1), no gate."""
    if i < 90:
        return "open"
    if i < 120:
        return "mid"
    if i < 240:
        return "lunch"
    return "pm"


def ob_shadow(day, n=2, tp_r=2.0):
    """Señales OB del día con su outcome (TP/SL/TIME) — para loggear como shadow."""
    out = []
    for t in run_ob([day], n=n, tp_r=tp_r, c4=False):
        tp = round(t["entry"] + tp_r * (t["entry"] - t["sl"]), 2)
        out.append({"sys": "OB", "dir": "long", "date": t["day"],
                    "entry": round(t["entry"], 2), "sl": round(t["sl"], 2), "tp": tp,
                    "kz": _killzone(t["ei"]),
                    "outcome": t["xt"], "pnl_ps": round(t["pnl"], 3)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--tp", type=float, default=2.0)
    a = ap.parse_args()
    out = ob_shadow(day_obj(a.date), n=a.n, tp_r=a.tp)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print(f"OB shadow {a.date}: {len(out)} señales")
    for o in out:
        print(f"  entry={o['entry']:.2f} sl={o['sl']:.2f} tp={o['tp']:.2f} -> {o['outcome']:<4} pnl={o['pnl_ps']:+.2f}/sh")
    if out:
        w = sum(1 for o in out if o["pnl_ps"] > 0)
        print(f"  hit {w}/{len(out)} = {100*w/len(out):.0f}%   pnl {sum(o['pnl_ps'] for o in out):+.2f}/sh")


if __name__ == "__main__":
    main()
