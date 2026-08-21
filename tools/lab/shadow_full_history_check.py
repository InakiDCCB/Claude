"""Aplica la MISMA disciplina de la sesión (full 2016-2026 vs recent 2023-2026, episodios
independientes, Welch vs baseline donde aplica) a los sistemas SHADOW activos, pedido explícito del
usuario tras cerrar la línea VIX/breadth/combinatoria. Reutiliza la infraestructura YA construida:

1. **LWR (Liquidity Wick Reversal)** -- calibrado 07-31 sobre solo 72 sesiones
   (`tools/calibrate_lwr.py`). Config live: wick_thresh=0.60, min_rvol=3.0, tp=0.5R (factory
   `wick_reversal` en tools/backtest.py). Corre contra los 10 años completos de 1-min
   (mismo harness que `backtest_live_full_history.py` para S1-S6).

2. **TD9S (TD Sequential / RUUT Cyclone)** -- calibrado 07-16 sobre 61 sesiones (`td_backtest.py`).
   Config live: Setup 9 Perfected (S9P) SHORT + RSI14(5m)>=60, SL=high+2xATR14, TP=close-3xATR14
   (`td_shadow.py`). Corre contra los 10 años completos (bloques 5-min desde tools/data/qqq_1min/).

3. **Golden Ticket gt_rsi2d + gt_3down** -- validados originalmente en 27 años DIARIOS via Yahoo
   (`gt_factory.py`, OOS bloqueado en 2023). Acá se recalculan sobre QQQ diario de Alpaca
   (`tools/data/qqq_daily_full.json`, 2016-2026) con RSI2 Wilder de dos fases (lección de la
   sesión) -- full/recent, episodios (la señal puede persistir varios días seguidos) y Welch
   contra el baseline real de retorno open-to-close.

Uso: python shadow_full_history_check.py
"""
import bisect
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from backtest import Day, stats, run_market, wick_reversal          # noqa: E402
from td_backtest import rsi as td_rsi, atr as td_atr, td_signals, simulate as td_simulate  # noqa: E402

DATA_1MIN_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"
QQQ_DAILY_PATH = Path(__file__).parents[1] / "data" / "qqq_daily_full.json"
RECENT_YEARS = {2023, 2024, 2025, 2026}
GAP_TOLERANCE = 3
HORIZONS_GT = None  # GT es O2C mismo dia, no forward horizon


def wilson_lb(wins, n, z=1.96):
    if n == 0:
        return None
    p = wins / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (center - margin) / denom


def load_days_1min(years):
    bydate = {}
    for year in years:
        path = DATA_1MIN_DIR / f"{year}.csv"
        if not path.exists():
            continue
        with path.open() as f:
            for row in csv.DictReader(f):
                date = row["t"][:10]
                bydate.setdefault(date, []).append(
                    {"t": row["t"], "o": float(row["o"]), "h": float(row["h"]),
                     "l": float(row["l"]), "c": float(row["c"]), "v": float(row["v"])})
    dates = sorted(bydate)
    days, prev = [], None
    for d in dates:
        bars = bydate[d]
        if len(bars) < 300:
            continue
        day = Day(d, bars, prev)
        days.append(day)
        prev = day
    return days, bydate


def fmt_stats(s):
    if s is None or s["n"] == 0:
        return "n=0"
    wlb = wilson_lb(s["w"], s["n"])
    pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "inf"
    return (f"n={s['n']:>4} hit={s['hit']:5.1f}% wilsonLB={wlb*100:5.1f}% pf={pf_s:>5} "
            f"pnl/sh={s['pnl']:+8.2f} mean={s['mean']:+.4f}")


def report_trades(name, trades):
    print(f"\n=== {name} ===")
    s_all = stats(trades)
    print(f"  POOL 2016-2026: {fmt_stats(s_all)}")
    s_recent = stats([t for t in trades if t["day"][:4] in {str(y) for y in RECENT_YEARS}])
    print(f"  RECENT 2023-2026: {fmt_stats(s_recent)}")
    by_year = {}
    for t in trades:
        by_year.setdefault(t["day"][:4], []).append(t)
    for year in sorted(by_year):
        print(f"    {year}: {fmt_stats(stats(by_year[year]))}")


