"""Research exploratorio: fórmulas poco usadas en finanzas retail, pedido explícito del usuario
2026-08-19 ("chicharronera", despejes, raíces, potencias, e, letras griegas). QQQ 1-min 2016-2026,
ventanas de 10min, TODO calculado sin look-ahead (ver feedback_lookahead_bias_research.md -- la
lección de la sección anterior de esta misma sesión) y reportado full (2016-2026) vs recent
(2023-2026), igual disciplina que el resto de hoy.

1. GAMMA (curvatura, "la chicharronera"): la fórmula cuadrática resuelve a·x²+b·x+c=0 porque una
   parábola tiene curvatura constante -- acá tomamos la 2da derivada discreta de 3 cierres
   consecutivos (c[i-2], c[i-1], c[i]) como proxy de curvatura de PRECIO, sin ajustar ninguna
   parábola de verdad, solo usando la misma intuición (¿la trayectoria se está curvando hacia
   arriba o hacia abajo, y eso predice el próximo movimiento?). gamma_i = c[i] - 2·c[i-1] + c[i-2].
   Sin look-ahead: usa solo información de 3 barras YA CERRADAS.

2. ER (Efficiency Ratio de Kaufman, raíz del path-length): ratio entre desplazamiento neto y
   distancia recorrida en un lookback -- involucra la idea de "raíz"/normalización de un camino
   irregular contra su línea recta, no una raíz cuadrada literal pero sí el mismo tipo de álgebra
   de "despeje" (aislar cuánto de la distancia recorrida fue realmente productiva).
   ER = |c[i]-c[i-L]| / Σ|c[k]-c[k-1]| para k en (i-L, i].

3. Forma funcional potencia: ¿la relación entre tamaño del movimiento y reversión forward es mejor
   descripta con una potencia lineal, cuadrática, cúbica o raíz cuadrada? Se computa correlación de
   Pearson (stdlib puro) entre |retorno actual|^p (p en 0.5,1,2,3, signo preservado) y el retorno
   forward firmado -- terciles NO sirven para esto (una transformación monótona de una variable
   positiva no cambia el orden de sus terciles), por eso se usa correlación en vez de buckets.

Uso: python exotic_math_patterns.py [--window 10]
"""
import argparse
import csv
import math
from pathlib import Path

DATA_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"
RECENT_YEARS = {2023, 2024, 2025, 2026}
ER_LOOKBACK = 6  # ventanas (60min con ventana=10min)


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
        windows.append({"o": float(chunk[0]["o"]), "c": float(chunk[-1]["c"])})
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
    """Correlación de Pearson streaming (sumas simples, sin guardar los pares)."""
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


