"""
tools/lab/situational_backtest.py
Backtest 10 años del situational_snapshot de QQQ.

Replica la función SQL situational_snapshot() sobre barras diarias históricas
para validar los precursores D→D+1 con muestra suficiente.

Aproximaciones (idénticas a volume_profiles):
  VPOC  ≈ vw  (VWAP del bar diario SIP)
  VAH   = vpoc + 0.34*(H-L)
  VAL   = vpoc - 0.34*(H-L)
  open  = bar.o  (proxy para open_9:30)

Uso:
  uv run python tools/lab/situational_backtest.py
  uv run python tools/lab/situational_backtest.py --since 2018
  uv run python tools/lab/situational_backtest.py --json
  uv run python tools/lab/situational_backtest.py --refresh   # fuerza re-fetch
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

# ── credenciales ──────────────────────────────────────────────────────────────
_env = json.loads((Path(__file__).parents[2] / ".mcp.json").read_text())["mcpServers"]["alpaca"]["env"]
HEADERS = {
    "APCA-API-KEY-ID":     _env["ALPACA_API_KEY"],
    "APCA-API-SECRET-KEY": _env["ALPACA_SECRET_KEY"],
}
DATA_URL = "https://data.alpaca.markets/v2"
CACHE    = Path(__file__).parent.parent / "data" / "qqq_1day.csv"


# ── fetch Alpaca ───────────────────────────────────────────────────────────────

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
    import datetime as _dt
    # SIP free bloquea los últimos ~15 min → usar now-16min como end máximo
    cap = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(minutes=16)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = min(end, cap)
    bars, params = [], {
        "symbols":    "QQQ",
        "timeframe":  "1Day",
        "start":      start,
        "end":        end,
        "limit":      "10000",
        "feed":       "sip",
        "adjustment": "split",
        "sort":       "asc",
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


def load_bars(since_year=2015, refresh=False) -> list[dict]:
    """Devuelve lista de dicts {date, o, h, l, c, v, vw} ordenada."""
    CACHE.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    if CACHE.exists() and not refresh:
        with open(CACHE, newline="") as f:
            rows = list(csv.DictReader(f))
        last = rows[-1]["date"] if rows else f"{since_year}-01-01"
        today = date.today().isoformat()
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
            _save(rows)
    else:
        raw = _fetch_bars(f"{since_year}-01-01T00:00:00Z",
                          date.today().isoformat() + "T23:59:59Z")
        rows = [{
            "date": b["t"][:10], "o": b["o"], "h": b["h"],
            "l": b["l"], "c": b["c"], "v": b["v"],
            "vw": b.get("vw") or b["c"],
        } for b in raw]
        rows.sort(key=lambda r: r["date"])
        _save(rows)

    return rows


def _save(rows):
    with open(CACHE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date","o","h","l","c","v","vw"])
        w.writeheader()
        w.writerows(rows)


# ── situational snapshot (réplica exacta del SQL) ─────────────────────────────

def _classify(y: dict, t: dict) -> tuple[str, str, float]:
    """
    Replica situational_snapshot() para un par (yesterday, today).
    Retorna (rule, bias, conf).
    """
    yh, yl, yc = float(y["h"]), float(y["l"]), float(y["c"])
    yvw        = float(y["vw"])
    th, tl, tc = float(t["h"]), float(t["l"]), float(t["c"])
    to_        = float(t["o"])

    # VP levels de ayer
    vpoc = yvw
    vah  = vpoc + 0.34 * (yh - yl)
    val  = vpoc - 0.34 * (yh - yl)

    # gap usando open de hoy como proxy de open_9:30
    if   to_ > yh:   v_gap = "gap_up_outside"
    elif to_ >= vah: v_gap = "gap_up_inside"
    elif to_ >= val: v_gap = "inside"
    elif to_ >= yl:  v_gap = "gap_down_inside"
    else:            v_gap = "gap_down_outside"

    # estructura de rango
    yr = yh - yl
    tr = th - tl
    if   tr > 1.5 * yr:               v_struct = "expansion"
    elif tr < 0.5 * yr:               v_struct = "contraction"
    elif th > yh and tl > yl:         v_struct = "higher_high"
    elif th < yh and tl < yl:         v_struct = "lower_low"
    elif th <= yh and tl >= yl:       v_struct = "inside_day"
    else:                             v_struct = "overlap"

    v_mid = (th + tl) / 2

    # reglas en orden de prioridad (idéntico al SQL)
    if v_gap == "gap_up_outside" and tc > yh:
        return "gap_up_sin_llenar", "bearish", 0.6

    if v_gap == "gap_down_outside" and tc < yl:
        return "gap_down_sin_llenar", "bullish", 0.6

    if not (tl <= vpoc <= th) and tc > 0 and abs(tc - vpoc) / tc < 0.015:
        bias = "bullish" if vpoc > tc else "bearish"
        return "naked_vpoc_iman", bias, 0.55

    if v_struct == "higher_high" and tc < v_mid:
        return "hh_agotamiento", "bearish", 0.5

    if v_struct == "lower_low" and tc > v_mid:
        return "ll_agotamiento", "bullish", 0.5

    if v_struct == "inside_day":
        return "inside_breakout_esperado", "mixed", 0.4

    if v_struct == "expansion":
        return "expansion_reversion", "mixed", 0.45

    return "default", "neutral", 0.3


# ── backtest ──────────────────────────────────────────────────────────────────

def run_backtest(rows: list[dict], since: str | None = None) -> list[dict]:
    if since:
        rows = [r for r in rows if r["date"] >= since]

    results = []
    for i in range(1, len(rows) - 1):
        y, t, nxt = rows[i-1], rows[i], rows[i+1]
        rule, bias, conf = _classify(y, t)

        hit = None
        if bias in ("bullish", "bearish"):
            tc  = float(t["c"])
            nc  = float(nxt["c"])
            hit = (bias == "bullish" and nc > tc) or (bias == "bearish" and nc < tc)

        results.append({
            "date":  t["date"],
            "year":  t["date"][:4],
            "rule":  rule,
            "bias":  bias,
            "conf":  conf,
            "hit":   hit,
        })
    return results


# ── estadísticas ─────────────────────────────────────────────────────────────

def _stats(items):
    n    = len(items)
    hits = sum(1 for x in items if x)
    if n == 0:
        return {"n": 0, "hits": 0, "pct": None, "effect": None}
    pct    = round(hits / n * 100, 1)
    effect = round(hits / n - 0.5, 3)
    return {"n": n, "hits": hits, "pct": pct, "effect": effect}


def analyze(results: list[dict]) -> dict:
    directional = [r for r in results if r["bias"] in ("bullish", "bearish")]

    # — por bias global
    by_bias: dict[str, list] = defaultdict(list)
    for r in directional:
        by_bias[r["bias"]].append(r["hit"])

    # — por regla
    by_rule: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for r in directional:
        by_rule[r["rule"]][r["bias"]].append(r["hit"])

    # — año × bias (solo directional)
    by_year: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for r in directional:
        by_year[r["year"]][r["bias"]].append(r["hit"])

    # — frecuencia de cada regla (total días clasificados)
    rule_freq: dict[str, int] = defaultdict(int)
    for r in results:
        rule_freq[r["rule"]] += 1

    total_days = len(results)

    return {
        "total_days":  total_days,
        "directional": len(directional),
        "by_bias":     {b: _stats(v) for b, v in by_bias.items()},
        "by_rule": {
            rule: {
                "freq":  rule_freq[rule],
                "freq_pct": round(rule_freq[rule] / total_days * 100, 1) if total_days else None,
                **{bias: _stats(hits) for bias, hits in biases.items()},
            }
            for rule, biases in by_rule.items()
        },
        "by_year": {
            yr: {b: _stats(v) for b, v in biases.items()}
            for yr, biases in sorted(by_year.items())
        },
        "rule_freq_all": {
            rule: {"n": rule_freq[rule],
                   "pct": round(rule_freq[rule] / total_days * 100, 1) if total_days else None}
            for rule in sorted(rule_freq, key=lambda r: -rule_freq[r])
        },
    }


# ── output ────────────────────────────────────────────────────────────────────

def print_report(stats: dict, since: str | None):
    label = f"desde {since}" if since else "histórico completo"
    print(f"\nSituational Backtest QQQ — {label}")
    print(f"  Días totales: {stats['total_days']}  |  Con bias direccional: {stats['directional']}")

    print("\n── Por bias (bullish/bearish vs close D+1) ──────────────────────────────")
    print(f"  {'Bias':<12} {'n':>5}  {'Hits':>5}  {'Hit%':>6}  {'Effect':>8}  {'vs base':>8}")
    for bias in ("bullish", "bearish"):
        s = stats["by_bias"].get(bias, {"n":0, "hits":0, "pct":None, "effect":None})
        pct = f"{s['pct']:.1f}%" if s["pct"] is not None else "—"
        eff = f"{s['effect']:+.3f}" if s["effect"] is not None else "—"
        print(f"  {bias:<12} {s['n']:>5}  {s['hits']:>5}  {pct:>6}  {eff:>8}  {'base=50%':>8}")

    print("\n── Por regla (solo bias direccional) ────────────────────────────────────")
    # Ordenar por n total descendente
    rule_rows = []
    for rule, rd in stats["by_rule"].items():
        n_total = sum(v["n"] for k, v in rd.items() if k in ("bullish","bearish"))
        rule_rows.append((n_total, rule, rd))
    rule_rows.sort(reverse=True)

    print(f"  {'Regla':<28} {'Bias':<10} {'n':>5}  {'Hit%':>6}  {'Effect':>8}  {'Freq%':>6}")
    for _, rule, rd in rule_rows:
        freq_pct = stats["by_rule"][rule].get("freq_pct", "?")
        first = True
        for bias in ("bullish", "bearish"):
            s = rd.get(bias)
            if s and s["n"] > 0:
                pct = f"{s['pct']:.1f}%" if s["pct"] is not None else "—"
                eff = f"{s['effect']:+.3f}" if s["effect"] is not None else "—"
                rule_label = rule if first else ""
                fp = f"{freq_pct}%" if first else ""
                print(f"  {rule_label:<28} {bias:<10} {s['n']:>5}  {pct:>6}  {eff:>8}  {fp:>6}")
                first = False

    print("\n── Año a año — bullish ──────────────────────────────────────────────────")
    print(f"  {'Año':<6} {'n':>4}  {'Hit%':>6}  {'Effect':>8}")
    for yr, biases in stats["by_year"].items():
        s = biases.get("bullish", {"n":0,"pct":None,"effect":None})
        pct = f"{s['pct']:.1f}%" if s["pct"] is not None else "—"
        eff = f"{s['effect']:+.3f}" if s["effect"] is not None else "—"
        print(f"  {yr:<6} {s['n']:>4}  {pct:>6}  {eff:>8}")

    print("\n── Año a año — bearish ──────────────────────────────────────────────────")
    print(f"  {'Año':<6} {'n':>4}  {'Hit%':>6}  {'Effect':>8}")
    for yr, biases in stats["by_year"].items():
        s = biases.get("bearish", {"n":0,"pct":None,"effect":None})
        pct = f"{s['pct']:.1f}%" if s["pct"] is not None else "—"
        eff = f"{s['effect']:+.3f}" if s["effect"] is not None else "—"
        print(f"  {yr:<6} {s['n']:>4}  {pct:>6}  {eff:>8}")

    print("\n── Frecuencia de reglas (% días) ────────────────────────────────────────")
    for rule, v in stats["rule_freq_all"].items():
        print(f"  {rule:<30} n={v['n']:>5}  ({v['pct']}%)")

    print()


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--since",   default=None, help="YYYY o YYYY-MM-DD para filtrar resultados")
    ap.add_argument("--fetch-since", default="2015", help="Año desde el que cachear (default 2015)")
    ap.add_argument("--refresh", action="store_true", help="Re-fetch aunque exista el cache")
    ap.add_argument("--json",    action="store_true", help="Output en JSON")
    args = ap.parse_args()

    since_filter = args.since
    if since_filter and len(since_filter) == 4:
        since_filter = since_filter + "-01-01"

    print("Cargando barras diarias QQQ...", flush=True)
    rows = load_bars(since_year=int(args.fetch_since), refresh=args.refresh)
    print(f"  {len(rows)} dias ({rows[0]['date']} -> {rows[-1]['date']})", flush=True)

    results = run_backtest(rows, since=since_filter)
    stats   = analyze(results)

    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print_report(stats, since_filter)


if __name__ == "__main__":
    main()
