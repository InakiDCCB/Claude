"""
tod_regime_lab.py — TOD × Régimen matrix para S1 RSI2 y S4 SWP.

Pregunta: ¿en qué combinación (time-of-day × régimen diario) tiene edge
positivo cada sistema? ¿Hay celdas que deberíamos bloquear como gates nuevos?

Dimensiones:
  TOD (5 buckets de k):
    early     k=14-20  (~10:45-11:10 ET)
    morning   k=21-28  (~11:15-11:55 ET, pre-H1 gate)
    midday    k=29-41  (~12:00-13:00 ET, zona H1 gate)
    afternoon k=42-59  (~13:05-14:30 ET)
    late      k=60-73  (~14:35-15:40 ET)

  Régimen (3 variables binarias → máx 6 combos significativas):
    gap_dir   up (>+0.3%) / flat (−0.3%..+0.3%) / down (<−0.3%)
    rsi2_on   True si open_9:30 >= y_val (mismo gate que el sistema live)

Output: por sistema, tabla 2D — filas=TOD, columnas=régimen.
         cada celda: n / hit% / PF / wLB (Wilson lower bound)
         celdas con n<10 marcadas con *.

Uso: uv run python tools/lab/tod_regime_lab.py [--system rsi2|swp|both]
"""

import sys
import csv
import math
import argparse
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parents[1]))
from backtest import Day, simulate

# ── constantes ────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"
YEARS = list(range(2016, 2027))

# S1 RSI2
RSI2_THRESH  = 15
RSI2_ATR_WARMUP = 14   # bloques 5-min mínimos para ATR (k>=14)
RSI2_TP_MULT = 0.5
RSI2_SL_MULT = 1.0
RSI2_TIMESTOP = 15     # minutos

# S4 SWP
SWP_TP_MULT  = 0.5     # tp = fill + 0.5*(fill-sl)
SWP_VOL_MULT = 1.5     # reclaim vol >= 1.5x avg5

# TOD buckets (índice del bloque 5-min k, donde k=0 es primer bloque de 9:30)
TOD_BUCKETS = [
    ("early",     14, 20),
    ("morning",   21, 28),
    ("midday",    29, 41),
    ("afternoon", 42, 59),
    ("late",      60, 73),
]

# Régimen: gap_dir × rsi2_on
GAP_UP_THRESH   =  0.3   # %
GAP_DOWN_THRESH = -0.3   # %


# ── helpers ───────────────────────────────────────────────────────────────────
def wilson_lb(wins, n, z=1.96):
    if n == 0:
        return None
    p = wins / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - m) / d


def pf_from_pnls(pnls):
    gain = sum(p for p in pnls if p > 0)
    loss = abs(sum(p for p in pnls if p <= 0))
    return gain / loss if loss > 0 else (float("inf") if gain > 0 else 0.0)


def tod_bucket(k):
    for name, lo, hi in TOD_BUCKETS:
        if lo <= k <= hi:
            return name
    return None


def gap_dir(day):
    if day.pdc is None:
        return None
    gp = (day.o[0] - day.pdc) / day.pdc * 100
    if gp > GAP_UP_THRESH:
        return "gap_up"
    if gp < GAP_DOWN_THRESH:
        return "gap_dn"
    return "flat"


def rsi2_on(day):
    if day.y_val is None:
        return None
    return day.o[0] >= day.y_val


# ── carga de datos ─────────────────────────────────────────────────────────────
def load_days():
    bydate = {}
    for year in YEARS:
        path = DATA_DIR / f"{year}.csv"
        if not path.exists():
            continue
        with path.open() as f:
            for row in csv.DictReader(f):
                date = row["t"][:10]
                bydate.setdefault(date, []).append({
                    "t": row["t"], "o": float(row["o"]), "h": float(row["h"]),
                    "l": float(row["l"]), "c": float(row["c"]), "v": float(row["v"]),
                })
    days, prev = [], None
    for date in sorted(bydate):
        bars = bydate[date]
        if len(bars) < 300:
            continue
        day = Day(date, bars, prev)
        days.append(day)
        prev = day
    return days


