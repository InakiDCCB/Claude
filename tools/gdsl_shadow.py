"""gdsl_shadow.py
Gap Down Sin Llenar (GDSL) shadow — batch diario para /post-close.

Señal (replica situational_snapshot + filtros régimen):
  Dia D: open_D < low_{D-1}  AND  close_D < low_{D-1}
          AND close_D > EMA200_D  AND  YoY_D > 0
  => sesgo bullish para D+1.

Entrada: open_{D+1}  (siguiente sesión hábil)
Salida:  close_{D+5} (5 sesiones hábiles desde la señal — 4 días sostenido)
Sin SL/TP — time-stop puro.

Backtest 2016-2026: n=144, PF=2.11, score=70.5 DEPLOY.
Walk-forward: train(2016-20) PF=1.62, test(2021-26) PF=2.57.

Stateless: recomputa los últimos ~280 días de barras para detectar:
  - Señal hoy (D) → entrada mañana [informativo, no se ejecuta]
  - Trade cuyo exit es hoy  (entry_date = 5 sesiones atrás) → resuelto
  - Trades cuyo exit es en el futuro → pendientes

Uso:
    python tools/gdsl_shadow.py 2026-09-10 --json
    python tools/gdsl_shadow.py 2026-09-10
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

# ── credenciales ──────────────────────────────────────────────────────────────
_env = json.loads(
    (Path(__file__).parents[1] / ".mcp.json").read_text()
)["mcpServers"]["alpaca"]["env"]
HEADERS = {
    "APCA-API-KEY-ID":     _env["ALPACA_API_KEY"],
    "APCA-API-SECRET-KEY": _env["ALPACA_SECRET_KEY"],
}
DATA_URL = "https://data.alpaca.markets/v2"
CACHE    = Path(__file__).parent / "data" / "qqq_1day.csv"

HOLD = 5   # sesiones hábiles desde la señal


# ── fetch / cache ─────────────────────────────────────────────────────────────

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


def _fetch_bars(start: str, end: str) -> list[dict]:
    cap = (datetime.now(timezone.utc) - timedelta(minutes=16)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = min(end, cap)
    bars, params = [], {
        "symbols": "QQQ", "timeframe": "1Day",
        "start": start, "end": end,
        "limit": "10000", "feed": "sip",
        "adjustment": "split", "sort": "asc",
    }
    while True:
        data = _get(f"{DATA_URL}/stocks/bars", params)
        batch = data.get("bars", {}).get("QQQ", [])
        bars.extend(batch)
        npt = data.get("next_page_token")
        if not npt:
            break
        params["page_token"] = npt
    return bars


def load_bars(since_year=2015) -> list[dict]:
    """Carga barras diarias QQQ desde cache, actualiza incrementalmente."""
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    if CACHE.exists():
        with open(CACHE, newline="") as f:
            rows = list(csv.DictReader(f))
        last  = rows[-1]["date"] if rows else f"{since_year}-01-01"
        today = datetime.now(timezone.utc).date().isoformat()
        if last < today:
            raw = _fetch_bars(last + "T00:00:00Z", today + "T23:59:59Z")
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
            _save_cache(rows)
    else:
        raw = _fetch_bars(
            f"{since_year}-01-01T00:00:00Z",
            datetime.now(timezone.utc).date().isoformat() + "T23:59:59Z",
        )
        rows = [{
            "date": b["t"][:10], "o": b["o"], "h": b["h"],
            "l": b["l"], "c": b["c"], "v": b["v"],
            "vw": b.get("vw") or b["c"],
        } for b in raw]
        rows.sort(key=lambda r: r["date"])
        _save_cache(rows)

    return rows


def _save_cache(rows):
    with open(CACHE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "o", "h", "l", "c", "v", "vw"])
        w.writeheader()
        w.writerows(rows)


# ── indicadores ───────────────────────────────────────────────────────────────

def _ema(vals, n):
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    s = sum(vals[:n]) / n
    out[n-1] = s
    k = 2 / (n + 1)
    for i in range(n, len(vals)):
        s = vals[i] * k + s * (1 - k)
        out[i] = s
    return out


def _yoy(closes):
    n = len(closes)
    out = [None] * n
    for i in range(252, n):
        out[i] = closes[i] / closes[i - 252] - 1
    return out


def _wilder_atr(highs, lows, closes, n=14):
    m = len(closes)
    trs = [highs[0] - lows[0]] + [
        max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        for i in range(1, m)
    ]
    atr = [None] * m
    if m <= n:
        return atr
    atr[n] = sum(trs[1:n+1]) / n
    for i in range(n+1, m):
        atr[i] = (atr[i-1] * (n-1) + trs[i]) / n
    return atr


def _atr_pct(atr_arr, window=60):
    """Percentil del ATR actual dentro de su ventana rodante (0=min, 1=max)."""
    out = [None] * len(atr_arr)
    for i in range(len(atr_arr)):
        if atr_arr[i] is None:
            continue
        start = max(0, i - window + 1)
        vals = [v for v in atr_arr[start:i+1] if v is not None]
        if len(vals) < 5:
            continue
        out[i] = sum(1 for v in vals if v <= atr_arr[i]) / len(vals)
    return out


# ── detección de señales ──────────────────────────────────────────────────────

def compute_signals(rows: list[dict]) -> tuple[list[int], list[int]]:
    """
    Devuelve (v1_signals, v2_signals):
      v1 = indices donde GDSL v1 dispara (ema200 + yoy)
      v2 = subset de v1 donde además ATR-pct-60d < 0.50 (baja volatilidad relativa)
    """
    closes = [float(r["c"]) for r in rows]
    opens  = [float(r["o"]) for r in rows]
    highs  = [float(r["h"]) for r in rows]
    lows   = [float(r["l"]) for r in rows]
    ema200 = _ema(closes, 200)
    yoy    = _yoy(closes)
    atr14  = _wilder_atr(highs, lows, closes, 14)
    apct   = _atr_pct(atr14, 60)

    v1, v2 = [], []
    for i in range(1, len(rows)):
        if opens[i] < lows[i-1] and closes[i] < lows[i-1]:
            if ema200[i] is not None and closes[i] > ema200[i]:
                if yoy[i] is not None and yoy[i] > 0:
                    v1.append(i)
                    if apct[i] is not None and apct[i] < 0.50:
                        v2.append(i)
    return v1, v2


# ── resolución ────────────────────────────────────────────────────────────────

def resolve(rows: list[dict], today: str) -> dict:
    """
    Para la fecha TODAY (ET), detecta y resuelve señales GDSL v1 y v2.
    Retorna dict con 'new_signal_v1', 'new_signal_v2', 'resolved', 'pending'.
    """
    dates  = [r["date"] for r in rows]
    opens  = [float(r["o"]) for r in rows]
    closes = [float(r["c"]) for r in rows]
    lows   = [float(r["l"]) for r in rows]

    try:
        today_idx = dates.index(today)
    except ValueError:
        return {"error": f"today {today} not in bars (markets closed?)"}

    v1_sigs, v2_sigs = compute_signals(rows)
    v1_set = set(v1_sigs)
    v2_set = set(v2_sigs)

    def _entry_info(sig_i, version_label):
        entry_idx = sig_i + 1
        exit_idx  = sig_i + HOLD
        return {
            "signal_date": today,
            "entry_date":  dates[entry_idx]  if entry_idx < len(dates) else None,
            "entry_price": round(opens[entry_idx], 2) if entry_idx < len(dates) else None,
            "exit_target": dates[exit_idx]   if exit_idx  < len(dates) else None,
            "version":     version_label,
            "note": (f"GDSL {version_label}: open={opens[sig_i]:.2f}"
                     f" < prev_low={lows[sig_i-1]:.2f},"
                     f" close={closes[sig_i]:.2f} < prev_low"),
        }

    new_signal_v1 = _entry_info(today_idx, "v1") if today_idx in v1_set else None
    new_signal_v2 = _entry_info(today_idx, "v2_atr") if today_idx in v2_set else None

    # — resoluciones y pendientes (solo v1 — v2 se infiere por si sig_i in v2_set)
    resolved_list = []
    pending       = []

    for sig_i in sorted(v1_set):
        entry_i = sig_i + 1
        exit_i  = sig_i + HOLD
        if entry_i >= len(dates) or exit_i >= len(dates):
            continue
        entry_d = dates[entry_i]
        exit_d  = dates[exit_i]
        if entry_d > today:
            continue
        in_v2 = sig_i in v2_set

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
                "also_v2":     in_v2,
                "note": f"GDSL exit(v1{'&v2' if in_v2 else ''}): {ep:.2f}->{xp:.2f} ({pct:+.2f}%)",
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
                "also_v2":        in_v2,
            })

    # el script reporta "resolved" (singular) = el/los trades de HOY
    resolved = resolved_list if resolved_list else None

    return {
        "today":          today,
        "new_signal_v1":  new_signal_v1,
        "new_signal_v2":  new_signal_v2,
        "resolved":       resolved,
        "pending":        pending,
        "n_bars":         len(rows),
        "bars_range":     f"{dates[0]} -> {dates[-1]}",
    }


# ── main ──────────────────────────────────────────────────────────────────────

def gdsl_shadow(date: str) -> dict:
    rows = load_bars(since_year=2015)
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

    result = gdsl_shadow(a.date)

    if a.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(f"\nGDSL Shadow — {a.date}  ({result.get('bars_range','')})")

    v1 = result.get("new_signal_v1")
    v2 = result.get("new_signal_v2")
    if v1:
        tag = " [GDSL v1+v2]" if v2 else " [GDSL v1 solo]"
        print(f"\n  [SEÑAL HOY]{tag} {v1['note']}")
        print(f"  => Entry {v1['entry_date']} @ open ~${v1['entry_price']}"
              f" | Exit target: {v1['exit_target']}")
    else:
        print("\n  Sin señal v1 hoy.")

    res_list = result.get("resolved") or []
    if res_list:
        for res in res_list:
            win = "WIN" if res["win"] else "LOSS"
            v2tag = "+v2" if res.get("also_v2") else ""
            print(f"\n  [RESUELTO v1{v2tag}] {res['signal_date']} -> "
                  f"{res['entry_date']}..{res['exit_date']}")
            print(f"  Entry ${res['entry_price']} -> Exit ${res['exit_price']} "
                  f"({res['pnl_pct']:+.2f}%) [{win}]")
    else:
        print("\n  Sin resolución hoy.")

    pend = result.get("pending", [])
    if pend:
        print(f"\n  Pendientes ({len(pend)}):")
        for p in pend:
            v2tag = "+v2" if p.get("also_v2") else ""
            print(f"    v1{v2tag} entry {p['entry_date']} @ ${p['entry_price']} | "
                  f"unrealized {p['unrealized_pct']:+.1f}% | "
                  f"{p['days_held']}d/{HOLD}d | exit target {p['exit_target']}")
    else:
        print("\n  Sin trades pendientes.")
    print()


if __name__ == "__main__":
    main()
