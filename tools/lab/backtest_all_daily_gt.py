"""Re-test de la familia Golden Ticket DIARIA (gt_rsi2d, gt_3down, gt_washout, gt_closelow_v1,
gt_closelow_v2) bajo la metodologia nueva del usuario (2026-08-28): hit ratio informativo, NO
filtro; P&L/PF manda; desglose por estacionalidad (dia semana/mes) y regimen (rango%/volumen
diario, liq x vol) -- mismo espiritu que backtest_all_intraday.py pero a nivel EPISODIO (no
dia-a-dia, para evitar pseudo-replicacion -- ver project_shadow_full_history_validation.md).

Las 4 primeras fueron ARCHIVADAS 2026-08-20 (ninguna sobrevive episodios+baseline, ver
project_golden_ticket.md); gt_closelow_v2 es el sucesor y esta LIVE (swing, v3.1.14) --
ver project_gt_closelow_v2.md. Definiciones y umbrales EXACTOS de esos dos archivos + de
tools/lab/gt_exhaustive_sweep.py (donde se encontraron/confirmaron). Datos: tools/data/qqq_daily_full.json
(27 años, gt_fetch_data.py).

Uso: python backtest_all_daily_gt.py
"""
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
from _score_common import horizon_score, seasonality_breakdown, print_seasonality, wilson_lb
from backtest import stats  # noqa: E402  (reusa el mismo stats() que el resto del roster)

DATA = Path(__file__).parent.parent / "data" / "qqq_daily_full.json"
GAP_TOLERANCE = 3   # mismo criterio que gt_exhaustive_sweep.py para fusionar señales solapadas


class DailyBar:
    """Adaptador minimo para reusar day_features()/seasonality_breakdown() (que esperan
    .date/.h/.l/.c/.v indexables) sobre UNA barra diaria en vez de un Day intradia completo."""
    __slots__ = ("date", "h", "l", "c", "v")

    def __init__(self, date, h, l, c, v):
        self.date, self.h, self.l, self.c, self.v = date, [h], [l], [c], [v]


def wilder_rsi2_daily(closes):
    n = 2
    out = [None] * len(closes)
    if len(closes) < n + 1:
        return out
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    out[n] = 100 - 100 / (1 + (ag / al if al else 1e9))
    for i in range(n + 1, len(closes)):
        g, l_ = gains[i - 1], losses[i - 1]
        ag = (ag * (n - 1) + g) / n
        al = (al * (n - 1) + l_) / n
        out[i] = 100 - 100 / (1 + (ag / al if al else 1e9))
    return out


def find_episodes(flags):
    raw_runs = []
    i, n = 0, len(flags)
    while i < n:
        if flags[i]:
            j = i
            while j < n and flags[j]:
                j += 1
            raw_runs.append([i, j - 1])
            i = j
        else:
            i += 1
    if not raw_runs:
        return []
    merged = [raw_runs[0]]
    for run in raw_runs[1:]:
        if run[0] - merged[-1][1] - 1 <= GAP_TOLERANCE:
            merged[-1][1] = run[1]
        else:
            merged.append(run)
    return merged


def fmt(s):
    if s is None or s["n"] == 0:
        return "n=0"
    wlb = wilson_lb(s["w"], s["n"])
    pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else " inf"
    return (f"n={s['n']:>4}  hit={s['hit']:5.1f}%(wlb {wlb*100:4.1f}%)  PF={pf_s:>5}  "
            f"ret_total={100*s['pnl']:>+7.1f}pp  mLL={s['mll']:>2}")


def main():
    raw = json.loads(DATA.read_text())
    raw.sort(key=lambda b: b["t"])
    dates = [b["t"][:10] for b in raw]
    opens = [b["o"] for b in raw]
    closes = [b["c"] for b in raw]
    highs = [b["h"] for b in raw]
    lows = [b["l"] for b in raw]
    vols = [b.get("v", 0) for b in raw]
    n = len(dates)
    print(f"QQQ diario: {n} sesiones ({dates[0]} -> {dates[-1]})\n")

    rsi2 = wilder_rsi2_daily(closes)
    clr = [(closes[i] - lows[i]) / (highs[i] - lows[i]) if highs[i] > lows[i] else 0.5 for i in range(n)]
    red = [closes[i] < opens[i] for i in range(n)]
    consec_dn = [0] * n
    for i in range(1, n):
        consec_dn[i] = consec_dn[i - 1] + 1 if closes[i] < closes[i - 1] else 0

    days = [DailyBar(dates[i], highs[i], lows[i], closes[i], vols[i]) for i in range(n)]

    def hold_ret(i, h):
        j = i + h - 1
        if j >= n:
            return None
        return closes[j] / opens[i] - 1

    SIGNALS = [
        ("gt_rsi2d", "ARCHIVADO 2026-08-20 (no sobrevive episodios+baseline)", 1,
         lambda i: i >= 1 and rsi2[i - 1] is not None and rsi2[i - 1] < 5),
        ("gt_3down", "ARCHIVADO 2026-08-20", 1,
         lambda i: i >= 1 and consec_dn[i - 1] >= 3),
        ("gt_washout", "ARCHIVADO 2026-08-20", 1,
         lambda i: i >= 1 and rsi2[i - 1] is not None and rsi2[i - 1] < 10 and clr[i - 1] < 0.3),
        ("gt_closelow_v1", "ARCHIVADO 2026-08-20 (superseded por v2)", 1,
         lambda i: i >= 1 and clr[i - 1] < 0.2 and red[i - 1]),
        ("gt_closelow_v2", "LIVE swing v3.1.14 (override usuario, n=0 en shadow al promover)", 3,
         lambda i: i >= 1 and clr[i - 1] < 0.1),
    ]

    out = {}
    for name, status, hold, flag_fn in SIGNALS:
        flags = [flag_fn(i) for i in range(n)]
        episodes = find_episodes(flags)
        trades = []
        for start, _end in episodes:
            r = hold_ret(start, hold)
            if r is not None:
                trades.append({"day": dates[start], "pnl": r})
        s = stats(trades)
        sc = horizon_score(s)
        print(f"=== {name}  hold={hold}d  [{status}] ===")
        print(f"  episodios={len(episodes)}  {fmt(s) if s else 'n=0'}   "
              f"score={sc['total']:.1f}/100 [{sc['verdict']}] (score = 100% PF/riesgo, hit NO pondera)")
        seas = seasonality_breakdown(trades, days, stats)
        print_seasonality(seas)
        print()
        out[name] = {"status": status, "hold": hold, "n_episodes": len(episodes),
                     "stats": s, "score": sc, "seasonality": seas}

    return out


if __name__ == "__main__":
    main()
