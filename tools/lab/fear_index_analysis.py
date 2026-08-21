"""Fear index (VIX) research, pedido explícito del usuario 2026-08-20 ("expandamos esto a un fear
index y al VIX"). Fuente distinta a precio/volumen propio de QQQ -- la que la sesión anterior
recomendó como siguiente paso de mayor valor tras 18 hipótesis agotadas sobre autocorrelación pura.

Datos: VIX/VIX3M/VVIX diarios oficiales de CBOE (`tools/fetch_vix_history.py`, pure-stdlib) vs QQQ
diario ya cacheado (`tools/data/qqq_daily_full.json`). TODO expanding-window hacia atrás (percentiles
y z-scores calculados SOLO con información hasta el día actual, nunca con el dataset completo --
misma lección de feedback_lookahead_bias_research.md), full (2016-2026) vs recent (2023-2026).

Hipótesis probadas:
1. Régimen de nivel de VIX (terciles expanding) -> retorno forward QQQ 1d/5d/20d.
2. Spike de VIX (cambio día a día, decil expanding) -> retorno forward -- ¿pánico = suelo?
3. Term structure VIX/VIX3M (backwardation >1 vs contango <1) -> retorno forward -- indicador
   profesional de stress, poco usado en retail (requiere VIX3M, no solo el VIX spot).
4. VVIX ("vol de la vol") régimen (terciles expanding) -> retorno forward.
5. Z-score de VIX vs su propia media/std expanding -> retorno forward -- ¿reversión del miedo?

Uso: python fear_index_analysis.py
"""
import bisect
import csv
import json
import math
from pathlib import Path

QQQ_PATH = Path(__file__).parents[1] / "data" / "qqq_daily_full.json"
VIX_DIR = Path(__file__).parents[1] / "data" / "vix"
RECENT_YEARS = {2023, 2024, 2025, 2026}
WARMUP = 60  # dias antes de confiar en percentiles/z-score expanding
FWD_HORIZONS = (1, 5, 20)


def load_qqq():
    raw = json.loads(QQQ_PATH.read_text())
    out = {}
    for bar in raw:
        out[bar["t"][:10]] = bar["c"]
    return out


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


def expanding_percentile(sorted_hist, x):
    """Percentil de x dentro de sorted_hist (lista ordenada de valores YA vistos, sin incluir x)."""
    if not sorted_hist:
        return None
    idx = bisect.bisect_left(sorted_hist, x)
    return idx / len(sorted_hist)


def bucket3_from_pct(p):
    if p is None:
        return None
    return "low" if p < 0.333 else ("high" if p > 0.667 else "mid")


