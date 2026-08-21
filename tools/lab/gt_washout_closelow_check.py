"""gt_washout y gt_closelow (Golden Ticket L1b, 07-03) nunca se retestearon con el protocolo de hoy
(full/recent + episodios independientes + Welch vs baseline) -- a diferencia de gt_rsi2d/gt_3down,
que ya se cerraron negativos (ver project_shadow_full_history_validation.md). Pedido del usuario:
"el tratamiento completo".

Definiciones (memoria / gt_factory.py, señal de HOY basada en la barra de AYER -- causal, mismo fix
de look-ahead aplicado a gt_rsi2d/gt_3down):
- gt_washout: rsi2_d(ayer) < 10 Y clr(ayer) < 0.3 -> long o2c hoy
- gt_closelow: clr(ayer) < 0.2 Y red(ayer) -> long o2c hoy
  clr = (close-low)/(high-low) de la barra (0.5 si high==low) ; red = close < open

Uso: python gt_washout_closelow_check.py
"""
import bisect
import json
from pathlib import Path

QQQ_DAILY_PATH = Path(__file__).parents[1] / "data" / "qqq_daily_full.json"
GAP_TOLERANCE = 3


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

    o2c = [(closes[i] / opens[i] - 1) for i in range(n)]
    RECENT_YEARS = {2023, 2024, 2025, 2026}
    baseline_full = o2c
    baseline_recent = [o2c[i] for i in range(n) if int(dates[i][:4]) in RECENT_YEARS]

    for label, flag_fn in (
        ("gt_washout (rsi2_d<10 Y clr<0.3 AYER, long o2c HOY)",
         lambda i: i >= 1 and rsi2[i - 1] is not None and rsi2[i - 1] < 10 and clr[i - 1] < 0.3),
        ("gt_closelow (clr<0.2 Y red AYER, long o2c HOY)",
         lambda i: i >= 1 and clr[i - 1] < 0.2 and red[i - 1]),
    ):
        flags = [flag_fn(i) for i in range(n)]
        idx_true = [i for i in range(n) if flags[i]]
        vals_full = [o2c[i] for i in idx_true]
        vals_recent = [o2c[i] for i in idx_true if int(dates[i][:4]) in RECENT_YEARS]
        t_full = welch_t(vals_full, baseline_full) if vals_full else None
        t_recent = welch_t(vals_recent, baseline_recent) if vals_recent else None
        print(f"\n{'='*70}\n{label}\n{'='*70}")
        if vals_full:
            print(f"  DIA-A-DIA full: n={len(vals_full)} mean_o2c={sum(vals_full)/len(vals_full)*100:+.3f}% "
                  f"vs baseline={sum(baseline_full)/len(baseline_full)*100:+.3f}%  Welch t={t_full:+.2f}")
        else:
            print("  DIA-A-DIA full: sin señales")
        if vals_recent:
            print(f"  DIA-A-DIA recent: n={len(vals_recent)} mean_o2c={sum(vals_recent)/len(vals_recent)*100:+.3f}% "
                  f"vs baseline={sum(baseline_recent)/len(baseline_recent)*100:+.3f}%  Welch t={t_recent:+.2f}")
        else:
            print("  DIA-A-DIA recent: sin señales")

        episodes = find_episodes(flags)
        ep_o2c = [o2c[s] for s, e in episodes]
        t_ep = welch_t(ep_o2c, baseline_full) if len(ep_o2c) >= 2 else None
        hit_ep = sum(1 for v in ep_o2c if v > 0) / len(ep_o2c) * 100 if ep_o2c else 0
        by_year = {}
        for s, e in episodes:
            y = dates[s][:4]
            by_year[y] = by_year.get(y, 0) + 1
        print(f"  EPISODIOS: n={len(episodes)}  por año: {', '.join(f'{y}:{c}' for y, c in sorted(by_year.items())) or '(ninguno)'}")
        if ep_o2c:
            t_s = f"{t_ep:+.2f}" if t_ep is not None else "n/a (n<2)"
            print(f"  Retorno o2c de entrada de episodio: mean={sum(ep_o2c)/len(ep_o2c)*100:+.3f}% "
                  f"hit={hit_ep:.1f}%  Welch(episodios vs baseline) t={t_s}")


if __name__ == "__main__":
    main()
