"""Barrido de EMA(5,7,9,15,21,34,55,100) x temporalidad (5,15,30,65min intradía + diario + semanal),
QQQ 2016-2026 (pedido usuario 2026-08-19). Para cada (período, temporalidad): ¿el retorno de la
barra SIGUIENTE es distinto cuando el cierre está arriba vs abajo de la EMA? (test de tendencia:
arriba > abajo = trend-following real; arriba < abajo = mean-reversion; arriba ≈ abajo = la EMA no
aporta nada en esa combinación). full=2016-2026, recent=2023-2026 -- misma disciplina del resto de
la sesión. Intradía: series CONTINUAS a través de días (igual que un gráfico real, la EMA no
resetea overnight -- distinto del resto de scripts de hoy que sí resetean por sesión).

Uso: python ema_sweep_multitimeframe.py
"""
import csv
import datetime as dt
import json
from pathlib import Path

DATA_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"
DAILY_PATH = Path(__file__).parents[1] / "data" / "qqq_daily_full.json"
PERIODS = (5, 7, 9, 15, 21, 34, 55, 100)
RECENT_YEARS = {2023, 2024, 2025, 2026}


def ema_all(closes, periods):
    """Devuelve dict period -> lista de EMA (None hasta que hay suficientes datos)."""
    out = {}
    for n in periods:
        vals = [None] * len(closes)
        if len(closes) >= n:
            s = sum(closes[:n]) / n
            vals[n - 1] = s
            k = 2 / (n + 1)
            for i in range(n, len(closes)):
                s = closes[i] * k + s * (1 - k)
                vals[i] = s
        out[n] = vals
    return out


def load_intraday_closes(window_min):
    """Serie CONTINUA de cierres (agregados en bloques de window_min) a través de TODOS los años,
    sin resetear en límites de día. Devuelve (closes, dates) alineados índice a índice."""
    closes, dates = [], []
    for year in range(2016, 2027):
        path = DATA_DIR / f"{year}.csv"
        if not path.exists():
            continue
        rows = list(csv.DictReader(path.open()))
        for i in range(0, len(rows) - window_min + 1, window_min):
            chunk = rows[i:i + window_min]
            closes.append(float(chunk[-1]["c"]))
            dates.append(chunk[-1]["t"][:10])
    return closes, dates


def load_daily_closes():
    bars = json.loads(DAILY_PATH.read_text())
    bars.sort(key=lambda b: b["t"])
    return [b["c"] for b in bars], [b["t"][:10] for b in bars]


def load_weekly_closes():
    bars = json.loads(DAILY_PATH.read_text())
    bars.sort(key=lambda b: b["t"])
    weeks = {}
    for b in bars:
        d = dt.date.fromisoformat(b["t"][:10])
        wk = d.isocalendar()[:2]   # (año ISO, semana ISO)
        weeks.setdefault(wk, []).append(b)
    closes, dates = [], []
    for wk in sorted(weeks):
        wbars = weeks[wk]
        closes.append(wbars[-1]["c"])
        dates.append(wbars[-1]["t"][:10])
    return closes, dates


class Acc:
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


def analyze(closes, dates, label):
    emas = ema_all(closes, PERIODS)
    results = []
    for period in PERIODS:
        e = emas[period]
        above = {"full": Acc(), "recent": Acc()}
        below = {"full": Acc(), "recent": Acc()}
        for i in range(period, len(closes) - 1):
            if e[i] is None or closes[i] == 0:
                continue
            fwd = (closes[i + 1] - closes[i]) / closes[i]
            year = int(dates[i][:4])
            bucket = above if closes[i] > e[i] else below
            bucket["full"].add(fwd)
            if year in RECENT_YEARS:
                bucket["recent"].add(fwd)
        af, bf = above["full"].stats(), below["full"].stats()
        ar, br = above["recent"].stats(), below["recent"].stats()
        results.append((period, af, bf, ar, br))
    return results


def print_results(label, results):
    print(f"\n=== {label} ===")
    print(f"{'EMA':<5}{'above_bps(f)':>13}{'below_bps(f)':>13}{'spread(f)':>10}"
          f"{'above_bps(r)':>13}{'below_bps(r)':>13}{'spread(r)':>10}")
    for period, af, bf, ar, br in results:
        if not af or not bf:
            print(f"{period:<5}  (datos insuficientes)")
            continue
        spread_f = af["mean_bps"] - bf["mean_bps"]
        spread_r = (ar["mean_bps"] - br["mean_bps"]) if (ar and br) else None
        ar_s = f"{ar['mean_bps']:>13.3f}" if ar else f"{'--':>13}"
        br_s = f"{br['mean_bps']:>13.3f}" if br else f"{'--':>13}"
        sr_s = f"{spread_r:>10.3f}" if spread_r is not None else f"{'--':>10}"
        print(f"{period:<5}{af['mean_bps']:>13.3f}{bf['mean_bps']:>13.3f}{spread_f:>10.3f}"
              f"{ar_s}{br_s}{sr_s}")


def main():
    timeframes = [
        ("5min", lambda: load_intraday_closes(5)),
        ("15min", lambda: load_intraday_closes(15)),
        ("30min", lambda: load_intraday_closes(30)),
        ("65min", lambda: load_intraday_closes(65)),
        ("diario", load_daily_closes),
        ("semanal", load_weekly_closes),
    ]
    all_results = {}
    for label, loader in timeframes:
        print(f"\nCargando temporalidad {label}...")
        closes, dates = loader()
        print(f"  {len(closes)} barras")
        results = analyze(closes, dates, label)
        all_results[label] = results
        print_results(label, results)

    (Path(__file__).parents[1] / "data" / "ema_sweep_results.json").write_text(
        json.dumps({label: [(p, af, bf, ar, br) for p, af, bf, ar, br in res]
                    for label, res in all_results.items()}))


if __name__ == "__main__":
    main()
