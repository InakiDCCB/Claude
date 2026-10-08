"""ohl_shadow.py
OHL Distribution shadow — batch diario para /post-close.

Senal:
  Dia D: open_D > close_{D-1}  (abrio por encima del cierre anterior)
          AND clr_D < 0.15      (cerro en el 15% inferior del rango del dia)
  => distribucion intradiaria: optimismo en apertura, vendedores dominan el dia.
  => sesgo bullish para D+1..D+3 (mean reversion).

Entrada: open_{D+1}  (siguiente sesion habil)
Salida:  close_{D+3} (3 sesiones habildes desde la senal)
Sin SL/TP — time-stop puro.

Backtest 2016-2026 (qqq_daily_full.json):
  hold=3d: n=141 ep, PF=2.260 full, PF=2.207 recent(2021-26), score=71.2 DEPLOY.
  hold=5d: n=140 ep, PF=2.079 full, PF=2.193 recent.
  hold=2d: n=141 ep, PF=1.976 full, score=65.9 DEPLOY.

Frecuencia estimada: ~14 episodios/anio (aproximadamente semanal).

Uso:
    python tools/ohl_shadow.py 2026-10-08 --json
    python tools/ohl_shadow.py 2026-10-08
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# -- credenciales -------------------------------------------------------------
_env = json.loads(
    (Path(__file__).parents[1] / ".mcp.json").read_text()
)["mcpServers"]["alpaca"]["env"]
HEADERS = {
    "APCA-API-KEY-ID":     _env["ALPACA_API_KEY"],
    "APCA-API-SECRET-KEY": _env["ALPACA_SECRET_KEY"],
}
DATA_URL = "https://data.alpaca.markets/v2"

HOLD = 3          # sesiones habildes desde la senal
CLR_THRESH = 0.15 # cierre en el 15% inferior del rango


# -- fetch / cache ------------------------------------------------------------

def _get(url, params, retries=5):
    full = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(full, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise


def _fetch_bars(start: str, end: str, symbol: str = "QQQ") -> list[dict]:
    cap = (datetime.now(timezone.utc) - timedelta(minutes=16)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = min(end, cap)
    bars, params = [], {
        "symbols": symbol, "timeframe": "1Day",
        "start": start, "end": end,
        "limit": "10000", "feed": "sip",
        "adjustment": "split", "sort": "asc",
    }
    while True:
        data = _get(f"{DATA_URL}/stocks/bars", params)
        batch = data.get("bars", {}).get(symbol, [])
        bars.extend(batch)
        npt = data.get("next_page_token")
        if not npt:
            break
        params["page_token"] = npt
    return bars


def _cache_path(symbol: str) -> Path:
    return Path(__file__).parent / "data" / f"{symbol.lower()}_1day.csv"


def load_bars(since_year: int = 2015, symbol: str = "QQQ") -> list[dict]:
    """Carga barras diarias desde cache, actualiza incrementalmente."""
    cache = _cache_path(symbol)
    cache.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    if cache.exists():
        with open(cache, newline="") as f:
            rows = list(csv.DictReader(f))
        last  = rows[-1]["date"] if rows else f"{since_year}-01-01"
        today = datetime.now(timezone.utc).date().isoformat()
        if last < today:
            raw = _fetch_bars(last + "T00:00:00Z", today + "T23:59:59Z", symbol)
            seen = {r["date"] for r in rows}
            for b in raw:
                d = b["t"][:10]
                if d not in seen:
                    rows.append({
                        "date": d, "o": b["o"], "h": b["h"],
                        "l": b["l"], "c": b["c"], "v": b["v"],
                        "vw": b.get("vw") or b["c"],
                    })
                    seen.add(d)
            rows.sort(key=lambda r: r["date"])
            _save_cache(rows, cache)
    else:
        raw = _fetch_bars(
            f"{since_year}-01-01T00:00:00Z",
            datetime.now(timezone.utc).date().isoformat() + "T23:59:59Z",
            symbol,
        )
        rows = [{
            "date": b["t"][:10], "o": b["o"], "h": b["h"],
            "l": b["l"], "c": b["c"], "v": b["v"],
            "vw": b.get("vw") or b["c"],
        } for b in raw]
        rows.sort(key=lambda r: r["date"])
        _save_cache(rows, cache)

    return rows


def _save_cache(rows, cache: Path):
    with open(cache, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "o", "h", "l", "c", "v", "vw"])
        w.writeheader()
        w.writerows(rows)


# -- deteccion de senales -----------------------------------------------------

def _clr(o, h, l, c):
    return (c - l) / (h - l) if h > l else 0.5


def find_signals(rows: list[dict]) -> tuple[list[int], list[int]]:
    """
    Devuelve (accepted, skipped) con slot filter aplicado.
    Signal en indice i = senal disparada al cierre del dia i.
    Entry = open[i+1], exit = close[i+HOLD].
    """
    closes = [float(r["c"]) for r in rows]
    opens  = [float(r["o"]) for r in rows]
    highs  = [float(r["h"]) for r in rows]
    lows   = [float(r["l"]) for r in rows]

    raw_sigs = []
    for i in range(1, len(rows)):
        opened_up = opens[i] > closes[i - 1]
        clr = _clr(opens[i], highs[i], lows[i], closes[i])
        if opened_up and clr < CLR_THRESH:
            raw_sigs.append(i)

    # slot filter: replica el backtest — si hay trade abierto, skip
    accepted, skipped = [], []
    last_exit = -1
    for s in raw_sigs:
        if s + 1 > last_exit:
            accepted.append(s)
            last_exit = s + HOLD
        else:
            skipped.append(s)

    return accepted, skipped


# -- resolucion ---------------------------------------------------------------

def resolve(rows: list[dict], today: str) -> dict:
    dates  = [r["date"] for r in rows]
    opens  = [float(r["o"]) for r in rows]
    closes = [float(r["c"]) for r in rows]
    highs  = [float(r["h"]) for r in rows]
    lows   = [float(r["l"]) for r in rows]

    try:
        today_idx = dates.index(today)
    except ValueError:
        return {"error": f"today {today} not in bars (markets closed?)"}

    accepted, skipped = find_signals(rows)
    accepted_set = set(accepted)

    # nueva senal hoy?
    new_signal = None
    if today_idx in accepted_set:
        entry_i = today_idx + 1
        exit_i  = today_idx + HOLD
        clr_today = _clr(opens[today_idx], highs[today_idx], lows[today_idx], closes[today_idx])
        new_signal = {
            "signal_date":  today,
            "entry_date":   dates[entry_i] if entry_i < len(dates) else None,
            "entry_price":  round(opens[entry_i], 2) if entry_i < len(dates) else None,
            "exit_target":  dates[exit_i]  if exit_i  < len(dates) else None,
            "clr":          round(clr_today, 4),
            "note": (f"OHL: open={opens[today_idx]:.2f} > prev_close={closes[today_idx-1]:.2f},"
                     f" clr={clr_today:.3f} < {CLR_THRESH}"),
        }

    resolved_list = []
    pending = []

    for sig_i in sorted(accepted_set):
        entry_i = sig_i + 1
        exit_i  = sig_i + HOLD
        if entry_i >= len(dates):
            continue
        entry_d = dates[entry_i]
        if entry_d > today:
            continue

        if exit_i >= len(dates):
            days_held = today_idx - entry_i
            pending.append({
                "signal_date":    dates[sig_i],
                "entry_date":     entry_d,
                "exit_target":    None,
                "entry_price":    round(opens[entry_i], 2),
                "current_close":  round(closes[today_idx], 2),
                "unrealized_pct": round((closes[today_idx] / opens[entry_i] - 1) * 100, 2),
                "days_held":      days_held,
                "days_left":      exit_i - today_idx,
            })
            continue

        exit_d = dates[exit_i]
        if exit_d == today:
            ep  = opens[entry_i]
            xp  = closes[exit_i]
            pct = round((xp / ep - 1) * 100, 4)
            resolved_list.append({
                "signal_date": dates[sig_i],
                "entry_date":  entry_d,
                "exit_date":   exit_d,
                "entry_price": round(ep, 2),
                "exit_price":  round(xp, 2),
                "pnl_pct":     pct,
                "outcome":     "TIME",
                "win":         pct > 0,
                "note": f"OHL exit: {ep:.2f}->{xp:.2f} ({pct:+.2f}%)",
            })
        elif exit_d > today:
            try:
                days_held = dates.index(today) - dates.index(entry_d)
            except ValueError:
                days_held = -1
            pending.append({
                "signal_date":    dates[sig_i],
                "entry_date":     entry_d,
                "exit_target":    exit_d,
                "entry_price":    round(opens[entry_i], 2),
                "current_close":  round(closes[today_idx], 2),
                "unrealized_pct": round((closes[today_idx] / opens[entry_i] - 1) * 100, 2),
                "days_held":      days_held,
                "days_left":      HOLD - days_held,
            })

    return {
        "today":           today,
        "new_signal":      new_signal,
        "resolved":        resolved_list if resolved_list else None,
        "pending":         pending,
        "skipped_overlap": [dates[i] for i in skipped if i < len(dates)],
        "n_bars":          len(rows),
        "bars_range":      f"{dates[0]} -> {dates[-1]}",
    }


# -- main ---------------------------------------------------------------------

def ohl_shadow(date: str) -> dict:
    rows = load_bars(since_year=2015, symbol="QQQ")
    return resolve(rows, date)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("date", help="YYYY-MM-DD (fecha ET del dia post-close)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    result = ohl_shadow(a.date)

    if a.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(f"\nOHL Shadow [QQQ] -- {a.date}  ({result.get('bars_range','')})")

    sig = result.get("new_signal")
    if sig:
        print(f"\n  [SENAL HOY] {sig['note']}")
        print(f"  => Entry {sig['entry_date']} @ open ~${sig['entry_price']}"
              f" | Exit target: {sig['exit_target']}")
    else:
        print("\n  Sin senal hoy.")

    res_list = result.get("resolved") or []
    if res_list:
        for res in res_list:
            win = "WIN" if res["win"] else "LOSS"
            print(f"\n  [RESUELTO] {res['signal_date']} -> "
                  f"{res['entry_date']}..{res['exit_date']}")
            print(f"  Entry ${res['entry_price']} -> Exit ${res['exit_price']} "
                  f"({res['pnl_pct']:+.2f}%) [{win}]")
    else:
        print("\n  Sin resolucion hoy.")

    pend = result.get("pending", [])
    if pend:
        print(f"\n  Pendientes ({len(pend)}):")
        for p in pend:
            print(f"    entry {p['entry_date']} @ ${p['entry_price']} | "
                  f"unrealized {p['unrealized_pct']:+.1f}% | "
                  f"{p['days_held']}d/{HOLD}d | exit target {p['exit_target']}")
    else:
        print("\n  Sin trades pendientes.")

    skipped = result.get("skipped_overlap", [])
    if skipped:
        print(f"\n  Skipped (overlap slot): {', '.join(str(s) for s in skipped[-5:])}")
    print()


if __name__ == "__main__":
    main()
