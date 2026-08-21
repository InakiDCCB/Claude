"""GT CloseLow v2 shadow batch (2026-08-20) -- reemplaza a gt_rsi2d/gt_3down/gt_washout/gt_closelow
v1 y a TD9S, todos ARCHIVADOS el mismo día tras un research exhaustivo que no encontró edge
rescatable (ver project_shadow_full_history_validation.md, project_gt_closelow_v2.md).

Señal: clr(ayer) < 0.1 (close-location-range: (close-low)/(high-low) de la barra DIARIA) -> long al
open del día siguiente, hold FIJO de 3 días hábiles, exit = close del 3er día (entry, entry+1,
entry+2). Backtest 10 años (episodios independientes, no día-a-día): PF=2.36 pool, positivo en
10/11 años, hit=66.5%.

Diseño STATELESS (a diferencia de TD9S/LWR que resuelven el mismo día): no hace falta trackear una
posición abierta entre ciclos -- cada día simplemente se pregunta "¿el día de hace 2 sesiones hábiles
cumplió la condición de entrada?" mirando las barras diarias ya disponibles. Se corre UNA vez por
día en `/post-close` (después del cierre de hoy, que es el 'exit' si corresponde).

Uso: python gt_closelow_v2_shadow.py <YYYY-MM-DD de HOY ET> --json
"""
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

HOLD_DAYS = 3
CLR_THRESH = 0.1


def fetch_daily(end_date, lookback_days=15):
    env = json.loads((Path(__file__).parents[1] / ".mcp.json").read_text())["mcpServers"]["alpaca"]["env"]
    headers = {"APCA-API-KEY-ID": env["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": env["ALPACA_SECRET_KEY"]}
    import datetime as dt
    start = (dt.date.fromisoformat(end_date) - dt.timedelta(days=lookback_days * 2)).isoformat()
    params = {"symbols": "QQQ", "timeframe": "1Day", "start": f"{start}T00:00:00Z",
              "end": f"{end_date}T23:59:00Z", "limit": "50", "feed": "sip", "adjustment": "split"}
    url = "https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        resp = json.loads(r.read())
    bars = resp.get("bars", {}).get("QQQ", [])
    return [b for b in bars if b["t"][:10] <= end_date]


def clr_of(bar):
    rng = bar["h"] - bar["l"]
    return (bar["c"] - bar["l"]) / rng if rng > 0 else 0.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("today")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    bars = fetch_daily(a.today)
    if len(bars) < HOLD_DAYS + 1:
        print(json.dumps({"status": "insufficient_bars", "n": len(bars)}) if a.json
              else f"Bars insuficientes: {len(bars)}")
        return

    # hoy = bars[-1]. entry_idx = hoy - (HOLD_DAYS-1). condicion se mira en el dia ANTES de entry.
    entry_idx = len(bars) - HOLD_DAYS
    cond_idx = entry_idx - 1
    if cond_idx < 0:
        print(json.dumps({"status": "no_signal", "reason": "not_enough_history"}) if a.json
              else "Sin historia suficiente para evaluar la condición.")
        return

    cond_bar = bars[cond_idx]
    entry_bar = bars[entry_idx]
    exit_bar = bars[-1]
    clr = clr_of(cond_bar)
    triggered = clr < CLR_THRESH

    out = {
        "sys": "GTCLV2", "cond_date": cond_bar["t"][:10], "clr": round(clr, 4),
        "triggered": triggered,
    }
    if triggered:
        entry_px = entry_bar["o"]
        exit_px = exit_bar["c"]
        pnl_sh = exit_px - entry_px  # $/share, misma convencion que el resto de GT (pnl_sh = close-open)
        out.update({
            "entry_date": entry_bar["t"][:10], "exit_date": exit_bar["t"][:10],
            "entry": round(entry_px, 2), "exit": round(exit_px, 2),
            "pnl_sh": round(pnl_sh, 3),
            "outcome": "TP" if pnl_sh > 0 else "SL",
        })

    if a.json:
        print(json.dumps(out))
    else:
        if triggered:
            print(f"GTCLV2 señal: entrada {out['entry_date']}@{out['entry']} -> salida {out['exit_date']}@{out['exit']} "
                  f"({out['outcome']}, {out['pnl_sh']:+.3f}/sh) [clr {out['cond_date']}={clr:.3f}]")
        else:
            print(f"GTCLV2 sin señal (clr {cond_bar['t'][:10]}={clr:.3f} >= {CLR_THRESH})")


if __name__ == "__main__":
    main()
