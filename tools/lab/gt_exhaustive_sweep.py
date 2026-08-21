"""Búsqueda EXHAUSTIVA de Golden Ticket (gt_rsi2d/gt_3down/gt_washout/gt_closelow), pedido explícito
del usuario: barre los UMBRALES de cada señal (no solo el valor original) Y prueba HOLDING PERIODS
multi-día (no solo o2c mismo día) -- ¿existe alguna combinación de umbral+horizonte con edge real
bajo el protocolo completo (full/recent + episodios + Welch vs baseline)?

Todo causal: features de AYER (rsi2/consec_dn/clr/red) deciden la entrada de HOY (open), igual que
gt_rsi2d/gt_3down ya corregidos. Holding N días: exit = close del día (entrada + N - 1).

Uso: python gt_exhaustive_sweep.py
"""
import bisect
import json
from pathlib import Path

QQQ_DAILY_PATH = Path(__file__).parents[1] / "data" / "qqq_daily_full.json"
GAP_TOLERANCE = 3
RECENT_YEARS = {2023, 2024, 2025, 2026}
HOLDS = (1, 2, 3, 5, 10)


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


def main():
    raw = json.loads(QQQ_DAILY_PATH.read_text())
    raw.sort(key=lambda b: b["t"])
    dates = [b["t"][:10] for b in raw]
    opens = [b["o"] for b in raw]
    closes = [b["c"] for b in raw]
    highs = [b["h"] for b in raw]
    lows = [b["l"] for b in raw]
    n = len(dates)
    rsi2 = wilder_rsi2_daily(closes)
    clr = [(closes[i] - lows[i]) / (highs[i] - lows[i]) if highs[i] > lows[i] else 0.5 for i in range(n)]
    red = [closes[i] < opens[i] for i in range(n)]
    consec_dn = [0] * n
    for i in range(1, n):
        consec_dn[i] = consec_dn[i - 1] + 1 if closes[i] < closes[i - 1] else 0

    def hold_ret(i, h):
        j = i + h - 1
        if j >= n:
            return None
        return closes[j] / opens[i] - 1

    baseline = {h: [] for h in HOLDS}
    for h in HOLDS:
        for i in range(n):
            r = hold_ret(i, h)
            if r is not None:
                baseline[h].append(r)

    def evaluate(label, flag_fn):
        flags = [flag_fn(i) for i in range(n)]
        n_sig = sum(flags)
        if n_sig < 20:
            return None
        best = None
        for h in HOLDS:
            vals = [hold_ret(i, h) for i in range(n) if flags[i]]
            vals = [v for v in vals if v is not None]
            if len(vals) < 20:
                continue
            t_day = welch_t(vals, baseline[h])
            episodes = find_episodes(flags)
            ep_vals = [hold_ret(s, h) for s, e in episodes]
            ep_vals = [v for v in ep_vals if v is not None]
            t_ep = welch_t(ep_vals, baseline[h]) if len(ep_vals) >= 5 else None
            if t_ep is not None and (best is None or abs(t_ep) > abs(best[1])):
                best = (h, t_ep, len(vals), len(episodes), t_day)
        if best is None:
            return None
        h, t_ep, n_day, n_ep, t_day = best
        return {"label": label, "n_sig": n_sig, "best_h": h, "t_ep": t_ep, "t_day": t_day,
                "n_day": n_day, "n_ep": n_ep}

    results = []

    print("Barriendo gt_rsi2d (umbral RSI2)...")
    for thresh in (2, 3, 5, 7, 10, 15, 20):
        r = evaluate(f"rsi2d<{thresh}", lambda i, t=thresh: i >= 1 and rsi2[i - 1] is not None and rsi2[i - 1] < t)
        if r:
            results.append(r)

    print("Barriendo gt_3down (umbral consec_dn)...")
    for thresh in (2, 3, 4, 5, 6):
        r = evaluate(f"3down>={thresh}", lambda i, t=thresh: i >= 1 and consec_dn[i - 1] >= t)
        if r:
            results.append(r)

    print("Barriendo gt_washout (rsi2 x clr)...")
    for rt in (5, 10, 15, 20):
        for ct in (0.2, 0.3, 0.4):
            r = evaluate(f"washout(rsi2<{rt},clr<{ct})",
                         lambda i, rt=rt, ct=ct: i >= 1 and rsi2[i - 1] is not None and rsi2[i - 1] < rt and clr[i - 1] < ct)
            if r:
                results.append(r)

    print("Barriendo gt_closelow (clr, con y sin red)...")
    for ct in (0.1, 0.2, 0.3, 0.4):
        r = evaluate(f"closelow(clr<{ct},red)", lambda i, ct=ct: i >= 1 and clr[i - 1] < ct and red[i - 1])
        if r:
            results.append(r)
        r2 = evaluate(f"closelow(clr<{ct},sinred)", lambda i, ct=ct: i >= 1 and clr[i - 1] < ct)
        if r2:
            results.append(r2)

    results.sort(key=lambda r: abs(r["t_ep"]), reverse=True)
    n_tests = len(results)
    print(f"\nTotal configuraciones probadas: {n_tests}")
    print(f"{'label':<26}{'n_sig':>7}{'best_h':>7}{'n_ep':>6}{'t_ep':>8}{'t_day':>8}")
    for r in results:
        t_day_s = f"{r['t_day']:+.2f}" if r['t_day'] is not None else "n/a"
        print(f"{r['label']:<26}{r['n_sig']:>7}{r['best_h']:>7}{r['n_ep']:>6}{r['t_ep']:+8.2f}{t_day_s:>8}")

    from statistics import NormalDist
    p_corrected = 0.05 / n_tests if n_tests else 0.05
    z_bonf = NormalDist().inv_cdf(1 - p_corrected / 2)
    print(f"\nUmbral Bonferroni (familia alpha=0.05, {n_tests} tests): |t_ep| > {z_bonf:.2f} (sin corregir: 1.96)")
    survivors = [r for r in results if abs(r["t_ep"]) > z_bonf]
    print(f"Sobrevivientes: {len(survivors)}")
    for r in survivors:
        print(f"  {r['label']} h={r['best_h']}d: t_ep={r['t_ep']:+.2f} n_ep={r['n_ep']}")


if __name__ == "__main__":
    main()