def main():
    qqq = load_qqq()
    vix = load_vix_csv("VIX")
    vix3m = load_vix_csv("VIX3M")
    vvix = load_vix_csv("VVIX", value_col="VVIX")

    dates = sorted(d for d in qqq if d in vix)
    print(f"Fechas alineadas QQQ+VIX: {len(dates)} ({dates[0]} -> {dates[-1]})")

    level_tables = {h: {"full": {}, "recent": {}} for h in FWD_HORIZONS}
    spike_tables = {h: {"full": {}, "recent": {}} for h in FWD_HORIZONS}
    term_tables = {h: {"full": {}, "recent": {}} for h in FWD_HORIZONS}
    vvix_tables = {h: {"full": {}, "recent": {}} for h in FWD_HORIZONS}
    z_tables = {h: {"full": {}, "recent": {}} for h in FWD_HORIZONS}

    vix_hist_sorted = []          # niveles VIX vistos hasta ayer (para percentil)
    vix_chg_hist_sorted = []      # cambios %VIX vistos hasta ayer (para percentil de spike)
    vvix_hist_sorted = []
    vix_sum, vix_sumsq, vix_n = 0.0, 0.0, 0  # para z-score expanding
    prev_vix = None

    for i, date in enumerate(dates):
        year = int(date[:4])
        era = "recent" if year in RECENT_YEARS else "full"
        eras = ("full",) if era == "full" else ("full", "recent")
        v = vix[date]

        # --- percentiles/z-score usando SOLO historia previa (expanding, sin look-ahead) ---
        lvl_pct = expanding_percentile(vix_hist_sorted, v) if i >= WARMUP else None
        z = None
        if i >= WARMUP and vix_n > 1:
            mean = vix_sum / vix_n
            var = vix_sumsq / vix_n - mean * mean
            if var > 0:
                z = (v - mean) / (var ** 0.5)
        chg_pct_rank = None
        if prev_vix is not None:
            chg = (v - prev_vix) / prev_vix
            chg_pct_rank = expanding_percentile(vix_chg_hist_sorted, chg) if i >= WARMUP else None
            bisect.insort(vix_chg_hist_sorted, chg)

        term_ratio = None
        if date in vix3m and vix3m[date] > 0:
            term_ratio = v / vix3m[date]

        vv_pct = None
        if date in vvix:
            vv = vvix[date]
            vv_pct = expanding_percentile(vvix_hist_sorted, vv) if i >= WARMUP else None
            bisect.insort(vvix_hist_sorted, vv)

        # --- forward returns QQQ (dias de trading, no calendario) ---
        for h in FWD_HORIZONS:
            if i + h >= len(dates):
                continue
            d0, dh = dates[i], dates[i + h]
            if d0 not in qqq or dh not in qqq:
                continue
            fwd = qqq[dh] / qqq[d0] - 1

            lb = bucket3_from_pct(lvl_pct)
            if lb:
                for e in eras:
                    level_tables[h][e].setdefault(lb, Bucket()).add(fwd)

            if chg_pct_rank is not None and chg_pct_rank > 0.9:
                for e in eras:
                    spike_tables[h][e].setdefault("spike_top10pct", Bucket()).add(fwd)
            elif chg_pct_rank is not None:
                for e in eras:
                    spike_tables[h][e].setdefault("normal", Bucket()).add(fwd)

            if term_ratio is not None:
                tb = "backwardation(>1)" if term_ratio > 1.0 else "contango(<1)"
                for e in eras:
                    term_tables[h][e].setdefault(tb, Bucket()).add(fwd)

            vb = bucket3_from_pct(vv_pct)
            if vb:
                for e in eras:
                    vvix_tables[h][e].setdefault(vb, Bucket()).add(fwd)

            if z is not None:
                zb = "z<-1" if z < -1 else ("z>1" if z > 1 else "z_mid")
                for e in eras:
                    z_tables[h][e].setdefault(zb, Bucket()).add(fwd)

        # --- actualizar historiales DESPUES de usarlos (expanding correcto; vvix/chg ya se
        # insertaron arriba, inmediatamente despues de leer su percentil) ---
        bisect.insort(vix_hist_sorted, v)
        vix_sum += v; vix_sumsq += v * v; vix_n += 1
        prev_vix = v

    def print_table(name, tables):
        print(f"\n=== {name} ===")
        for h in FWD_HORIZONS:
            print(f"-- horizonte {h}d --")
            print(f"{'bucket':<20}{'n(full)':>9}{'ret_bps(full)':>15}{'t(full)':>9}"
                  f"{'n(rec)':>9}{'ret_bps(rec)':>14}{'t(rec)':>8}")
            for label in sorted(tables[h]["full"]):
                f = tables[h]["full"][label].stats()
                r = tables[h]["recent"].get(label)
                rs = r.stats() if r else None
                if not f:
                    continue
                rn = rs["n"] if rs else 0
                rb = f"{rs['mean_bps']:>14.1f}" if rs else f"{'--':>14}"
                rt = f"{rs['t']:>8.1f}" if rs else f"{'--':>8}"
                print(f"{label:<20}{f['n']:>9}{f['mean_bps']:>15.1f}{f['t']:>9.1f}{rn:>9}{rb}{rt}")

    print_table("1. Regimen de nivel de VIX (terciles expanding)", level_tables)
    print_table("2. Spike de VIX (decil top10 de cambio dia-a-dia, expanding)", spike_tables)
    print_table("3. Term structure VIX/VIX3M (backwardation vs contango)", term_tables)
    print_table("4. Regimen VVIX (vol-of-vol, terciles expanding)", vvix_tables)
    print_table("5. Z-score de VIX (expanding mean/std)", z_tables)


if __name__ == "__main__":
    main()
