"""Breadth de mercado (amplitud), pedido explícito del usuario 2026-08-20 tras cerrar VIX/fear-index
con resultado negativo ("probemos con breadth de mercado"). Canasta de 54 miembros grandes/líquidos
del Nasdaq-100 (`tools/fetch_breadth_history.py`, limitación de composición actual reconocida ahí)
vs retorno forward de QQQ.

LECCIÓN APLICADA DESDE EL DISEÑO (no como parche después, a diferencia de la sesión VIX): cada
bucket se compara DIRECTO contra el baseline real (cualquier día, mismo horizonte) con test de
Welch -- no solo contra el bucket opuesto, que fue la trampa que invalidó el hallazgo VIX (ver
project_fear_index_vix_research.md, cierre 2026-08-20).

Métricas (todas con SOLO información hasta el día actual, incremental, sin look-ahead):
1. % avanzando (close > close previo) en la canasta -- terciles expanding.
2. % arriba de su SMA50 propia -- terciles expanding (participación de tendencia corto plazo).
3. % arriba de su SMA200 propia -- terciles expanding (participación de tendencia largo plazo).
4. Máximos/mínimos netos de 20 días ((nuevos_max - nuevos_min) / n_validos) -- terciles expanding.
5. "Breadth thrust" (evento, no régimen): % avanzando cruza de <40% a >60% en <=10 dias de trading
   -- patrón conocido (Zweig breadth thrust) pero raro, poco usado en retail.

Uso: python breadth_analysis.py
"""
import bisect
import json
from collections import deque
from pathlib import Path

QQQ_PATH = Path(__file__).parents[1] / "data" / "qqq_daily_full.json"
BREADTH_DIR = Path(__file__).parents[1] / "data" / "breadth"
RECENT_YEARS = {2023, 2024, 2025, 2026}
WARMUP = 210  # dias antes de confiar en SMA200 + percentiles expanding
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
    __slots__ = ("prev_close", "sum50", "buf50", "sum200", "buf200", "buf20")

    def __init__(self):
        self.prev_close = None
        self.buf50 = deque(maxlen=50)
        self.sum50 = 0.0
        self.buf200 = deque(maxlen=200)
        self.sum200 = 0.0
        self.buf20 = deque(maxlen=20)

    def update_and_read(self, close):
        """Lee senales usando SOLO historia previa (buffers antes de insertar close), luego
        actualiza los buffers con el close de hoy."""
        adv = None if self.prev_close is None else (close > self.prev_close)
        above50 = None
        if len(self.buf50) == 50:
            above50 = close > (self.sum50 / 50)
        above200 = None
        if len(self.buf200) == 200:
            above200 = close > (self.sum200 / 200)
        new_hi = new_lo = None
        if len(self.buf20) == 20:
            new_hi = close >= max(self.buf20)
            new_lo = close <= min(self.buf20)

        if len(self.buf50) == 50:
            self.sum50 -= self.buf50[0]
        self.buf50.append(close); self.sum50 += close
        if len(self.buf200) == 200:
            self.sum200 -= self.buf200[0]
        self.buf200.append(close); self.sum200 += close
        self.buf20.append(close)
        self.prev_close = close
        return adv, above50, above200, new_hi, new_lo


class Bucket:
    def __init__(self):
        self.n, self.s = 0, 0.0

    def add(self, x):
        self.n += 1
        self.s += x

    def mean(self):
        return self.s / self.n if self.n else None


def welch_t(a_vals, b_vals):
    na, nb = len(a_vals), len(b_vals)
    if na < 2 or nb < 2:
        return None
    ma, mb = sum(a_vals) / na, sum(b_vals) / nb
    va = sum((x - ma) ** 2 for x in a_vals) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b_vals) / (nb - 1)
    se = (va / na + vb / nb) ** 0.5
    return None if se == 0 else (ma - mb) / se


def expanding_percentile(sorted_hist, x):
    if not sorted_hist:
        return None
    return bisect.bisect_left(sorted_hist, x) / len(sorted_hist)