# ============================================================
# 1. LWR
# ============================================================

def run_lwr():
    print("\n" + "#" * 70 + "\n# 1. LWR (Liquidity Wick Reversal) -- 10 años completos\n" + "#" * 70)
    days, _ = load_days_1min(range(2016, 2027))
    print(f"{len(days)} días cargados.")
    sig = wick_reversal(("r", 0.5), wick_thresh=0.60, min_rvol=3.0)()
    trades = run_market(days, sig, c4=False)
    report_trades("LWR long (wt=0.60 rvol>=3.0 tp=0.5R)", trades)


# ============================================================
# 2. TD9S
# ============================================================

def build_5min_blocks(bydate):
    blocks = []
    for d in sorted(bydate):
        bs = bydate[d]
        for i0 in range(0, len(bs), 5):
            grp = bs[i0:i0 + 5]
            blocks.append({"d": d, "i1": min(i0 + len(grp) - 1, len(bs) - 1),
                           "o": grp[0]["o"], "h": max(x["h"] for x in grp),
                           "l": min(x["l"] for x in grp), "c": grp[-1]["c"],
                           "v": sum(x["v"] for x in grp)})
    return blocks


def run_td9s():
    print("\n" + "#" * 70 + "\n# 2. TD9S (S9P short + RSI14>=60) -- 10 años completos\n" + "#" * 70)
    _, bydate = load_days_1min(range(2016, 2027))
    bydate_min = {d: [{"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"]}
                       for b in bars] for d, bars in bydate.items()}
    blocks = build_5min_blocks(bydate_min)
    print(f"{len(blocks)} bloques 5-min.")
    closes = [b["c"] for b in blocks]
    r14 = td_rsi(closes)
    a14 = td_atr(blocks)
    sigs = td_signals(blocks)
    trades = []
    for s in sigs:
        if s["side"] != "short" or s["kind"] != "S9P":
            continue
        i = s["i"]
        if a14[i] is None or r14[i] is None or r14[i] < 60:
            continue
        b = blocks[i]
        entry, sl, tp = b["c"], b["c"] + 2 * a14[i], b["c"] - 3 * a14[i]
        r = td_simulate(bydate_min, b["d"], b["i1"], "short", entry, sl, tp)
        if r is None:
            continue
        trades.append({"day": b["d"], "pnl": r})

    def stats_td(trades):
        n = len(trades)
        if n == 0:
            return None
        w = sum(1 for t in trades if t["pnl"] > 0)
        gw = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gl = -sum(t["pnl"] for t in trades if t["pnl"] <= 0)
        return {"n": n, "w": w, "hit": 100 * w / n, "pnl": sum(t["pnl"] for t in trades),
                "mean": sum(t["pnl"] for t in trades) / n,
                "pf": (gw / gl) if gl > 0 else float("inf")}

    print(f"  POOL 2016-2026: {fmt_stats(stats_td(trades))}")
    recent = [t for t in trades if t["day"][:4] in {str(y) for y in RECENT_YEARS}]
    print(f"  RECENT 2023-2026: {fmt_stats(stats_td(recent))}")
    by_year = {}
    for t in trades:
        by_year.setdefault(t["day"][:4], []).append(t)
    for year in sorted(by_year):
        print(f"    {year}: {fmt_stats(stats_td(by_year[year]))}")


# ============================================================
# 3. Golden Ticket: gt_rsi2d + gt_3down (daily O2C)
# ============================================================

def wilder_rsi2_daily(closes):
    """RSI2 con seed de dos fases (lección de la sesión: promedio simple primero, recursion despues)."""
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
        g, l = gains[i - 1], losses[i - 1]
        ag = (ag * (n - 1) + g) / n
        al = (al * (n - 1) + l) / n
        out[i] = 100 - 100 / (1 + (ag / al if al else 1e9))
    return out


def welch_t(a, b):
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = (va / na + vb / nb) ** 0.5
    return None if se == 0 else (ma - mb) / se


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