def run(window_min):
    gamma_tables = {"full": {}, "recent": {}}   # sign(gamma) -> Bucket
    er_tables = {"full": {}, "recent": {}}       # ER tercile -> Bucket
    power_corr = {p: {"full": Corr(), "recent": Corr()} for p in (0.5, 1, 2, 3)}

    # pasada 1: recolectar distribución de ER para fijar terciles globales
    er_values = []
    for date, year, bars in iter_day_bars():
        w = make_windows(bars, window_min)
        if len(w) < ER_LOOKBACK + 3:
            continue
        for i in range(ER_LOOKBACK, len(w) - 1):
            closes = [w[k]["c"] for k in range(i - ER_LOOKBACK, i + 1)]
            net = abs(closes[-1] - closes[0])
            path = sum(abs(closes[k] - closes[k - 1]) for k in range(1, len(closes)))
            if path > 0:
                er_values.append(net / path)
    er_values.sort()
    n_er = len(er_values)
    er_lo, er_hi = er_values[n_er // 3], er_values[2 * n_er // 3]
    print(f"ER terciles: lo={er_lo:.3f} hi={er_hi:.3f} (n={n_er})")

    # pasada 2: análisis real
    for date, year, bars in iter_day_bars():
        w = make_windows(bars, window_min)
        if len(w) < ER_LOOKBACK + 3:
            continue
        era = "recent" if year in RECENT_YEARS else "full"

        for i in range(ER_LOOKBACK, len(w) - 1):
            cur, nxt = w[i], w[i + 1]
            cur_ret = cur["c"] - cur["o"]
            fwd_ret = nxt["c"] - nxt["o"]
            fwd_raw = fwd_ret / cur["o"]  # SIN ajustar por signo -- estas pruebas son direccionales

            # --- 1. Gamma (curvatura, 3 cierres) ---
            if i >= 2:
                c0, c1, c2 = w[i - 2]["c"], w[i - 1]["c"], w[i]["c"]
                gamma = (c2 - 2 * c1 + c0) / cur["o"]
                if gamma != 0:
                    g_sign = "gamma_pos (curva hacia arriba)" if gamma > 0 else "gamma_neg (curva hacia abajo)"
                    for e in (("full",) if era == "full" else ("full", "recent")):
                        gamma_tables[e].setdefault(g_sign, Bucket()).add(fwd_raw)

            # --- 2. Efficiency Ratio ---
            closes = [w[k]["c"] for k in range(i - ER_LOOKBACK, i + 1)]
            net = abs(closes[-1] - closes[0])
            path = sum(abs(closes[k] - closes[k - 1]) for k in range(1, len(closes)))
            if path > 0 and cur_ret != 0:
                er = net / path
                er_bucket = bucket3(er, er_lo, er_hi)
                sign = 1 if cur_ret > 0 else -1
                fwd_signed = fwd_ret * sign / cur["o"]
                for e in (("full",) if era == "full" else ("full", "recent")):
                    er_tables[e].setdefault(er_bucket, Bucket()).add(fwd_signed)

            # --- 3. Forma funcional potencia ---
            if cur["o"] > 0:
                cur_ret_pct = cur_ret / cur["o"]
                for p in (0.5, 1, 2, 3):
                    x = math.copysign(abs(cur_ret_pct) ** p, cur_ret_pct)
                    for e in (("full",) if era == "full" else ("full", "recent")):
                        power_corr[p][e].add(x, fwd_raw)

    return gamma_tables, er_tables, power_corr


def print_bucket_table(name, tables):
    print(f"\n=== {name} ===")
    print(f"{'bucket':<28}{'n(full)':>9}{'fwd_bps(full)':>15}{'t(full)':>9}"
          f"{'n(rec)':>9}{'fwd_bps(rec)':>14}{'t(rec)':>8}")
    labels = sorted(tables["full"])
    for label in labels:
        f = tables["full"][label].stats()
        r = tables["recent"].get(label)
        rs = r.stats() if r else None
        if not f:
            continue
        rn = rs["n"] if rs else 0
        rb = f"{rs['mean_bps']:>14.3f}" if rs else f"{'--':>14}"
        rt = f"{rs['t']:>8.1f}" if rs else f"{'--':>8}"
        print(f"{label:<28}{f['n']:>9}{f['mean_bps']:>15.3f}{f['t']:>9.1f}{rn:>9}{rb}{rt}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=10)
    a = ap.parse_args()

    print(f"Exotic math patterns, ventana={a.window}min, full=2016-2026, recent=2023-2026")
    gamma_tables, er_tables, power_corr = run(a.window)

    print_bucket_table("1. GAMMA (curvatura de 3 cierres) -> retorno forward RAW (sin ajustar signo)", gamma_tables)
    print_bucket_table("2. Efficiency Ratio (Kaufman) -> retorno forward firmado (continuación=+)", er_tables)

    print("\n=== 3. Correlación (Pearson) entre |retorno_actual|^p (signo preservado) y retorno "
          "forward RAW ===")
    print(f"{'p':<6}{'r (full)':>12}{'r (recent)':>14}")
    for p in (0.5, 1, 2, 3):
        rf = power_corr[p]["full"].r()
        rr = power_corr[p]["recent"].r()
        print(f"{p:<6}{rf:>12.5f}{rr:>14.5f}" if rf is not None and rr is not None else f"{p:<6}  n/a")


if __name__ == "__main__":
    main()
