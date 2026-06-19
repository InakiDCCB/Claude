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


def day_obj(date):
    bars = json.loads(DATA.read_text())
    bydate = {}
    for b in bars:
        bydate.setdefault(b["t"][:10], []).append(b)
    dates = sorted(bydate)
    if date not in bydate:
        raise SystemExit(f"sin barras para {date} (fechas disponibles: {dates[0]}..{dates[-1]})")
    idx = dates.index(date)
    prev = Day(dates[idx - 1], bydate[dates[idx - 1]]) if idx > 0 else None
    return Day(date, bydate[date], prev)


def ob_shadow(day, n=2, tp_r=2.0):
    """Señales OB del día con su outcome (TP/SL/TIME) — para loggear como shadow."""
    out = []
    for t in run_ob([day], n=n, tp_r=tp_r, c4=False):
        tp = round(t["entry"] + tp_r * (t["entry"] - t["sl"]), 2)
        out.append({"sys": "OB", "dir": "long", "date": t["day"],
                    "entry": round(t["entry"], 2), "sl": round(t["sl"], 2), "tp": tp,
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
