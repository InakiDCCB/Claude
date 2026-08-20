"""Research exploratorio: minería de patrones intradía en QQQ 1-min (2016-2026, todo lo que
Alpaca tiene -- ver tools/fetch_1min_full.py). Streaming, pure-stdlib, dos pasadas por año
(memoria acotada: nunca carga más de un día de barras a la vez).

Preguntas que responde (pedido del usuario 2026-08-19, ver project_macro_cycle_research.md):
1. Estacionalidad: ¿hay bloques de 5-min ET / día-de-semana / mes / día-OPEX con retorno o
   volatilidad sistemáticamente distintos del resto?
2. Comportamiento condicional de movimientos de 5-min según:
   - "fuerza implícita" = |retorno de la ventana| / ATR-intradía-reciente (¿el movimiento es grande
     relativo a lo normal de HOY, o es ruido normal?)
   - volumen relativo = volumen de la ventana / promedio móvil de volumen intradía reciente
   ¿El retorno de la ventana SIGUIENTE (misma dirección = continuación, opuesta = reversión)
   depende de esas dos variables? Se reporta como tabla fuerza×volumen con n, retorno medio
   forward, y % continuación.

Metodología: 2 pasadas por año-CSV. Pasada 1 acumula la distribución de "fuerza" y "volumen
relativo" para fijar terciles GLOBALES (no por año, para comparar años entre sí). Pasada 2 aplica
esos terciles y acumula: (a) estacionalidad (sum/sumsq/n por bucket), (b) tabla condicional
fuerza×volumen -> retorno forward. Ambas pasadas son streaming por día -- nunca se guarda más de
un día de barras 1-min en memoria a la vez.

Uso: python micro_pattern_mining.py [--since 2016] [--until 2026] [--window 5]
"""
import argparse
import csv
import datetime as dt
import statistics
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"

ATR_LOOKBACK = 12   # ventanas de N-min previas (mismo día) para el ATR-intradía-reciente
VOL_LOOKBACK = 12
WARMUP = ATR_LOOKBACK  # ventanas descartadas al inicio de cada día (baseline sin sembrar)


def iter_day_bars(year):
    """Yields (date_str, [bars]) -- bars agrupadas por día calendario ET, en orden."""
    path = DATA_DIR / f"{year}.csv"
    if not path.exists():
        return
    cur_date, cur_bars = None, []
    with path.open() as f:
        for row in csv.DictReader(f):
            date = row["t"][:10]
            if date != cur_date:
                if cur_bars:
                    yield cur_date, cur_bars
                cur_date, cur_bars = date, []
            cur_bars.append(row)
        if cur_bars:
            yield cur_date, cur_bars


def make_windows(bars, n):
    """Agrupa barras 1-min consecutivas en ventanas de n barras (open primera, close última)."""
    windows = []
    for i in range(0, len(bars) - n + 1, n):
        chunk = bars[i:i + n]
        o = float(chunk[0]["o"])
        c = float(chunk[-1]["c"])
        h = max(float(b["h"]) for b in chunk)
        l = min(float(b["l"]) for b in chunk)
        v = sum(float(b["v"]) for b in chunk)
        t = chunk[0]["t"]
        windows.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    return windows


def et_bucket(t_iso, n):
    """Bloque de n-min desde 9:30 ET (usa el timestamp UTC ISO tal cual, offset fijo de sesión
    RTH -- las barras ya vienen filtradas 13:30-20:00 UTC, offset ET no importa para el bucket
    relativo a la apertura salvo el día de cambio DST, error de +/-1 bucket, aceptable para esto)."""
    hh, mm = int(t_iso[11:13]), int(t_iso[14:16])
    minutes_from_1330utc = (hh * 60 + mm) - (13 * 60 + 30)
    return minutes_from_1330utc // n


def is_opex(date_str):
    d = dt.date.fromisoformat(date_str)
    return d.weekday() == 4 and 15 <= d.day <= 21


