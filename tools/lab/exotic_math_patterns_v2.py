"""Segunda tanda de matemática "no usada en finanzas retail", pedido explícito del usuario
2026-08-20 ("continúa haciendo pruebas... ponte creativo, metodologías matemáticas novedosas").
QQQ 1-min 2016-2026, ventanas de 10min, TODO expanding/rolling hacia atrás únicamente (cero
look-ahead -- ver feedback_lookahead_bias_research.md), full (2016-2026) vs recent (2023-2026),
misma disciplina del resto de la sesión anterior.

1. HURST EXPONENT (R/S, análisis de rango reescalado) -- mide si una serie es de reversión a la
   media (H<0.5), paseo aleatorio (H=0.5) o persistente/tendencial (H>0.5). Estimador de una sola
   escala sobre lookback de 20 ventanas (200min): Z_k = cumsum(r_k - mean(r)), R = max(Z)-min(Z),
   S = stdev(r), H = log(R/S) / log(L).

2. ENTROPÍA DE SHANNON de la secuencia de signos (up/down) en el mismo lookback -- entropía baja
   = secuencia predecible/direccional, entropía alta (techo 1.0 bit) = 50/50 moneda al aire.

3. RACHAS (runs, espíritu del test de Wald-Wolfowitz) -- longitud de la racha de ventanas
   consecutivas del mismo signo terminando en la actual, sin mirar adelante.

4. RETROCESOS DE FIBONACCI -- posición dentro del rango de la sesión (razón áurea: niveles
   0.236/0.382/0.5/0.618/0.786) pero con rango EXPANDIENTE (running_high/running_low, warmup 4
   ventanas) -- a diferencia del intento anterior de esta sesión que tenía look-ahead, acá se
   corrige desde el diseño.

5. ACF (función de autocorrelación) multi-lag, k=1..10 ventanas -- busca periodicidad natural
   (ciclo) en el retorno de 10min, más allá del lag-1 ya cubierto en timeframe_continuation_sweep.

6. LEY DE BENFORD sobre volumen por ventana -- primer dígito significativo del volumen vs la
   distribución esperada de Benford, bucketed contra volatilidad forward (control tipo "absurdo"
   como fase lunar/último dígito, pero con una pregunta real: ¿el dígito líder del volumen anticipa
   algo, o es puro ruido de escala como predice la ley?).

Uso: python exotic_math_patterns_v2.py [--window 10]
"""
import argparse
import csv
import math
from collections import deque
from pathlib import Path

DATA_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"
RECENT_YEARS = {2023, 2024, 2025, 2026}
LOOKBACK = 20       # ventanas para Hurst/entropía (200min)
RANGE_WARMUP = 4    # ventanas antes de confiar en running_high/low (fib)
ACF_MAXLAG = 10
FIB_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786]
FIB_TOL = 0.04


def iter_day_bars():
    for year in range(2016, 2027):
        path = DATA_DIR / f"{year}.csv"
        if not path.exists():
            continue
        cur_date, cur_bars = None, []
        with path.open() as f:
            for row in csv.DictReader(f):
                date = row["t"][:10]
                if date != cur_date:
                    if cur_bars:
                        yield cur_date, year, cur_bars
                    cur_date, cur_bars = date, []
                cur_bars.append(row)
            if cur_bars:
                yield cur_date, year, cur_bars


def make_windows(bars, n):
    windows = []
    for i in range(0, len(bars) - n + 1, n):
        chunk = bars[i:i + n]
        windows.append({
            "o": float(chunk[0]["o"]), "c": float(chunk[-1]["c"]),
            "h": max(float(x["h"]) for x in chunk),
            "l": min(float(x["l"]) for x in chunk),
            "v": sum(float(x["v"]) for x in chunk),
        })
    return windows


class Bucket:
    def __init__(self):
        self.n, self.s, self.ss = 0, 0.0, 0.0

    def add(self, x):
        self.n += 1
        self.s += x
        self.ss += x * x

    def stats(self):
        if self.n == 0:
            return None
        mean = self.s / self.n
        var = self.ss / self.n - mean * mean
        se = (var / self.n) ** 0.5 if var > 0 else 0.0
        return {"n": self.n, "mean_bps": mean * 10000, "t": mean / se if se > 0 else 0.0}


class Corr:
    def __init__(self):
        self.n, self.sx, self.sy, self.sxx, self.syy, self.sxy = 0, 0.0, 0.0, 0.0, 0.0, 0.0

    def add(self, x, y):
        self.n += 1
        self.sx += x; self.sy += y
        self.sxx += x * x; self.syy += y * y
        self.sxy += x * y

    def r(self):
        if self.n < 2:
            return None
        cov = self.sxy / self.n - (self.sx / self.n) * (self.sy / self.n)
        vx = self.sxx / self.n - (self.sx / self.n) ** 2
        vy = self.syy / self.n - (self.sy / self.n) ** 2
        denom = (vx * vy) ** 0.5
        return cov / denom if denom > 0 else None