# ── S1 RSI2 señales ────────────────────────────────────────────────────────────
def rsi2_signals(days):
    """Devuelve lista de dicts con metadatos de cada señal RSI2."""
    records = []
    for day in days:
        gd = gap_dir(day)
        r2on = rsi2_on(day)
        if gd is None or r2on is None:
            continue
        for i in range(day.n - 9):
            if (i + 1) % 5 != 0:
                continue
            k = (i + 1) // 5 - 1
            if k < RSI2_ATR_WARMUP:
                continue
            if day.f_rsi2 is None or day.f_rsi2[k] is None:
                continue
            if day.f_rsi2[k] >= RSI2_THRESH:
                continue
            if day.f_atr is None or day.f_atr[k] is None:
                continue
            # slot: máx 1 señal en vuelo — skip si ya hay una abierta
            # (simplificación: mismo criterio que el backtest original)
            tod = tod_bucket(k)
            if tod is None:
                continue

            # simular entrada en la siguiente barra (delay=1, baseline)
            entry_bar = i + 1
            if entry_bar >= day.n - 1:
                continue
            entry = day.o[entry_bar]
            atr5  = day.f_atr[k]
            sl    = round(entry - RSI2_SL_MULT * atr5, 2)
            if sl >= entry:
                continue
            tp_spec = ("abs", round(entry + RSI2_TP_MULT * atr5, 2))
            _, xp, xt = simulate(day, entry_bar, entry, sl, tp_spec, None, RSI2_TIMESTOP)
            pnl = xp - entry

            records.append({
                "tod": tod, "k": k,
                "gap_dir": gd, "rsi2_on": r2on,
                "pnl": pnl, "xt": xt,
                "date": day.date,
            })
    return records


# ── S4 SWP señales ─────────────────────────────────────────────────────────────
def swp_signals(days):
    """Sweep session-low + reclaim con volumen. Sin gate diario."""
    records = []
    for day in days:
        gd  = gap_dir(day)
        r2on = rsi2_on(day)
        if gd is None or r2on is None:
            continue
        session_low = day.l[0]
        slot_open   = False   # máx 1 señal SWP por día
        for i in range(1, day.n - 2):
            session_low = min(session_low, day.l[i - 1])
            # ¿nueva sesión low?
            if day.l[i] >= session_low:
                continue
            sweep_low = day.l[i]
            # buscar reclaim en ≤3 barras
            for j in range(i + 1, min(i + 4, day.n - 1)):
                if day.c[j] <= sweep_low:
                    continue
                if day.v[j - 4] is None:
                    continue
                avgv5 = day.avgv5[j] if day.avgv5[j] else None
                if avgv5 is None or day.v[j] < SWP_VOL_MULT * avgv5:
                    continue
                # señal válida
                k = j // 5
                tod = tod_bucket(k)
                if tod is None:
                    break
                if slot_open:
                    break
                slot_open = True

                entry = day.c[j]
                sl    = round(sweep_low - 0.05, 2)
                if sl >= entry:
                    break
                tp_spec = ("abs", round(entry + SWP_TP_MULT * (entry - sl), 2))
                _, xp, xt = simulate(day, j + 1, entry, sl, tp_spec, None, None)
                pnl = xp - entry

                records.append({
                    "tod": tod, "k": k,
                    "gap_dir": gd, "rsi2_on": r2on,
                    "pnl": pnl, "xt": xt,
                    "date": day.date,
                })
                break
    return records


# ── formato de tabla ───────────────────────────────────────────────────────────
def cell_str(pnls, min_n=5):
    n = len(pnls)
    if n == 0:
        return "  —  "
    wins = sum(1 for p in pnls if p > 0)
    pf   = pf_from_pnls(pnls)
    hit  = 100 * wins / n
    wlb  = wilson_lb(wins, n)
    flag = "*" if n < min_n else " "
    pf_s = f"{pf:.2f}" if pf != float("inf") else " inf"
    wlb_s = f"{wlb*100:.0f}%" if wlb else " ?"
    return f"n={n:>3}{flag} h={hit:>4.0f}% PF={pf_s} wLB={wlb_s}"