class Acc:
    """Acumulador sum/sumsq/n para media y stdev streaming."""
    def __init__(self):
        self.n = 0
        self.s = 0.0
        self.ss = 0.0

    def add(self, x):
        self.n += 1
        self.s += x
        self.ss += x * x

    def mean(self):
        return self.s / self.n if self.n else None

    def std(self):
        if self.n < 2:
            return None
        var = (self.ss - self.s * self.s / self.n) / (self.n - 1)
        return var ** 0.5 if var > 0 else 0.0


def pass1_collect_distributions(years, n):
    """Devuelve listas de (strength, vol_ratio) de TODAS las ventanas válidas, todos los años."""
    strengths, vol_ratios = [], []
    for year in years:
        for date, bars in iter_day_bars(year):
            windows = make_windows(bars, n)
            if len(windows) < WARMUP + 2:
                continue
            atr_win = [abs(w["c"] - w["o"]) for w in windows[:ATR_LOOKBACK]]
            vol_win = [w["v"] for w in windows[:VOL_LOOKBACK]]
            for i in range(WARMUP, len(windows) - 1):
                w = windows[i]
                atr = sum(atr_win) / len(atr_win) if atr_win else None
                vol_avg = sum(vol_win) / len(vol_win) if vol_win else None
                ret = (w["c"] - w["o"]) / w["o"]
                if atr and w["o"] and vol_avg:
                    strength = abs(ret) / (atr / w["o"]) if atr > 0 else None
                    vol_ratio = w["v"] / vol_avg if vol_avg > 0 else None
                    if strength is not None and vol_ratio is not None:
                        strengths.append(strength)
                        vol_ratios.append(vol_ratio)
                atr_win = atr_win[1:] + [abs(w["c"] - w["o"])]
                vol_win = vol_win[1:] + [w["v"]]
    return strengths, vol_ratios


