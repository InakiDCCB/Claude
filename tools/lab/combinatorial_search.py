"""Búsqueda combinatoria de hipótesis ya probadas en la sesión, pedido explícito del usuario:
"¿si combinamos entre sí diferentes hipótesis que ya hemos tenido... combinaciones de 2, 3 y hasta
4?". ADVERTENCIA METODOLÓGICA aplicada desde el diseño, no despues: probar C(6,2)+C(6,3)+C(6,4)=50
combinaciones es un problema de comparaciones múltiples real -- a alpha=0.05 sin corregir,
esperamos ~2-3 "significativos" por puro azar aunque NO haya ninguna señal real. Este script:
1. Corrige con Bonferroni (alpha_familia=0.05 / 50 combos ~ requiere |t| mayor a ~2.9-3.3 según
   cuantas combinaciones realmente se testean, no solo las que se intentan).
2. Exige un minimo de episodios independientes (>=15) para siquiera correr el test -- muchas
   combinaciones de 4 condiciones tercil (1/3^4 ~ 1.2% de los dias) van a tener muy pocos episodios,
   se reportan como "insuficiente muestra", no como null.
3. Reporta TODO (no solo los que sobreviven) para que la tasa de falsos positivos esperada sea
   auditable.

6 condiciones DISTINTAS (no redundantes entre si, a diferencia de VIX/breadth que resultaron ser
la misma señal con 64% de solapamiento):
  A. VIX alto (tercil, expanding)                    -- estres implicito (opciones)
  B. Breadth debil (%<SMA50 canasta, tercil)          -- estres de accion de precio
  C. QQQ cierre debajo de su EMA21 diaria             -- el UNICO sobreviviente individual de la sesion
  D. QQQ cerca del minimo de su rango de 20 dias       -- version diaria de "near-low" (murio intradia)
  E. Racha de 2+ dias consecutivos a la baja           -- version diaria de "rachas" (tanda 2)
  F. Volatilidad realizada alta (stdev 20d retornos, tercil) -- distinta de VIX (implicita vs realizada)

Uso: python combinatorial_search.py
"""
import bisect
import csv
import itertools
import json
import math
from collections import deque
from pathlib import Path

QQQ_PATH = Path(__file__).parents[1] / "data" / "qqq_daily_full.json"
VIX_DIR = Path(__file__).parents[1] / "data" / "vix"
BREADTH_DIR = Path(__file__).parents[1] / "data" / "breadth"
GAP_TOLERANCE = 3
HORIZONS = (5, 20, 60)
MIN_EPISODES = 15
FAMILY_ALPHA = 0.05


def load_qqq():
    raw = json.loads(QQQ_PATH.read_text())
    raw.sort(key=lambda b: b["t"])
    return raw


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


def expanding_percentile(sorted_hist, x):
    if not sorted_hist:
        return None
    return bisect.bisect_left(sorted_hist, x) / len(sorted_hist)


def welch_t(a, b):
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = (va / na + vb / nb) ** 0.5
    return None if se == 0 else (ma - mb) / se