def print_matrix(title, records, regime_keys):
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")

    # agrupar
    cells = defaultdict(list)
    for r in records:
        rk = tuple(r[k] for k in regime_keys)
        cells[(r["tod"], rk)].append(r["pnl"])

    regime_vals = sorted(set(tuple(r[k] for k in regime_keys) for r in records))
    tod_names   = [b[0] for b in TOD_BUCKETS]

    # header
    hdr = f"{'TOD':<12}" + "".join(f"  {'/'.join(str(v) for v in rv):<36}" for rv in regime_vals)
    print(hdr)
    print("-" * len(hdr))

    totals = defaultdict(list)
    for tod in tod_names:
        row = f"{tod:<12}"
        for rv in regime_vals:
            pnls = cells[(tod, rv)]
            row += f"  {cell_str(pnls):<36}"
            totals[rv].extend(pnls)
        print(row)

    # totales por columna
    print("-" * len(hdr))
    row = f"{'TOTAL':<12}"
    for rv in regime_vals:
        row += f"  {cell_str(totals[rv]):<36}"
    print(row)

    # resumen global
    all_pnls = [r["pnl"] for r in records]
    n = len(all_pnls)
    if n:
        wins = sum(1 for p in all_pnls if p > 0)
        print(f"\n  Global: n={n} hit={100*wins/n:.1f}% PF={pf_from_pnls(all_pnls):.3f} "
              f"pnl/sh={sum(all_pnls)/n:+.4f}")


def print_tod_only(title, records):
    """Sección adicional: solo TOD, agrupando todos los regímenes."""
    print(f"\n  -- {title}: solo TOD (todos los regímenes) --")
    cells = defaultdict(list)
    for r in records:
        cells[r["tod"]].append(r["pnl"])
    for tod, _, _ in TOD_BUCKETS:
        pnls = cells[tod]
        flag = "  << H1 gate" if tod in ("early", "morning") else ""
        print(f"    {tod:<12}  {cell_str(pnls)}{flag}")


# ── main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["rsi2", "swp", "both"], default="both")
    ap.add_argument("--years", type=str, default="2016-2026",
                    help="rango de años, ej. 2016-2026 o 2021-2026")
    args = ap.parse_args()

    # parsear rango de años
    if "-" in args.years:
        y0, y1 = map(int, args.years.split("-"))
        global YEARS
        YEARS[:] = list(range(y0, y1 + 1))

    print(f"Cargando datos {YEARS[0]}–{YEARS[-1]}…", end=" ", flush=True)
    days = load_days()
    print(f"{len(days)} días hábiles")

    if args.system in ("rsi2", "both"):
        recs = rsi2_signals(days)
        print_matrix(
            "S1 RSI2 — TOD × (gap_dir / rsi2_on)",
            recs,
            regime_keys=["gap_dir", "rsi2_on"],
        )
        print_tod_only("S1 RSI2", recs)

        # desglose solo para días rsi2_on=True (los únicos donde opera el sistema)
        recs_on = [r for r in recs if r["rsi2_on"]]
        print_matrix(
            "S1 RSI2 — solo días rsi2_on=True — TOD × gap_dir",
            recs_on,
            regime_keys=["gap_dir"],
        )

    if args.system in ("rsi2", "both"):
        gate_impact_analysis(recs_on, days)

    if args.system in ("swp", "both"):
        recs = swp_signals(days)
        print_matrix(
            "S4 SWP — TOD × (gap_dir / rsi2_on)",
            recs,
            regime_keys=["gap_dir", "rsi2_on"],
        )
        print_tod_only("S4 SWP", recs)


