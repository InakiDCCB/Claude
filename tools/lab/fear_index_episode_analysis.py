"""Chequeo de robustez pendiente de fear_index_analysis.py (ver project_fear_index_vix_research.md):
el t-stat día-a-día de "VIX alto"/"backwardation" -> retorno forward está casi seguro inflado
porque el régimen se queda "prendido" muchos días seguidos durante una misma crisis (autocorrelación
temporal / pseudo-replicación, no look-ahead). Este script cuenta EPISODIOS distintos (rachas de
días consecutivos en el régimen, tolerando gaps cortos) y trata cada episodio como UNA sola
observación -- así el n deja de ser "días" y pasa a ser "eventos de mercado independientes".

Mismos datos/definiciones que fear_index_analysis.py (expanding percentiles, WARMUP=60, sin
look-ahead). GAP_TOLERANCE fusiona rachas separadas por <=3 días de trading (ruido cruzando el
umbral de percentil) en un solo episodio.

Uso: python fear_index_episode_analysis.py
"""
import bisect
import csv
import json
from pathlib import Path

QQQ_PATH = Path(__file__).parents[1] / "data" / "qqq_daily_full.json"
VIX_DIR = Path(__file__).parents[1] / "data" / "vix"
WARMUP = 60
GAP_TOLERANCE = 3
HORIZONS = (5, 20, 60)


def load_qqq():
    raw = json.loads(QQQ_PATH.read_text())
    return {bar["t"][:10]: bar["c"] for bar in raw}


def load_vix_csv(name, value_col="CLOSE"):
    path = VIX_DIR / f"{name}.csv"
    out = {}
    with path.open() as f:
        for row in csv.DictReader(f):
            m, d, y = row["DATE"].split("/")
            date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
            try:
                out[date] = float(row[value_col])
            except (ValueError, KeyError):
                continue
    return out


def expanding_percentile(sorted_hist, x):
    if not sorted_hist:
        return None
    idx = bisect.bisect_left(sorted_hist, x)
    return idx / len(sorted_hist)


def find_episodes(flags, dates):
    """flags: lista de bool alineada con dates. Devuelve lista de (start_idx, end_idx) fusionando
    gaps <= GAP_TOLERANCE indices de trading."""
    raw_runs = []
    i = 0
    n = len(flags)
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


def episode_stats(episodes, dates, qqq):
    rows = []
    for start_idx, end_idx in episodes:
        entry_date = dates[start_idx]
        if entry_date not in qqq:
            continue
        entry_px = qqq[entry_date]
        row = {"start": entry_date, "end": dates[end_idx], "duration_days": end_idx - start_idx + 1}
        for h in HORIZONS:
            tgt_idx = start_idx + h
            if tgt_idx < len(dates) and dates[tgt_idx] in qqq:
                row[f"fwd_{h}d"] = qqq[dates[tgt_idx]] / entry_px - 1
            else:
                row[f"fwd_{h}d"] = None
        rows.append(row)
    return rows


def summarize(rows, label):
    print(f"\n=== {label}: {len(rows)} episodios ===")
    if not rows:
        return
    by_year = {}
    for r in rows:
        y = r["start"][:4]
        by_year[y] = by_year.get(y, 0) + 1
    print("Episodios por año:", ", ".join(f"{y}:{n}" for y, n in sorted(by_year.items())))
    durs = [r["duration_days"] for r in rows]
    print(f"Duracion (dias trading): media={sum(durs)/len(durs):.1f}, min={min(durs)}, max={max(durs)}")

    print(f"{'horizonte':<10}{'n':>5}{'mean_ret%':>12}{'median%':>10}{'hit%>0':>9}{'min%':>9}{'max%':>9}")
    for h in HORIZONS:
        vals = sorted(r[f"fwd_{h}d"] for r in rows if r[f"fwd_{h}d"] is not None)
        if not vals:
            continue
        n = len(vals)
        mean = sum(vals) / n * 100
        median = vals[n // 2] * 100
        hit = sum(1 for v in vals if v > 0) / n * 100
        print(f"{h}d{'':<7}{n:>5}{mean:>12.2f}{median:>10.2f}{hit:>9.1f}{vals[0]*100:>9.2f}{vals[-1]*100:>9.2f}")

    print("\nEpisodios individuales (start -> end, duracion, fwd_20d%):")
    for r in rows:
        f20 = r.get("fwd_20d")
        f20s = f"{f20*100:+.2f}%" if f20 is not None else "n/a"
        print(f"  {r['start']} -> {r['end']}  ({r['duration_days']}d trading)  fwd_20d={f20s}")


def main():
    qqq = load_qqq()
    vix = load_vix_csv("VIX")
    vix3m = load_vix_csv("VIX3M")

    dates = sorted(d for d in qqq if d in vix)

    vix_hist_sorted = []
    high_flags, contango_free_flags = [], []
    term_flags = []
    for i, date in enumerate(dates):
        v = vix[date]
        pct = expanding_percentile(vix_hist_sorted, v) if i >= WARMUP else None
        high_flags.append(bool(pct is not None and pct > 0.667))
        bisect.insort(vix_hist_sorted, v)

        term_ratio = v / vix3m[date] if date in vix3m and vix3m[date] > 0 else None
        term_flags.append(bool(term_ratio is not None and term_ratio > 1.0))

    high_episodes = find_episodes(high_flags, dates)
    term_episodes = find_episodes(term_flags, dates)

    high_rows = episode_stats(high_episodes, dates, qqq)
    term_rows = episode_stats(term_episodes, dates, qqq)

    summarize(high_rows, "Episodios de VIX en tercil ALTO (percentil expanding >66.7%)")
    summarize(term_rows, "Episodios de BACKWARDATION (VIX/VIX3M > 1)")


if __name__ == "__main__":
    main()