def run_gt():
    print("\n" + "#" * 70 + "\n# 3. Golden Ticket gt_rsi2d + gt_3down -- daily O2C, 10 años\n" + "#" * 70)
    raw = json.loads(QQQ_DAILY_PATH.read_text())
    raw.sort(key=lambda b: b["t"])
    dates = [b["t"][:10] for b in raw]
    closes = [b["c"] for b in raw]
    opens = [b["o"] for b in raw]
    n = len(dates)
    rsi2 = wilder_rsi2_daily(closes)

    consec_dn = [0] * n
    for i in range(1, n):
        consec_dn[i] = consec_dn[i - 1] + 1 if closes[i] < closes[i - 1] else 0

    o2c = [(closes[i] / opens[i] - 1) for i in range(n)]
    baseline_full = o2c
    baseline_recent = [o2c[i] for i in range(n) if int(dates[i][:4]) in RECENT_YEARS]

    # OJO: el gate de HOY debe usar SOLO datos conocidos ANTES de la apertura de hoy -- por eso
    # rsi2[i-1]/consec_dn[i-1] (cierre de AYER), no rsi2[i]/consec_dn[i] (que incluye el cierre de
    # HOY, el mismo dato que se esta prediciendo -- look-ahead bias circular, detectado en la
    # primera corrida: daba hit=3.2%, t=-11, la firma clasica de "el label se filtro al feature").
    # Mismo espiritu que feedback_lookahead_bias_research.md.
    for label, flag_fn in (
        ("gt_rsi2d (RSI2 diario < 5 AYER, long o2c HOY)", lambda i: i >= 1 and rsi2[i - 1] is not None and rsi2[i - 1] < 5),
        ("gt_3down (>=3 cierres consecutivos a la baja AYER, long o2c HOY)", lambda i: i >= 1 and consec_dn[i - 1] >= 3),
    ):
        flags = [flag_fn(i) for i in range(n)]
        idx_true = [i for i in range(n) if flags[i]]
        vals_full = [o2c[i] for i in idx_true]
        vals_recent = [o2c[i] for i in idx_true if int(dates[i][:4]) in RECENT_YEARS]
        t_full = welch_t(vals_full, baseline_full)
        t_recent = welch_t(vals_recent, baseline_recent) if vals_recent else None
        print(f"\n-- {label} --")
        print(f"  DIA-A-DIA full: n={len(vals_full)} mean_o2c={sum(vals_full)/len(vals_full)*100:+.3f}% "
              f"vs baseline={sum(baseline_full)/len(baseline_full)*100:+.3f}%  Welch t={t_full:+.2f}" if vals_full else "  sin señales")
        if vals_recent:
            print(f"  DIA-A-DIA recent: n={len(vals_recent)} mean_o2c={sum(vals_recent)/len(vals_recent)*100:+.3f}% "
                  f"vs baseline={sum(baseline_recent)/len(baseline_recent)*100:+.3f}%  Welch t={t_recent:+.2f}")

        episodes = find_episodes(flags)
        ep_o2c = []  # o2c del PRIMER dia de cada episodio (entrada), para chequeo de independencia
        for s, e in episodes:
            ep_o2c.append(o2c[s])
        t_ep = welch_t(ep_o2c, baseline_full) if ep_o2c else None
        hit_ep = sum(1 for v in ep_o2c if v > 0) / len(ep_o2c) * 100 if ep_o2c else 0
        by_year = {}
        for s, e in episodes:
            y = dates[s][:4]
            by_year[y] = by_year.get(y, 0) + 1
        print(f"  EPISODIOS (entrada=primer dia de cada racha): n={len(episodes)}  "
              f"por año: {', '.join(f'{y}:{c}' for y, c in sorted(by_year.items()))}")
        if ep_o2c:
            print(f"  Retorno o2c del dia de entrada del episodio: mean={sum(ep_o2c)/len(ep_o2c)*100:+.3f}% "
                  f"hit={hit_ep:.1f}%  Welch(episodios vs baseline) t={t_ep:+.2f}")


def main():
    run_lwr()
    run_td9s()
    run_gt()


if __name__ == "__main__":
    main()