def bucket3(p):
    if p is None:
        return None
    return "low" if p < 0.333 else ("high" if p > 0.667 else "mid")


def main():
    qqq = load_qqq()
    basket = load_basket()
    print(f"Canasta: {len(basket)} simbolos")

    all_dates = sorted(set(qqq) & set().union(*[set(d) for d in basket.values()]))
    print(f"Fechas alineadas: {len(all_dates)} ({all_dates[0]} -> {all_dates[-1]})")

    states = {sym: SymState() for sym in basket}
    metric_series = {"pct_adv": [], "pct_above50": [], "pct_above200": [], "net_hilo": []}
    dates_valid = []  # fechas donde ya hay >= WARMUP dias vistos

    hist_sorted = {k: [] for k in metric_series}
    fwd_returns = {h: {} for h in HORIZONS}  # date -> fwd return (calculado despues, abajo)

    raw_daily = []  # (date, pct_adv, pct_above50, pct_above200, net_hilo) para el thrust-scan

    for i, date in enumerate(all_dates):
        n_adv = n_val_adv = 0
        n_a50 = n_val_50 = 0
        n_a200 = n_val_200 = 0
        n_hi = n_lo = n_val_hilo = 0
        for sym, series in basket.items():
            if date not in series:
                continue
            adv, above50, above200, new_hi, new_lo = states[sym].update_and_read(series[date])
            if adv is not None:
                n_val_adv += 1
                n_adv += 1 if adv else 0
            if above50 is not None:
                n_val_50 += 1
                n_a50 += 1 if above50 else 0
            if above200 is not None:
                n_val_200 += 1
                n_a200 += 1 if above200 else 0
            if new_hi is not None:
                n_val_hilo += 1
                n_hi += 1 if new_hi else 0
                n_lo += 1 if new_lo else 0

        pct_adv = n_adv / n_val_adv if n_val_adv else None
        pct_a50 = n_a50 / n_val_50 if n_val_50 else None
        pct_a200 = n_a200 / n_val_200 if n_val_200 else None
        net_hilo = (n_hi - n_lo) / n_val_hilo if n_val_hilo else None
        raw_daily.append((date, pct_adv, pct_a50, pct_a200, net_hilo))

    # --- pasada de buckets (expanding percentile, sin look-ahead) + retorno forward ---
    # guarda listas CRUDAS de retornos por (metrica, horizonte, era, bucket) -- necesarias para
    # el test de Welch contra baseline, no solo la media (leccion de la sesion VIX: comparar
    # contra el bucket opuesto no alcanza, hay que comparar contra el baseline real).
    tables = {m: {h: {"full": {}, "recent": {}} for h in HORIZONS} for m in metric_series}
    hist = {m: [] for m in metric_series}

    for i, (date, pct_adv, pct_a50, pct_a200, net_hilo) in enumerate(raw_daily):
        year = int(date[:4])
        era = "recent" if year in RECENT_YEARS else "full"
        eras = ("full",) if era == "full" else ("full", "recent")
        vals = {"pct_adv": pct_adv, "pct_above50": pct_a50, "pct_above200": pct_a200, "net_hilo": net_hilo}

        for m, v in vals.items():
            if v is None:
                continue
            pct_rank = expanding_percentile(hist[m], v) if i >= WARMUP else None
            bisect.insort(hist[m], v)
            b = bucket3(pct_rank)
            if b is None:
                continue
            for h in HORIZONS:
                if i + h >= len(raw_daily):
                    continue
                d0, dh = date, raw_daily[i + h][0]
                if d0 not in qqq or dh not in qqq:
                    continue
                fwd = qqq[dh] / qqq[d0] - 1
                for e in eras:
                    tables[m][h][e].setdefault(b, []).append(fwd)

    # --- baseline real (cualquier dia, separado por era) para el test de Welch ---
    baseline_returns = {h: {"full": [], "recent": []} for h in HORIZONS}
    for i in range(len(all_dates)):
        d0 = all_dates[i]
        if d0 not in qqq:
            continue
        year = int(d0[:4])
        era = "recent" if year in RECENT_YEARS else "full"
        eras = ("full",) if era == "full" else ("full", "recent")
        for h in HORIZONS:
            if i + h < len(all_dates) and all_dates[i + h] in qqq:
                fwd = qqq[all_dates[i + h]] / qqq[d0] - 1
                for e in eras:
                    baseline_returns[h][e].append(fwd)

    def print_and_welch(name, m):
        print(f"\n=== {name} ===")
        for h in HORIZONS:
            bf, br = baseline_returns[h]["full"], baseline_returns[h]["recent"]
            print(f"-- horizonte {h}d -- baseline full mean={sum(bf)/len(bf)*100:+.2f}% (n={len(bf)}), "
                  f"recent mean={sum(br)/len(br)*100:+.2f}% (n={len(br)})")
            print(f"{'bucket':<8}{'n(full)':>9}{'mean%(full)':>13}{'t_full':>8}"
                  f"{'n(rec)':>9}{'mean%(rec)':>12}{'t_rec':>8}")
            for b in ("low", "mid", "high"):
                fvals = tables[m][h]["full"].get(b, [])
                rvals = tables[m][h]["recent"].get(b, [])
                fm = f"{sum(fvals)/len(fvals)*100:+.2f}" if fvals else "--"
                rm = f"{sum(rvals)/len(rvals)*100:+.2f}" if rvals else "--"
                tf = welch_t(fvals, bf) if fvals else None
                tr = welch_t(rvals, br) if rvals else None
                tf_s = f"{tf:+.1f}" if tf is not None else "--"
                tr_s = f"{tr:+.1f}" if tr is not None else "--"
                print(f"{b:<8}{len(fvals):>9}{fm:>13}{tf_s:>8}{len(rvals):>9}{rm:>12}{tr_s:>8}")

    print_and_welch("1. % avanzando en la canasta", "pct_adv")
    print_and_welch("2. % arriba de SMA50 propia", "pct_above50")
    print_and_welch("3. % arriba de SMA200 propia", "pct_above200")
    print_and_welch("4. Nuevos maximos - minimos netos (20d)", "net_hilo")

    # --- 5. Breadth thrust: pct_adv cruza de <40% a >60% en <=10 dias de trading ---
    print("\n=== 5. Breadth thrust (pct_adv <40% -> >60% en <=10 dias) ===")
    thrust_starts = []
    window = deque(maxlen=11)
    for i, (date, pct_adv, *_ ) in enumerate(raw_daily):
        window.append((date, pct_adv))
        if len(window) < 11 or pct_adv is None:
            continue
        d0, p0 = window[0]
        if p0 is not None and p0 < 0.40 and pct_adv > 0.60:
            thrust_starts.append(i)  # marca el dia de la señal (confirmacion)
    print(f"Eventos de thrust detectados: {len(thrust_starts)}")
    for h in HORIZONS:
        rets = []
        for idx in thrust_starts:
            if idx + h < len(raw_daily):
                d0, dh = raw_daily[idx][0], raw_daily[idx + h][0]
                if d0 in qqq and dh in qqq:
                    rets.append(qqq[dh] / qqq[d0] - 1)
        if rets:
            mean = sum(rets) / len(rets)
            hit = sum(1 for r in rets if r > 0) / len(rets)
            bf = baseline_returns[h]["full"]
            base_mean = sum(bf) / len(bf)
            t = welch_t(rets, bf)
            t_s = f"{t:+.2f}" if t is not None else "n/a"
            print(f"  {h}d: n={len(rets)} mean={mean*100:+.2f}% hit={hit*100:.1f}%  vs baseline={base_mean*100:+.2f}%  Welch t={t_s}")
    print("\nFechas de los thrust:")
    for idx in thrust_starts:
        print(f"  {raw_daily[idx][0]}")


if __name__ == "__main__":
    main()
