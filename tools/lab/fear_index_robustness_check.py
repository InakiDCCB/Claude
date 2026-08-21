"""Tercera pasada de validación del hallazgo VIX (ver project_fear_index_vix_research.md) antes de
implementarlo. El chequeo de episodios ya descartó que fuera "2-3 crisis disfrazadas de patrón".
Esta pasada ataca tres riesgos distintos que TODAVÍA no se probaron:

1. **¿El efecto depende de 2020/2022?** Recalcula episodios excluyendo esos dos años -- si el hit
   rate y la mediana se sostienen en el resto de los años, el hallazgo no es solo "crash + bear
   market", es un patrón de sustos normales también.
2. **¿Hay edge real vs. el baseline, no solo drift secular?** Compara el retorno de los episodios
   contra el retorno de CUALQUIER día en la misma ventana (mismo horizonte), con un test de dos
   muestras (Welch, stdlib puro) -- streaming de todos los días, no solo los de régimen alto.
3. **¿Es frágil al umbral exacto (66.7 percentil)?** Repite con top-cuartil (75%) y top-decil (90%)
   para ver si la dirección/magnitud se sostiene al mover el corte.

Uso: python fear_index_robustness_check.py
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
EXCLUDE_YEARS = {2020, 2022}


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


def episode_returns(episodes, dates, qqq, horizon, exclude_years=None):
    out = []
    for start_idx, end_idx in episodes:
        entry_date = dates[start_idx]
        if exclude_years and int(entry_date[:4]) in exclude_years:
            continue
        tgt_idx = start_idx + horizon
        if entry_date in qqq and tgt_idx < len(dates) and dates[tgt_idx] in qqq:
            out.append(qqq[dates[tgt_idx]] / qqq[entry_date] - 1)
    return out


def all_day_returns(dates, qqq, horizon):
    out = []
    for i in range(len(dates) - horizon):
        d0, dh = dates[i], dates[i + horizon]
        if d0 in qqq and dh in qqq:
            out.append(qqq[dh] / qqq[d0] - 1)
    return out


def welch_t(a, b):
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = (va / na + vb / nb) ** 0.5
    if se == 0:
        return None
    return (ma - mb) / se


def summarize_returns(vals):
    if not vals:
        return None
    n = len(vals)
    vals_sorted = sorted(vals)
    mean = sum(vals) / n
    median = vals_sorted[n // 2]
    hit = sum(1 for v in vals if v > 0) / n
    return {"n": n, "mean": mean, "median": median, "hit": hit}


def build_flags(dates, vix, vix3m, pct_threshold):
    vix_hist_sorted = []
    high_flags, term_flags = [], []
    for i, date in enumerate(dates):
        v = vix[date]
        pct = expanding_percentile(vix_hist_sorted, v) if i >= WARMUP else None
        high_flags.append(bool(pct is not None and pct > pct_threshold))
        bisect.insort(vix_hist_sorted, v)
        term_ratio = v / vix3m[date] if date in vix3m and vix3m[date] > 0 else None
        term_flags.append(bool(term_ratio is not None and term_ratio > 1.0))
    return high_flags, term_flags


def main():
    qqq = load_qqq()
    vix = load_vix_csv("VIX")
    vix3m = load_vix_csv("VIX3M")
    dates = sorted(d for d in qqq if d in vix)

    print("=" * 70)
    print("1. SENSIBILIDAD A 2020/2022 (excluyendo esos 2 años del set de episodios)")
    print("=" * 70)
    high_flags, term_flags = build_flags(dates, vix, vix3m, 0.667)
    high_episodes = find_episodes(high_flags, dates)
    term_episodes = find_episodes(term_flags, dates)

    for label, episodes in (("VIX-alto", high_episodes), ("Backwardation", term_episodes)):
        print(f"\n-- {label} --")
        for h in HORIZONS:
            full = episode_returns(episodes, dates, qqq, h)
            ex = episode_returns(episodes, dates, qqq, h, exclude_years=EXCLUDE_YEARS)
            sf, se = summarize_returns(full), summarize_returns(ex)
            if sf and se:
                print(f"  {h}d: TODOS n={sf['n']} mean={sf['mean']*100:+.2f}% median={sf['median']*100:+.2f}% hit={sf['hit']*100:.1f}%"
                      f"   |   SIN 2020/2022 n={se['n']} mean={se['mean']*100:+.2f}% median={se['median']*100:+.2f}% hit={se['hit']*100:.1f}%")

    print("\n" + "=" * 70)
    print("2. EPISODIOS vs. BASELINE (cualquier dia, mismo horizonte) -- test Welch")
    print("=" * 70)
    for label, episodes in (("VIX-alto", high_episodes), ("Backwardation", term_episodes)):
        print(f"\n-- {label} --")
        for h in HORIZONS:
            ep_rets = episode_returns(episodes, dates, qqq, h)
            base_rets = all_day_returns(dates, qqq, h)
            sep, sbase = summarize_returns(ep_rets), summarize_returns(base_rets)
            t = welch_t(ep_rets, base_rets)
            t_s = f"{t:+.2f}" if t is not None else "n/a"
            print(f"  {h}d: episodios mean={sep['mean']*100:+.2f}% (n={sep['n']})  vs  baseline mean={sbase['mean']*100:+.2f}% (n={sbase['n']})  Welch t={t_s}")

    print("\n" + "=" * 70)
    print("3. SENSIBILIDAD AL UMBRAL (VIX-alto: percentil 66.7 vs 75 vs 90)")
    print("=" * 70)
    for thresh in (0.667, 0.75, 0.90):
        hf, _ = build_flags(dates, vix, vix3m, thresh)
        eps = find_episodes(hf, dates)
        print(f"\n-- umbral p{thresh*100:.0f} ({len(eps)} episodios) --")
        for h in HORIZONS:
            rets = episode_returns(eps, dates, qqq, h)
            s = summarize_returns(rets)
            if s:
                print(f"  {h}d: n={s['n']} mean={s['mean']*100:+.2f}% median={s['median']*100:+.2f}% hit={s['hit']*100:.1f}%")


if __name__ == "__main__":
    main()