def gate_impact_analysis(recs_on, days):
    """
    Compara tres universos de señales RSI2 (solo días rsi2_on=True):
      BASE  : todos (sin gates de tiempo)
      H1    : k >= 29  (gate actual v3.1.23)
      H1+H2 : k >= 29 AND NOT (gap_dn AND midday)   (hipótesis nueva)

    Para cada universo: global PF/hit/pnl + año por año.
    Al final: tabla de señales eliminadas por H2 con su impacto aislado.
    """
    base   = recs_on
    h1     = [r for r in recs_on if r["tod"] not in ("early", "morning")]
    h1h2   = [r for r in h1      if not (r["gap_dir"] == "gap_dn" and r["tod"] == "midday")]
    elim   = [r for r in h1      if      r["gap_dir"] == "gap_dn" and r["tod"] == "midday"]

    def summary(label, recs, n_days):
        n     = len(recs)
        wins  = sum(1 for r in recs if r["pnl"] > 0)
        pnls  = [r["pnl"] for r in recs]
        pf    = pf_from_pnls(pnls)
        hit   = 100 * wins / n if n else 0
        wlb   = wilson_lb(wins, n)
        pnl_d = sum(pnls) / n_days if n_days else 0
        sig_d = n / n_days if n_days else 0
        return (f"  {label:<10} n={n:>5}  hit={hit:>5.1f}%  PF={pf:.3f}  "
                f"wLB={wlb*100:.1f}%  pnl/sh={sum(pnls)/n:+.4f}  "
                f"sig/dia={sig_d:.2f}  pnl/dia={pnl_d:+.4f}")

    # n_days donde rsi2_on=True
    on_days = len({r["date"] for r in recs_on})

    print(f"\n{'='*72}")
    print(f"  H2 GATE IMPACT — RSI2 en días rsi2_on=True ({on_days} sesiones)")
    print(f"{'='*72}")
    print(summary("BASE",  base,  on_days))
    print(summary("H1",    h1,    on_days))
    print(summary("H1+H2", h1h2,  on_days))
    print(f"\n  Señales eliminadas por H2:")
    print(summary("  elim", elim, on_days))

    # año por año
    print(f"\n  Año por año (H1 vs H1+H2, rsi2_on=True):")
    print(f"  {'Year':<6}  {'H1 n':>5}  {'H1 PF':>6}  {'H1+H2 n':>8}  {'H1+H2 PF':>9}  {'delta PF':>9}  {'elim n':>7}")
    print(f"  {'-'*65}")
    years_seen = sorted({r["date"][:4] for r in h1})
    for yr in years_seen:
        h1_y   = [r for r in h1   if r["date"][:4] == yr]
        h2_y   = [r for r in h1h2 if r["date"][:4] == yr]
        el_y   = [r for r in elim if r["date"][:4] == yr]
        pf1    = pf_from_pnls([r["pnl"] for r in h1_y])
        pf2    = pf_from_pnls([r["pnl"] for r in h2_y])
        delta  = pf2 - pf1
        sign   = "+" if delta >= 0 else ""
        mark   = " OK" if delta > 0 else (" !!" if delta < -0.02 else "  ")
        print(f"  {yr:<6}  {len(h1_y):>5}  {pf1:>6.3f}  {len(h2_y):>8}  {pf2:>9.3f}  "
              f"{sign}{delta:>8.3f}{mark}  {len(el_y):>7}")

    # robustez: ¿en cuántos años mejora H2?
    improve = sum(
        1 for yr in years_seen
        if pf_from_pnls([r["pnl"] for r in h1h2 if r["date"][:4] == yr]) >
           pf_from_pnls([r["pnl"] for r in h1   if r["date"][:4] == yr])
    )
    print(f"\n  H2 mejora en {improve}/{len(years_seen)} años")
    print(f"  Señales eliminadas: {len(elim)} de {len(h1)} ({100*len(elim)/len(h1):.1f}% del universo H1)")


if __name__ == "__main__":
    main()
