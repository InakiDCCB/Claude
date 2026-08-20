"""Research exploratorio: continuación/reversión de 10-min condicionada a contexto (gap, régimen
de tendencia, posición en el rango del día, cercanía a números redondos) + dos controles
deliberadamente ABSURDOS (fase lunar, último dígito del precio) para calibrar qué tan fácil es que
algo "salga significativo" por puro azar con este volumen de datos. QQQ 1-min 2016-2026 + diario.

Lección de la sesión anterior (ver project_macro_cycle_research.md): un efecto significativo en el
pool de 10 años puede estar completamente muerto en los últimos años. Por eso TODA tabla acá se
reporta con dos columnas: historia completa (2016-2026) y SOLO reciente (2023-2026) -- si algo no
sobrevive en la columna reciente, no es un candidato real hoy, sin importar cuán lindo se vea en el
pool completo.

Uso: python context_conditioned_patterns.py [--window 10]
"""
import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path

DATA_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"
DAILY_PATH = Path(__file__).parents[1] / "data" / "qqq_daily_full.json"
RECENT_YEARS = {2023, 2024, 2025, 2026}
SMA_LEN = 20
SYNODIC_MONTH = 29.530588853
REF_NEW_MOON = dt.date(2000, 1, 6)


def load_daily_context():
    """Devuelve dict date_str -> {'gap_bucket', 'trend_bucket'} usando SOLO info hasta AYER
    (sin lookahead: el SMA de tendencia y el close de referencia del gap son de días previos)."""
    bars = json.loads(DAILY_PATH.read_text())
    bars.sort(key=lambda b: b["t"])
    dates = [b["t"][:10] for b in bars]
    closes = [b["c"] for b in bars]
    opens = [b["o"] for b in bars]

    ctx = {}
    for i in range(1, len(dates)):
        prior_close = closes[i - 1]
        gap_pct = (opens[i] - prior_close) / prior_close * 100
        gap_bucket = "gap_up" if gap_pct > 0.3 else ("gap_down" if gap_pct < -0.3 else "flat")

        if i >= SMA_LEN:
            sma = sum(closes[i - SMA_LEN:i]) / SMA_LEN   # SMA de los 20 cierres ANTES de hoy
            trend_bucket = "uptrend" if closes[i - 1] >= sma else "downtrend"
        else:
            trend_bucket = None

        ctx[dates[i]] = {"gap_bucket": gap_bucket, "trend_bucket": trend_bucket}
    return ctx


def moon_bucket(date_str):
    d = dt.date.fromisoformat(date_str)
    days_since = (d - REF_NEW_MOON).days
    phase = (days_since % SYNODIC_MONTH) / SYNODIC_MONTH   # 0=luna nueva, 0.5=luna llena
    if phase < 0.0625 or phase >= 0.9375:
        return "new_moon"
    if 0.4375 <= phase < 0.5625:
        return "full_moon"
    return "other"


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
        windows.append({"o": float(chunk[0]["o"]), "c": float(chunk[-1]["c"]),
                         "h": max(float(b["h"]) for b in chunk),
                         "l": min(float(b["l"]) for b in chunk)})
    return windows


class Bucket:
    def __init__(self):
        self.n = 0
        self.s = 0.0
        self.ss = 0.0

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
        t = mean / se if se > 0 else 0.0
        return {"n": self.n, "mean_bps": mean * 10000, "t": t}