def terciles(values):
    s = sorted(values)
    n = len(s)
    return s[n // 3], s[2 * n // 3]


def bucket3(x, t1, t2):
    return "low" if x <= t1 else ("high" if x > t2 else "med")


def pass2_analyze(years, n, str_t, vol_t):
    seasonality = {
        "et_bucket": defaultdict(Acc), "dow": defaultdict(Acc),
        "month": defaultdict(Acc), "opex": defaultdict(Acc),
    }
    cond = defaultdict(lambda: {"n": 0, "continue_n": 0, "fwd_ret_sum": 0.0})

    for year in years:
        for date, bars in iter_day_bars(year):
            windows = make_windows(bars, n)
            if len(windows) < WARMUP + 2:
                continue
            d = dt.date.fromisoformat(date)
            opex = is_opex(date)
            atr_win = [abs(w["c"] - w["o"]) for w in windows[:ATR_LOOKBACK]]
            vol_win = [w["v"] for w in windows[:VOL_LOOKBACK]]

            for i, w in enumerate(windows):
                ret = (w["c"] - w["o"]) / w["o"]
                seasonality["et_bucket"][et_bucket(w["t"], n)].add(ret)
                seasonality["dow"][d.weekday()].add(ret)
                seasonality["month"][d.month].add(ret)
                seasonality["opex"][opex].add(ret)

            for i in range(WARMUP, len(windows) - 1):
                w, w_next = windows[i], windows[i + 1]
                atr = sum(atr_win) / len(atr_win) if atr_win else None
                vol_avg = sum(vol_win) / len(vol_win) if vol_win else None
                ret = (w["c"] - w["o"]) / w["o"]
                fwd_ret = (w_next["c"] - w_next["o"]) / w_next["o"]
                if atr and w["o"] and vol_avg and atr > 0 and vol_avg > 0 and ret != 0:
                    strength = abs(ret) / (atr / w["o"])
                    vol_ratio = w["v"] / vol_avg
                    key = (bucket3(strength, *str_t), bucket3(vol_ratio, *vol_t))
                    sign = 1 if ret > 0 else -1
                    fwd_signed = fwd_ret * sign  # + = continuación, - = reversión
                    c = cond[key]
                    c["n"] += 1
                    c["fwd_ret_sum"] += fwd_signed
                    if fwd_signed > 0:
                        c["continue_n"] += 1
                atr_win = atr_win[1:] + [abs(w["c"] - w["o"])]
                vol_win = vol_win[1:] + [w["v"]]

    return seasonality, cond


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=2016)
    ap.add_argument("--until", type=int, default=2026)
    ap.add_argument("--window", type=int, default=5, help="tamaño de ventana en barras 1-min")
    a = ap.parse_args()
    years = list(range(a.since, a.until + 1))
    n = a.window

    print(f"Pasada 1/2: recolectando distribución de fuerza/volumen ({years[0]}-{years[-1]}, ventana={n}min)...")
    strengths, vol_ratios = pass1_collect_distributions(years, n)
    if not strengths:
        print("Sin datos -- ¿corriste tools/fetch_1min_full.py?")
        return
    str_t = terciles(strengths)
    vol_t = terciles(vol_ratios)
    print(f"  n={len(strengths)} ventanas. terciles fuerza={str_t}, terciles volumen={vol_t}")

    print("Pasada 2/2: estacionalidad + tabla condicional...")
    seasonality, cond = pass2_analyze(years, n, str_t, vol_t)

    print(f"\n=== Estacionalidad -- retorno medio por bloque de {n}-min ET (top/bottom 5 por |mean|) ===")
    et_items = [(k, ac.mean(), ac.std(), ac.n) for k, ac in seasonality["et_bucket"].items() if ac.n > 30]
    et_items.sort(key=lambda x: abs(x[1]))
    for k, m, s, cnt in et_items[-5:][::-1]:
        et_min = k * n
        hh, mm = 9 + (30 + et_min) // 60, (30 + et_min) % 60
        print(f"  bloque ET {hh:02d}:{mm:02d}  mean_ret={m*100:+.4f}%  std={s*100:.4f}%  n={cnt}")

    print(f"\n=== Estacionalidad -- día de semana (0=Lun..4=Vie) ===")
    for k in sorted(seasonality["dow"]):
        ac = seasonality["dow"][k]
        print(f"  dow={k}  mean_ret={ac.mean()*100:+.5f}%  std={ac.std()*100:.4f}%  n={ac.n}")

    print(f"\n=== Estacionalidad -- mes ===")
    for k in sorted(seasonality["month"]):
        ac = seasonality["month"][k]
        print(f"  mes={k:2d}  mean_ret={ac.mean()*100:+.5f}%  std={ac.std()*100:.4f}%  n={ac.n}")

    print(f"\n=== Estacionalidad -- OPEX (3er viernes) vs resto ===")
    for k in (True, False):
        ac = seasonality["opex"][k]
        if ac.n:
            print(f"  opex={k}  mean_ret={ac.mean()*100:+.5f}%  std={ac.std()*100:.4f}%  n={ac.n}")

    print(f"\n=== Tabla condicional: fuerza x volumen -> retorno forward (ventana siguiente) ===")
    print(f"{'fuerza':<8}{'volumen':<8}{'n':>10}{'%continuación':>15}{'fwd_ret_medio':>16}")
    for str_b in ("low", "med", "high"):
        for vol_b in ("low", "med", "high"):
            c = cond.get((str_b, vol_b))
            if c and c["n"] > 0:
                pct_cont = 100 * c["continue_n"] / c["n"]
                mean_fwd = 100 * c["fwd_ret_sum"] / c["n"]
                print(f"{str_b:<8}{vol_b:<8}{c['n']:>10}{pct_cont:>14.1f}%{mean_fwd:>15.5f}%")


if __name__ == "__main__":
    main()