def bucket3(x, lo, hi):
    return "low" if x <= lo else ("high" if x >= hi else "mid")


def hurst_rs(returns):
    L = len(returns)
    mean = sum(returns) / L
    dev = [r - mean for r in returns]
    cum = []
    running = 0.0
    for d in dev:
        running += d
        cum.append(running)
    R = max(cum) - min(cum)
    var = sum(r * r for r in dev) / L
    S = var ** 0.5
    if R <= 0 or S <= 0:
        return None
    return math.log(R / S) / math.log(L)


def benford_bucket(v):
    if v < 1:
        return None
    s = str(int(v))
    d = s[0]
    return d if d != "0" else None


def run(window_min):
    hurst_tables = {"full": {}, "recent": {}}
    ent_tables = {"full": {}, "recent": {}}
    run_tables = {"full": {}, "recent": {}}
    fib_tables = {"full": {}, "recent": {}}
    benford_tables = {"full": {}, "recent": {}}
    acf_full = {k: Corr() for k in range(1, ACF_MAXLAG + 1)}
    acf_recent = {k: Corr() for k in range(1, ACF_MAXLAG + 1)}

    # pasada 1: distribución de Hurst y entropía para fijar terciles globales
    hurst_vals, ent_vals = [], []
    for date, year, bars in iter_day_bars():
        w = make_windows(bars, window_min)
        if len(w) < LOOKBACK + 3:
            continue
        rets = [math.log(w[k]["c"] / w[k - 1]["c"]) for k in range(1, len(w))]
        for i in range(LOOKBACK, len(rets)):
            seg = rets[i - LOOKBACK:i]
            h = hurst_rs(seg)
            if h is not None:
                hurst_vals.append(h)
            ups = sum(1 for r in seg if r > 0)
            downs = sum(1 for r in seg if r < 0)
            tot = ups + downs
            if tot > 0:
                p_up, p_down = ups / tot, downs / tot
                ent = 0.0
                for p in (p_up, p_down):
                    if p > 0:
                        ent -= p * math.log2(p)
                ent_vals.append(ent)
    hurst_vals.sort(); ent_vals.sort()
    nh, ne = len(hurst_vals), len(ent_vals)
    h_lo, h_hi = hurst_vals[nh // 3], hurst_vals[2 * nh // 3]
    e_lo, e_hi = ent_vals[ne // 3], ent_vals[2 * ne // 3]
    print(f"Hurst terciles: lo={h_lo:.3f} hi={h_hi:.3f} (n={nh})")
    print(f"Entropy terciles: lo={e_lo:.3f} hi={e_hi:.3f} (n={ne})")

    # pasada 2: análisis real
    for date, year, bars in iter_day_bars():
        w = make_windows(bars, window_min)
        if len(w) < LOOKBACK + 3:
            continue
        era = "recent" if year in RECENT_YEARS else "full"
        eras = ("full",) if era == "full" else ("full", "recent")

        rets = [math.log(w[k]["c"] / w[k - 1]["c"]) for k in range(1, len(w))]
        acf_buf = deque(maxlen=ACF_MAXLAG + 1)
        running_high, running_low = None, None
        streak_sign, streak_len = 0, 0

        for i in range(1, len(w)):
            cur, nxt = w[i], w[i + 1] if i + 1 < len(w) else None
            if nxt is None:
                continue
            cur_ret = rets[i - 1]
            fwd_ret = (nxt["c"] - nxt["o"]) / cur["o"]

            # running range (expanding, warmup) para Fibonacci
            if running_high is None:
                running_high, running_low = cur["h"], cur["l"]
            else:
                running_high = max(running_high, cur["h"])
                running_low = min(running_low, cur["l"])

            # --- 1 & 2: Hurst / Entropy (necesitan LOOKBACK retornos previos) ---
            if i - 1 >= LOOKBACK:
                seg = rets[i - 1 - LOOKBACK:i - 1]
                h = hurst_rs(seg)
                if h is not None:
                    hb = bucket3(h, h_lo, h_hi)
                    sign = 1 if cur_ret > 0 else (-1 if cur_ret < 0 else 0)
                    fwd_signed = fwd_ret * sign
                    if sign != 0:
                        for e in eras:
                            hurst_tables[e].setdefault(hb, Bucket()).add(fwd_signed)

                ups = sum(1 for r in seg if r > 0)
                downs = sum(1 for r in seg if r < 0)
                tot = ups + downs
                if tot > 0:
                    p_up, p_down = ups / tot, downs / tot
                    ent = 0.0
                    for p in (p_up, p_down):
                        if p > 0:
                            ent -= p * math.log2(p)
                    eb = bucket3(ent, e_lo, e_hi)
                    sign = 1 if cur_ret > 0 else (-1 if cur_ret < 0 else 0)
                    if sign != 0:
                        for e in eras:
                            ent_tables[e].setdefault(eb, Bucket()).add(fwd_ret * sign)

            # --- 3: Racha ---
            sign = 1 if cur_ret > 0 else (-1 if cur_ret < 0 else 0)
            if sign == 0:
                streak_len = 0
            elif sign == streak_sign:
                streak_len += 1
            else:
                streak_sign, streak_len = sign, 1
            if streak_len > 0:
                rb = "1" if streak_len == 1 else ("2" if streak_len == 2 else "3+")
                for e in eras:
                    run_tables[e].setdefault(rb, Bucket()).add(fwd_ret * streak_sign)

            # --- 4: Fibonacci (expanding, warmup) ---
            if i >= RANGE_WARMUP and running_high > running_low:
                rp = (running_high - cur["c"]) / (running_high - running_low)
                near_fib = "far"
                for lvl in FIB_LEVELS:
                    if abs(rp - lvl) <= FIB_TOL:
                        near_fib = f"near_{lvl}"
                        break
                for e in eras:
                    fib_tables[e].setdefault(near_fib, Bucket()).add(fwd_ret)

            # --- 5: ACF multi-lag ---
            acf_buf.append(cur_ret)
            if len(acf_buf) == ACF_MAXLAG + 1:
                newest = acf_buf[-1]
                for k in range(1, ACF_MAXLAG + 1):
                    older = acf_buf[-1 - k]
                    acf_full[k].add(older, newest)
                    if era == "recent":
                        acf_recent[k].add(older, newest)

            # --- 6: Benford (primer dígito del volumen de la ventana) ---
            d = benford_bucket(cur["v"])
            if d is not None:
                for e in eras:
                    benford_tables[e].setdefault(d, Bucket()).add(abs(fwd_ret))

    return hurst_tables, ent_tables, run_tables, fib_tables, benford_tables, acf_full, acf_recent


def print_bucket_table(name, tables, order=None):
    print(f"\n=== {name} ===")
    print(f"{'bucket':<16}{'n(full)':>9}{'fwd_bps(full)':>15}{'t(full)':>9}"
          f"{'n(rec)':>9}{'fwd_bps(rec)':>14}{'t(rec)':>8}")
    labels = order if order else sorted(tables["full"])
    for label in labels:
        if label not in tables["full"]:
            continue
        f = tables["full"][label].stats()
        r = tables["recent"].get(label)
        rs = r.stats() if r else None
        if not f:
            continue
        rn = rs["n"] if rs else 0
        rb = f"{rs['mean_bps']:>14.3f}" if rs else f"{'--':>14}"
        rt = f"{rs['t']:>8.1f}" if rs else f"{'--':>8}"
        print(f"{label:<16}{f['n']:>9}{f['mean_bps']:>15.3f}{f['t']:>9.1f}{rn:>9}{rb}{rt}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=10)
    a = ap.parse_args()

    print(f"Exotic math patterns v2, ventana={a.window}min, full=2016-2026, recent=2023-2026")
    hurst_t, ent_t, run_t, fib_t, benford_t, acf_full, acf_recent = run(a.window)

    print_bucket_table("1. Hurst (R/S, lookback 20 ventanas) -> fwd_ret en direccion del retorno actual", hurst_t,
                        order=["low", "mid", "high"])
    print_bucket_table("2. Entropia de Shannon (signos, lookback 20) -> fwd_ret en direccion del retorno actual", ent_t,
                        order=["low", "mid", "high"])
    print_bucket_table("3. Longitud de racha -> fwd_ret en direccion de la racha", run_t,
                        order=["1", "2", "3+"])
    print_bucket_table("4. Cercania a nivel Fibonacci (rango EXPANDIENTE) -> fwd_ret RAW", fib_t,
                        order=[f"near_{l}" for l in FIB_LEVELS] + ["far"])
    print_bucket_table("6. Primer digito de Benford (volumen ventana) -> |fwd_ret| (volatilidad)", benford_t,
                        order=[str(d) for d in range(1, 10)])

    print("\n=== 5. ACF multi-lag (retorno ventana_t vs ventana_t-k), k=1..10 ===")
    print(f"{'k':<4}{'r (full)':>12}{'r (recent)':>14}")
    for k in range(1, ACF_MAXLAG + 1):
        rf = acf_full[k].r()
        rr = acf_recent[k].r()
        rf_s = f"{rf:>12.5f}" if rf is not None else f"{'n/a':>12}"
        rr_s = f"{rr:>14.5f}" if rr is not None else f"{'n/a':>14}"
        print(f"{k:<4}{rf_s}{rr_s}")


if __name__ == "__main__":
    main()
