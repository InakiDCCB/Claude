"""Chequeo de robustez del hallazgo de breadth_analysis.py: %-arriba-de-SMA50 en tercil BAJO (pocas
acciones de la canasta por encima de su propia media de 50 dias -- "breadth debil") y
nuevos-maximos-menos-minimos en tercil BAJO cruzan Welch>2 contra el baseline real en AMBAS eras a
60d -- la primera vez en la sesion que algo pasa esa prueba desde el diseño (lección del cierre de
VIX). Antes de llamarlo candidato, aplica el MISMO chequeo de episodios que a VIX: ¿son 2-3
clusters (2018Q4/2020/2022) o un patron que se repite?

Uso: python breadth_episode_check.py
"""
import bisect
import json
from collections import deque
from pathlib import Path

QQQ_PATH = Path(__file__).parents[1] / "data" / "qqq_daily_full.json"
BREADTH_DIR = Path(__file__).parents[1] / "data" / "breadth"
WARMUP = 210
GAP_TOLERANCE = 3
HORIZONS = (5, 20, 60)


def load_qqq():
    raw = json.loads(QQQ_PATH.read_text())
    return {bar["t"][:10]: bar["c"] for bar in raw}


def load_basket():
    out = {}
    for path in sorted(BREADTH_DIR.glob("*.json")):
        raw = json.loads(path.read_text())
        out[path.stem] = {bar["t"][:10]: bar["c"] for bar in raw}
    return out


class SymState:
    def __init__(self):
        self.buf50 = deque(maxlen=50)
        self.sum50 = 0.0
        self.buf20 = deque(maxlen=20)

    def update_and_read(self, close):
        above50 = close > (self.sum50 / 50) if len(self.buf50) == 50 else None
        new_hi = new_lo = None
        if len(self.buf20) == 20:
            new_hi = close >= max(self.buf20)
            new_lo = close <= min(self.buf20)
        if len(self.buf50) == 50:
            self.sum50 -= self.buf50[0]
        self.buf50.append(close); self.sum50 += close
        self.buf20.append(close)
        return above50, new_hi, new_lo


def expanding_percentile(sorted_hist, x):
    if not sorted_hist:
        return None
    return bisect.bisect_left(sorted_hist, x) / len(sorted_hist)


def find_episodes(flags, dates):
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


def welch_t(a, b):
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = (va / na + vb / nb) ** 0.5
    return None if se == 0 else (ma - mb) / se


def summarize(rows_key, rows):
    vals = sorted(r[rows_key] for r in rows if r.get(rows_key) is not None)
    if not vals:
        return None
    n = len(vals)
    return {"n": n, "mean": sum(vals) / n, "median": vals[n // 2], "hit": sum(1 for v in vals if v > 0) / n}


def main():
    qqq = load_qqq()
    basket = load_basket()
    all_dates = sorted(set(qqq) & set().union(*[set(d) for d in basket.values()]))
    states = {sym: SymState() for sym in basket}

    pct50_series, hilo_series = [], []
    for date in all_dates:
        n_a50 = n_val_50 = n_hi = n_lo = n_val_hilo = 0
        for sym, series in basket.items():
            if date not in series:
                continue
            above50, new_hi, new_lo = states[sym].update_and_read(series[date])
            if above50 is not None:
                n_val_50 += 1
                n_a50 += 1 if above50 else 0
            if new_hi is not None:
                n_val_hilo += 1
                n_hi += 1 if new_hi else 0
                n_lo += 1 if new_lo else 0
        pct50_series.append(n_a50 / n_val_50 if n_val_50 else None)
        hilo_series.append((n_hi - n_lo) / n_val_hilo if n_val_hilo else None)

    def low_tercile_flags(series):
        hist, flags = [], []
        for i, v in enumerate(series):
            if v is None:
                flags.append(False)
                continue
            pct = expanding_percentile(hist, v) if i >= WARMUP else None
            bisect.insort(hist, v)
            flags.append(bool(pct is not None and pct < 0.333))
        return flags

    def episode_rows(episodes):
        rows = []
        for start_idx, end_idx in episodes:
            entry = all_dates[start_idx]
            if entry not in qqq:
                continue
            row = {"start": entry, "end": all_dates[end_idx], "dur": end_idx - start_idx + 1}
            for h in HORIZONS:
                tgt = start_idx + h
                row[f"fwd_{h}d"] = (qqq[all_dates[tgt]] / qqq[entry] - 1) if tgt < len(all_dates) and all_dates[tgt] in qqq else None
            rows.append(row)
        return rows

    baseline = {h: [] for h in HORIZONS}
    for i in range(len(all_dates)):
        d0 = all_dates[i]
        if d0 not in qqq:
            continue
        for h in HORIZONS:
            if i + h < len(all_dates) and all_dates[i + h] in qqq:
                baseline[h].append(qqq[all_dates[i + h]] / qqq[d0] - 1)

    for label, series in (("pct_above_50sma BAJO (breadth debil)", pct50_series),
                           ("net_hilo BAJO (mas nuevos minimos que maximos)", hilo_series)):
        flags = low_tercile_flags(series)
        episodes = find_episodes(flags, all_dates)
        rows = episode_rows(episodes)
        print(f"\n{'='*70}\n{label}: {len(rows)} episodios\n{'='*70}")
        by_year = {}
        for r in rows:
            y = r["start"][:4]
            by_year[y] = by_year.get(y, 0) + 1
        print("Por año:", ", ".join(f"{y}:{n}" for y, n in sorted(by_year.items())))
        for h in HORIZONS:
            s = summarize(f"fwd_{h}d", rows)
            if not s:
                continue
            ep_vals = [r[f"fwd_{h}d"] for r in rows if r.get(f"fwd_{h}d") is not None]
            t = welch_t(ep_vals, baseline[h])
            t_s = f"{t:+.2f}" if t is not None else "n/a"
            base_mean = sum(baseline[h]) / len(baseline[h])
            print(f"  {h}d: n={s['n']} mean={s['mean']*100:+.2f}% median={s['median']*100:+.2f}% "
                  f"hit={s['hit']*100:.1f}%  |  baseline={base_mean*100:+.2f}%  Welch(episodios vs baseline) t={t_s}")


if __name__ == "__main__":
    main()