def run(window_min):
    daily_ctx = load_daily_context()

    # dimensiones de contexto -> {bucket_label: {"full": Bucket, "recent": Bucket}}
    dims = ["gap_bucket", "trend_bucket", "range_position", "round_number", "moon_bucket", "digit_control"]
    tables = {d: {} for d in dims}

    for date, year, bars in iter_day_bars():
        ctx = daily_ctx.get(date)
        w = make_windows(bars, window_min)
        if len(w) < 5:
            continue
        mbucket = moon_bucket(date)
        era = "recent" if year in RECENT_YEARS else "full"  # "full" acumula TODO (incluye recent)

        # rango de sesión EXPANDIENDO (solo hasta la barra actual -- CORREGIDO 08-19: la versión
        # original usaba min/max de TODO el día, look-ahead bias real -- un sistema en vivo a las
        # 9:40 no puede saber cuál va a ser el máximo/mínimo de las 15:50).
        running_low = w[0]["l"]
        running_high = w[0]["h"]
        RANGE_WARMUP = 4  # ~40min con ventana=10min -- antes de eso el rango "hasta ahora" es
                          # demasiado angosto para que la posición dentro de él signifique algo

        for i in range(len(w) - 1):
            cur = w[i]
            running_low = min(running_low, cur["l"])
            running_high = max(running_high, cur["h"])
            span = running_high - running_low
            if i < RANGE_WARMUP:
                continue

            cur_ret = cur["c"] - cur["o"]
            if cur_ret == 0:
                continue
            nxt = w[i + 1]
            fwd_ret = nxt["c"] - nxt["o"]
            sign = 1 if cur_ret > 0 else -1
            fwd_signed = fwd_ret * sign / cur["o"]

            # posición en el rango del día HASTA AHORA (sin look-ahead)
            rp = (cur["c"] - running_low) / span if span > 0 else 0.5
            range_bucket = "near_low" if rp < 0.33 else ("near_high" if rp > 0.67 else "mid_range")

            # cercanía a número redondo ($0.50): distancia en centavos al múltiplo de 50c más cercano
            cents = cur["c"] * 100
            dist_to_round50 = abs(cents - round(cents / 50) * 50)
            round_bucket = "near_round" if dist_to_round50 <= 5 else "far_round"

            digit_bucket = f"digit_{int(round(cur['c'] * 100)) % 10}"

            entries = [("range_position", range_bucket), ("round_number", round_bucket),
                       ("moon_bucket", mbucket), ("digit_control", digit_bucket)]
            if ctx:
                entries.append(("gap_bucket", ctx["gap_bucket"]))
                if ctx["trend_bucket"]:
                    entries.append(("trend_bucket", ctx["trend_bucket"]))

            for dim, label in entries:
                slot = tables[dim].setdefault(label, {"full": Bucket(), "recent": Bucket()})
                slot["full"].add(fwd_signed)
                if year in RECENT_YEARS:
                    slot["recent"].add(fwd_signed)

    return tables


def print_table(name, table):
    print(f"\n=== {name} ===")
    print(f"{'bucket':<14}{'n(full)':>10}{'fwd_bps(full)':>15}{'t(full)':>9}"
          f"{'n(23-26)':>10}{'fwd_bps(23-26)':>16}{'t(23-26)':>10}")
    for label in sorted(table):
        full = table[label]["full"].stats()
        recent = table[label]["recent"].stats()
        if not full:
            continue
        rn = recent["n"] if recent else 0
        rb = f"{recent['mean_bps']:>16.3f}" if recent else f"{'--':>16}"
        rt = f"{recent['t']:>10.1f}" if recent else f"{'--':>10}"
        print(f"{label:<14}{full['n']:>10}{full['mean_bps']:>15.3f}{full['t']:>9.1f}"
              f"{rn:>10}{rb}{rt}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=10)
    a = ap.parse_args()

    print(f"Análisis condicionado a contexto, ventana={a.window}min, 2016-2026 (columna 'full') "
          f"vs 2023-2026 (columna 'recent').")
    print("fwd_bps = expectancy de apostar CONTINUACIÓN (mismo signo que la barra actual). "
          "Negativo = reversión paga, positivo = continuación paga.")

    tables = run(a.window)
    print_table("Gap de apertura (vs cierre de ayer)", tables["gap_bucket"])
    print_table("Régimen de tendencia (cierre de ayer vs SMA20 diaria)", tables["trend_bucket"])
    print_table("Posición en el rango del día hasta ahora", tables["range_position"])
    print_table("Cercanía a número redondo ($0.50)", tables["round_number"])
    print_table("CONTROL ABSURDO: fase lunar", tables["moon_bucket"])
    print_table("CONTROL ABSURDO: último dígito del precio (centavos)", tables["digit_control"])


if __name__ == "__main__":
    main()
