"""¿Combinar VIX (fear index, cerrado 08-20 -- pasaba independencia de episodios, fallaba baseline)
con breadth (cerrado 08-20 -- pasaba baseline dia-a-dia, fallaba independencia de episodios) llega
a algo? Pedido explícito del usuario. Hipótesis a probar: si ambos capturan el MISMO fenómeno de
estrés de mercado desde ángulos distintos (VIX=implícito de opciones, breadth=acción de precio),
combinarlos con AND angosta la muestra sin agregar información nueva -- pero es una hipótesis
testeable, no una supuesta a priori.

Régimen conjunto: VIX en tercil alto (expanding) Y %-canasta-arriba-de-SMA50 en tercil bajo
(expanding), mismo día. Espejo (complacencia): VIX bajo Y breadth fuerte. Aplica el protocolo
COMPLETO aprendido de los dos cierres anteriores desde el diseño: episodios independientes (no 2-3
crisis) Y Welch contra baseline real, los dos juntos, no uno solo.

Uso: python vix_breadth_combined.py
"""
import bisect
import csv
import json
from collections import deque
from pathlib import Path

QQQ_PATH = Path(__file__).parents[1] / "data" / "qqq_daily_full.json"
VIX_DIR = Path(__file__).parents[1] / "data" / "vix"
BREADTH_DIR = Path(__file__).parents[1] / "data" / "breadth"
VIX_WARMUP = 60
BREADTH_WARMUP = 210
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

    def read_above50(self, close):
        above50 = close > (self.sum50 / 50) if len(self.buf50) == 50 else None
        if len(self.buf50) == 50:
            self.sum50 -= self.buf50[0]
        self.buf50.append(close); self.sum50 += close
        return above50


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


def episode_rows(episodes, dates, qqq):
    rows = []
    for start_idx, end_idx in episodes:
        entry = dates[start_idx]
        if entry not in qqq:
            continue
        row = {"start": entry, "end": dates[end_idx]}
        for h in HORIZONS:
            tgt = start_idx + h
            row[f"fwd_{h}d"] = (qqq[dates[tgt]] / qqq[entry] - 1) if tgt < len(dates) and dates[tgt] in qqq else None
        rows.append(row)
    return rows


def summarize(rows, key):
    vals = sorted(r[key] for r in rows if r.get(key) is not None)
    if not vals:
        return None
    n = len(vals)
    return {"n": n, "mean": sum(vals) / n, "median": vals[n // 2], "hit": sum(1 for v in vals if v > 0) / n}


def report(label, flags, dates, qqq, baseline):
    episodes = find_episodes(flags, dates)
    rows = episode_rows(episodes, dates, qqq)
    print(f"\n{'='*70}\n{label}: {len(rows)} episodios\n{'='*70}")
    if not rows:
        print("(sin episodios)")
        return
    by_year = {}
    for r in rows:
        y = r["start"][:4]
        by_year[y] = by_year.get(y, 0) + 1
    print("Por año:", ", ".join(f"{y}:{n}" for y, n in sorted(by_year.items())))
    for h in HORIZONS:
        s = summarize(rows, f"fwd_{h}d")
        if not s:
            continue
        vals = [r[f"fwd_{h}d"] for r in rows if r.get(f"fwd_{h}d") is not None]
        t = welch_t(vals, baseline[h])
        t_s = f"{t:+.2f}" if t is not None else "n/a"
        base_mean = sum(baseline[h]) / len(baseline[h])
        print(f"  {h}d: n={s['n']} mean={s['mean']*100:+.2f}% median={s['median']*100:+.2f}% "
              f"hit={s['hit']*100:.1f}%  |  baseline={base_mean*100:+.2f}%  Welch t={t_s}")


def main():
    qqq = load_qqq()
    vix = load_vix_csv("VIX")
    basket = load_basket()

    dates = sorted(set(qqq) & set(vix) & set().union(*[set(d) for d in basket.values()]))
    print(f"Fechas alineadas QQQ+VIX+breadth: {len(dates)} ({dates[0]} -> {dates[-1]})")

    # --- VIX percentile diario (expanding) ---
    vix_hist, vix_pct = [], []
    for i, date in enumerate(dates):
        v = vix[date]
        pct = expanding_percentile(vix_hist, v) if i >= VIX_WARMUP else None
        vix_pct.append(pct)
        bisect.insort(vix_hist, v)

    # --- breadth %-arriba-SMA50 percentile diario (expanding) ---
    states = {sym: SymState() for sym in basket}
    breadth_hist, breadth_pct = [], []
    for i, date in enumerate(dates):
        n_a50 = n_val = 0
        for sym, series in basket.items():
            if date not in series:
                continue
            above50 = states[sym].read_above50(series[date])
            if above50 is not None:
                n_val += 1
                n_a50 += 1 if above50 else 0
        raw = n_a50 / n_val if n_val else None
        pct = expanding_percentile(breadth_hist, raw) if (i >= BREADTH_WARMUP and raw is not None) else None
        breadth_pct.append(pct)
        if raw is not None:
            bisect.insort(breadth_hist, raw)

    vix_high = [bool(p is not None and p > 0.667) for p in vix_pct]
    vix_low = [bool(p is not None and p < 0.333) for p in vix_pct]
    breadth_weak = [bool(p is not None and p < 0.333) for p in breadth_pct]
    breadth_strong = [bool(p is not None and p > 0.667) for p in breadth_pct]

    joint_stress = [a and b for a, b in zip(vix_high, breadth_weak)]
    joint_calm = [a and b for a, b in zip(vix_low, breadth_strong)]

    # --- overlap: ¿cuanto se solapan las dos señales individuales? ---
    n_vix_high = sum(vix_high)
    n_breadth_weak = sum(breadth_weak)
    n_joint = sum(joint_stress)
    overlap_of_vix = n_joint / n_vix_high * 100 if n_vix_high else 0
    overlap_of_breadth = n_joint / n_breadth_weak * 100 if n_breadth_weak else 0
    print(f"\nDias VIX-alto: {n_vix_high} | Dias breadth-debil: {n_breadth_weak} | Dias AMBOS: {n_joint}")
    print(f"De los dias VIX-alto, {overlap_of_vix:.1f}% tambien son breadth-debil.")
    print(f"De los dias breadth-debil, {overlap_of_breadth:.1f}% tambien son VIX-alto.")

    baseline = {h: [] for h in HORIZONS}
    for i in range(len(dates)):
        d0 = dates[i]
        if d0 not in qqq:
            continue
        for h in HORIZONS:
            if i + h < len(dates) and dates[i + h] in qqq:
                baseline[h].append(qqq[dates[i + h]] / qqq[d0] - 1)

    report("VIX-alto Y breadth-debil (estres CONFIRMADO por las 2 señales)", joint_stress, dates, qqq, baseline)
    report("VIX-bajo Y breadth-fuerte (complacencia CONFIRMADA por las 2 señales)", joint_calm, dates, qqq, baseline)


if __name__ == "__main__":
    main()