def find_episodes(flags, n):
    raw_runs = []
    i = 0
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
    qqq_bars = load_qqq()
    qqq = {b["t"][:10]: b["c"] for b in qqq_bars}
    vix = load_vix_csv("VIX")
    basket = load_basket()

    dates = sorted(set(qqq) & set(vix) & set().union(*[set(d) for d in basket.values()]))
    n = len(dates)
    print(f"Fechas alineadas: {n} ({dates[0]} -> {dates[-1]})")
    closes = [qqq[d] for d in dates]

    # --- A. VIX alto ---
    vix_hist, vix_pct = [], []
    for i, date in enumerate(dates):
        v = vix[date]
        vix_pct.append(expanding_percentile(vix_hist, v) if i >= 60 else None)
        bisect.insort(vix_hist, v)
    flag_A = [bool(p is not None and p > 0.667) for p in vix_pct]

    # --- B. Breadth debil (%<SMA50) ---
    class SymState:
        def __init__(self):
            self.buf = deque(maxlen=50); self.s = 0.0

        def read(self, close):
            above = close > (self.s / 50) if len(self.buf) == 50 else None
            if len(self.buf) == 50:
                self.s -= self.buf[0]
            self.buf.append(close); self.s += close
            return above

    states = {sym: SymState() for sym in basket}
    breadth_hist, breadth_pct = [], []
    for i, date in enumerate(dates):
        n_a = n_v = 0
        for sym, series in basket.items():
            if date not in series:
                continue
            a = states[sym].read(series[date])
            if a is not None:
                n_v += 1; n_a += 1 if a else 0
        raw = n_a / n_v if n_v else None
        p = expanding_percentile(breadth_hist, raw) if (i >= 210 and raw is not None) else None
        breadth_pct.append(p)
        if raw is not None:
            bisect.insort(breadth_hist, raw)
    flag_B = [bool(p is not None and p < 0.333) for p in breadth_pct]

    # --- C. QQQ debajo de su EMA21 (seed SMA de los primeros 21) ---
    ema21 = [None] * n
    alpha = 2 / (21 + 1)
    seed_buf = []
    cur_ema = None
    for i, c in enumerate(closes):
        if cur_ema is None:
            seed_buf.append(c)
            if len(seed_buf) == 21:
                cur_ema = sum(seed_buf) / 21
                ema21[i] = cur_ema
        else:
            cur_ema = c * alpha + cur_ema * (1 - alpha)
            ema21[i] = cur_ema
    flag_C = [bool(ema21[i] is not None and closes[i] < ema21[i]) for i in range(n)]

    # --- D. Cerca del minimo del rango de 20 dias (tercil bajo de posicion en rango) ---
    win20 = deque(maxlen=20)
    range_pct = [None] * n
    rp_hist = []
    for i, c in enumerate(closes):
        win20.append(c)
        if len(win20) == 20:
            hi, lo = max(win20), min(win20)
            rp = (c - lo) / (hi - lo) if hi > lo else None  # 0=en el minimo, 1=en el maximo
            if rp is not None:
                pct = expanding_percentile(rp_hist, rp) if i >= 60 else None
                range_pct[i] = pct
                bisect.insort(rp_hist, rp)
    flag_D = [bool(range_pct[i] is not None and range_pct[i] < 0.333) for i in range(n)]

    # --- E. Racha de 2+ dias consecutivos a la baja ---
    flag_E = [False] * n
    streak = 0
    for i in range(1, n):
        if closes[i] < closes[i - 1]:
            streak += 1
        else:
            streak = 0
        flag_E[i] = streak >= 2

    # --- F. Volatilidad realizada alta (stdev 20d de log-retornos, tercil) ---
    logrets = [None] + [math.log(closes[i] / closes[i - 1]) for i in range(1, n)]
    win_vol = deque(maxlen=20)
    vol_hist, vol_pct = [], [None] * n
    for i in range(1, n):
        win_vol.append(logrets[i])
        if len(win_vol) == 20:
            mean = sum(win_vol) / 20
            var = sum((x - mean) ** 2 for x in win_vol) / 20
            sd = var ** 0.5
            pct = expanding_percentile(vol_hist, sd) if i >= 60 else None
            vol_pct[i] = pct
            bisect.insort(vol_hist, sd)
    flag_F = [bool(vol_pct[i] is not None and vol_pct[i] > 0.667) for i in range(n)]

    flags = {"A_vix_alto": flag_A, "B_breadth_debil": flag_B, "C_bajo_ema21": flag_C,
              "D_cerca_minimo20d": flag_D, "E_racha_baja2": flag_E, "F_vol_realizada_alta": flag_F}

    for name, f in flags.items():
        print(f"  {name}: {sum(f)} dias ({sum(f)/n*100:.1f}%)")

    baseline = {h: [] for h in HORIZONS}
    for i in range(n):
        d0 = dates[i]
        if d0 not in qqq:
            continue
        for h in HORIZONS:
            if i + h < n and dates[i + h] in qqq:
                baseline[h].append(qqq[dates[i + h]] / qqq[d0] - 1)

    names = list(flags.keys())
    results = []
    total_combos = 0
    for size in (2, 3, 4):
        for combo in itertools.combinations(names, size):
            total_combos += 1
            joint = [all(flags[k][i] for k in combo) for i in range(n)]
            episodes = find_episodes(joint, n)
            rows = []
            for s, e in episodes:
                entry = dates[s]
                if entry not in qqq:
                    continue
                rows.append((s, entry))
            n_ep = len(rows)
            if n_ep < MIN_EPISODES:
                results.append({"combo": combo, "size": size, "n_ep": n_ep, "status": "insuficiente"})
                continue
            best_t, best_h = None, None
            per_h = {}
            for h in HORIZONS:
                vals = []
                for s, entry in rows:
                    tgt = s + h
                    if tgt < n and dates[tgt] in qqq:
                        vals.append(qqq[dates[tgt]] / qqq[entry] - 1)
                t = welch_t(vals, baseline[h]) if len(vals) >= 2 else None
                per_h[h] = (t, len(vals), sum(vals) / len(vals) if vals else None)
                if t is not None and (best_t is None or abs(t) > abs(best_t)):
                    best_t, best_h = t, h
            results.append({"combo": combo, "size": size, "n_ep": n_ep, "status": "ok",
                             "per_h": per_h, "best_t": best_t, "best_h": best_h})

    # correccion de Bonferroni sobre las combinaciones REALMENTE testeadas (con muestra suficiente)
    tested = [r for r in results if r["status"] == "ok"]
    insuf = [r for r in results if r["status"] == "insuficiente"]
    n_tested = len(tested) * len(HORIZONS)  # cada combo aporta hasta 3 tests (uno por horizonte)
    from statistics import NormalDist
    if n_tested > 0:
        p_corrected = FAMILY_ALPHA / n_tested
        z_bonf = NormalDist().inv_cdf(1 - p_corrected / 2)
    else:
        z_bonf = None

    print(f"\nTotal combinaciones (2+3+4): {total_combos}. Con muestra suficiente (>={MIN_EPISODES} "
          f"episodios): {len(tested)}. Insuficientes: {len(insuf)}.")
    print(f"Tests individuales (combos x horizontes) = {n_tested}. Umbral Bonferroni "
          f"(familia alpha={FAMILY_ALPHA}): |t| > {z_bonf:.2f}" if z_bonf else "sin tests suficientes")
    print(f"(referencia: umbral SIN corregir habria sido |t|>1.96)")

    tested.sort(key=lambda r: abs(r["best_t"]) if r["best_t"] is not None else 0, reverse=True)
    print(f"\n{'combo':<45}{'n_ep':>6}{'best_h':>7}{'best_t':>8}  veredicto")
    for r in tested:
        combo_s = "+".join(c.split("_")[0] for c in r["combo"])
        bt = r["best_t"]
        bt_s = f"{bt:+.2f}" if bt is not None else "n/a"
        verdict = "CANDIDATO (sobrevive Bonferroni)" if (bt is not None and z_bonf and abs(bt) > z_bonf) else ""
        print(f"{combo_s:<45}{r['n_ep']:>6}{r['best_h']:>7}{bt_s:>8}  {verdict}")

    survivors = [r for r in tested if r["best_t"] is not None and z_bonf and abs(r["best_t"]) > z_bonf]
    print(f"\nSobrevivientes tras Bonferroni: {len(survivors)} de {len(tested)} combos testeados "
          f"({n_tested} tests individuales).")
    if survivors:
        print("Detalle de sobrevivientes:")
        for r in survivors:
            print(f"  {r['combo']}: {r['per_h']}")


if __name__ == "__main__":
    main()
