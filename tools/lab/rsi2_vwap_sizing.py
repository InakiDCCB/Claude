"""
S1 RSI2 — VWAP-distance tiered sizing backtest.

Pregunta: ¿el gap entre el cierre del bloque 5-min y el VWAP al sello predice
el outcome? ¿Se puede usar para sizing variable sin look-ahead?

Diseño anti-lookahead estricto:
  - VWAP al sello = Day.vwap[seal_bar] (incremental desde 9:30 hasta esa barra
    inclusive, calculado por Day.__init__ — no toca ningún dato futuro del día)
  - gap_norm = (close_5m - vwap) / atr5m  (escala-neutral entre regímenes)
  - Tier asignado SOLO con datos disponibles al sello, antes de la entrada

Tiers de sizing (3 rangos, barridos en PARTE 3):
  A: gap_norm <= -1.0  → 1.5× base  (dip profundo bajo VWAP)
  B: -1.0 < gap_norm <= 0.0 → 1.0× base (dip moderado)
  C: gap_norm > 0.0          → 0.5× base (entrada sobre VWAP)

Walk-forward: TRAIN 2016-2021 / TEST 2022-2026 (OOS).

Uso: uv run python tools/lab/rsi2_vwap_sizing.py
"""
import sys
import math
import csv
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parents[1]))
from backtest import Day, simulate

DATA_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"

ENTRY_MIN  = 30    # bar 30  ~ 10:00 ET
ENTRY_MAX  = 370   # bar 370 ~ 15:40 ET (PASSIVE v3.1.20)
TP_MULT    = 0.5
SL_MULT    = 1.0
THRESH     = 15    # RSI2 < 15
TIME_STOP  = 15    # minutos

# Tier-A boundary (en ATR5m) y tamaños relativos
TIER_BOUNDS = [-1.0, 0.0]   # A: <= -1.0  |  B: (-1,0]  |  C: > 0
TIER_SIZES  = [1.5,  1.0, 0.5]
TIER_NAMES  = ["A deep<VWAP", "B mod<VWAP", "C above VWAP"]


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────────────────────────────────────

def wilson_lb(wins, n, z=1.96):
    if n == 0:
        return None
    p = wins / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (c - m) / d


def load_days(years):
    bydate = {}
    for year in years:
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
    for d in sorted(bydate):
        bars = bydate[d]
        if len(bars) < 300:
            continue
        day = Day(d, bars, prev)
        days.append(day)
        prev = day
    return days


def sim_entry(day, seal_bar, atr5, delay_bars):
    """Entrada con delay_bars barras de retraso desde el sello."""
    entry_bar = seal_bar + delay_bars
    if entry_bar >= day.n - 1:
        return None
    entry = day.o[entry_bar]
    sl = round(entry - SL_MULT * atr5, 2)
    if sl >= entry:
        return None
    tp = ("abs", round(entry + TP_MULT * atr5, 2))
    xi, xp, xt = simulate(day, entry_bar, entry, sl, tp, None, TIME_STOP)
    return {"pnl": xp - entry, "xt": xt, "entry": entry}


def get_tier(gap_norm):
    for i, b in enumerate(TIER_BOUNDS):
        if gap_norm <= b:
            return i
    return len(TIER_BOUNDS)


def pf_of(pnls):
    g = sum(p for p in pnls if p > 0)
    l = abs(sum(p for p in pnls if p <= 0))
    return g / l if l > 0 else float("inf")


def fmt_pf(pf):
    return f"{pf:.3f}" if pf != float("inf") else "  inf"


# ──────────────────────────────────────────────────────────────────────────────
# Generación de señales
# ──────────────────────────────────────────────────────────────────────────────

def collect_signals(days):
    """
    Devuelve cada señal RSI2 con el gap normalizado calculado sin lookahead.
    gap_norm = (close_5m - vwap_al_sello) / atr5m
    """
    signals = []
    for day in days:
        for i in range(day.n - 9):
            if (i + 1) % 5 != 0:
                continue
            k = (i + 1) // 5 - 1
            if k < 14:
                continue
            if day.f_rsi2 is None or day.f_rsi2[k] is None:
                continue
            if day.f_rsi2[k] >= THRESH:
                continue
            if day.f_atr is None or day.f_atr[k] is None:
                continue
            if not (ENTRY_MIN <= (i + 1) <= ENTRY_MAX):
                continue
            atr5 = day.f_atr[k]
            # VWAP incremental hasta la barra i (último bar del bloque 5-min)
            # Day.vwap[i] usa solo barras 0..i — sin lookahead
            vwap_seal = day.vwap[i]
            close_5m  = day.c[i]   # igual que day.f_c[k]
            gap       = close_5m - vwap_seal
            gap_norm  = gap / atr5 if atr5 > 0 else 0.0
            signals.append({
                "day":      day,
                "date":     day.date,
                "seal_bar": i,
                "atr5":     atr5,
                "rsi2":     day.f_rsi2[k],
                "gap":      gap,
                "gap_norm": gap_norm,
                "vwap":     vwap_seal,
            })
    return signals


# ──────────────────────────────────────────────────────────────────────────────
# Análisis
# ──────────────────────────────────────────────────────────────────────────────

def analyze_binary(signals, delay, label):
    """Binario: below VWAP (gap_norm<=0) vs above VWAP."""
    below, above = [], []
    for sig in signals:
        r = sim_entry(sig["day"], sig["seal_bar"], sig["atr5"], delay)
        if r is None:
            continue
        if sig["gap_norm"] <= 0.0:
            below.append(r["pnl"])
        else:
            above.append(r["pnl"])

    total = below + above
    print(f"\n{label}")
    for lbl, pnls in [("below VWAP (gap<=0)", below), ("above VWAP (gap>0)", above),
                      ("TOTAL            ", total)]:
        if not pnls:
            print(f"  {lbl}: n=0")
            continue
        n = len(pnls)
        w = sum(1 for p in pnls if p > 0)
        wlb = wilson_lb(w, n)
        pf  = pf_of(pnls)
        hit = 100 * w / n
        avg = sum(pnls) / n
        print(f"  {lbl}: n={n:>5} hit={hit:5.1f}% wLB={wlb*100:5.1f}% "
              f"pf={fmt_pf(pf):>6} avg/sh={avg:+.4f}")


def analyze_tiered(signals, delay, bounds, sizes, label):
    """3 tiers con sizing relativo — compara flat vs tiered."""
    tier_pnl = {0: [], 1: [], 2: []}

    for sig in signals:
        r = sim_entry(sig["day"], sig["seal_bar"], sig["atr5"], delay)
        if r is None:
            continue
        t = get_tier(sig["gap_norm"])
        tier_pnl[t].append(r["pnl"])

    all_flat    = tier_pnl[0] + tier_pnl[1] + tier_pnl[2]
    all_tiered  = (
        [p * sizes[0] for p in tier_pnl[0]] +
        [p * sizes[1] for p in tier_pnl[1]] +
        [p * sizes[2] for p in tier_pnl[2]]
    )

    print(f"\n{label}")
    for t, name in enumerate(TIER_NAMES):
        pnls = tier_pnl[t]
        if not pnls:
            print(f"  {name}: n=0")
            continue
        n   = len(pnls)
        w   = sum(1 for p in pnls if p > 0)
        wlb = wilson_lb(w, n)
        pf  = pf_of(pnls)
        hit = 100 * w / n
        avg = sum(pnls) / n
        print(f"  {name} ({sizes[t]:.1f}×): n={n:>5} hit={hit:5.1f}% wLB={wlb*100:5.1f}% "
              f"pf={fmt_pf(pf):>6} avg/sh={avg:+.4f} total={sum(pnls):+.3f}")

    if all_flat:
        n  = len(all_flat)
        pf_f = pf_of(all_flat)
        pf_t = pf_of(all_tiered)
        tot_f = sum(all_flat)
        tot_t = sum(all_tiered)
        lift  = (tot_t - tot_f) / abs(tot_f) * 100 if tot_f != 0 else 0
        print(f"\n  FLAT  (1.0× todos): n={n} pf={fmt_pf(pf_f)} total/sh={tot_f:+.3f}")
        print(f"  TIERED({','.join(str(s) for s in sizes)}×): n={n} pf={fmt_pf(pf_t)} total/sh={tot_t:+.3f} lift={lift:+.1f}%")


def year_by_year(signals, delay):
    """Año a año: per-tier stats y flat vs tiered PF."""
    by_year = {}
    for sig in signals:
        r = sim_entry(sig["day"], sig["seal_bar"], sig["atr5"], delay)
        if r is None:
            continue
        year = sig["date"][:4]
        t    = get_tier(sig["gap_norm"])
        sz   = TIER_SIZES[t]
        by_year.setdefault(year, {0: [], 1: [], 2: [], "f": [], "t": []})
        by_year[year][t].append(r["pnl"])
        by_year[year]["f"].append(r["pnl"])
        by_year[year]["t"].append(r["pnl"] * sz)

    header = (f"{'Año':>5} | {'A n':>5} {'A pf':>6} | {'B n':>5} {'B pf':>6} | "
              f"{'C n':>5} {'C pf':>6} | {'Flat':>7} | {'Tiered':>7} | {'Lift':>7}")
    print("\n" + header)
    print("-" * len(header))

    for year in sorted(by_year):
        d = by_year[year]
        parts = []
        for t in range(3):
            pnls = d[t]
            pf   = pf_of(pnls) if pnls else None
            pf_s = fmt_pf(pf) if pf is not None else "   —  "
            parts.append(f"n={len(pnls):>3} {pf_s}")
        pf_f = pf_of(d["f"]) if d["f"] else None
        pf_t = pf_of(d["t"]) if d["t"] else None
        tf   = sum(d["f"]); tt = sum(d["t"])
        lift = (tt - tf) / abs(tf) * 100 if tf != 0 else 0
        flag = lambda v: "▼" if v is not None and v < 1.0 else " "
        print(f"  {year} | {parts[0]} | {parts[1]} | {parts[2]} | "
              f"{fmt_pf(pf_f):>7}{flag(pf_f)} | {fmt_pf(pf_t):>7}{flag(pf_t)} | {lift:>+6.1f}%")


def threshold_sweep(signals, delay):
    """Sweep del límite del Tier A (gap_norm <= X) para encontrar umbral robusto."""
    print("\n" + "=" * 70)
    print("PARTE 3 — Sweep del umbral Tier A (gap_norm <= X → 1.5×)")
    print("  Compara flat_pf vs tiered_pf [1.5×, 1.0×, 0.5×] para cada X")
    print("  El patrón debe ser robusto: tiered_pf > flat_pf en un rango amplio de X")
    print("=" * 70)

    # Pre-computar todos los outcomes
    outcomes = []
    for sig in signals:
        r = sim_entry(sig["day"], sig["seal_bar"], sig["atr5"], delay)
        if r is None:
            continue
        outcomes.append({"pnl": r["pnl"], "gn": sig["gap_norm"]})

    if not outcomes:
        return

    thresholds_a = [-2.5, -2.0, -1.5, -1.0, -0.75, -0.5, -0.25]

    print(f"\n  {'X (tier A)':>12} | {'nA':>5} {'nB':>5} {'nC':>5} | "
          f"{'flat pf':>8} | {'tiered pf':>10} | {'lift':>7}")
    print("  " + "-" * 72)

    for x in thresholds_a:
        na = nb = nc = 0
        flat_pnl = []
        tier_pnl = {0: [], 1: [], 2: []}

        for o in outcomes:
            gn = o["gn"]
            flat_pnl.append(o["pnl"])
            if gn <= x:
                t = 0; na += 1
            elif gn <= 0.0:
                t = 1; nb += 1
            else:
                t = 2; nc += 1
            tier_pnl[t].append(o["pnl"])

        tiered = ([p * 1.5 for p in tier_pnl[0]] +
                  [p * 1.0 for p in tier_pnl[1]] +
                  [p * 0.5 for p in tier_pnl[2]])

        pf_f = pf_of(flat_pnl)
        pf_t = pf_of(tiered)
        tot_f = sum(flat_pnl)
        tot_t = sum(tiered)
        lift  = (tot_t - tot_f) / abs(tot_f) * 100 if tot_f != 0 else 0
        flag  = " ◄ mejor" if pf_t > pf_f and lift > 5 else ""
        print(f"  X={x:>6.2f}       | {na:>5} {nb:>5} {nc:>5} | "
              f"{fmt_pf(pf_f):>8} | {fmt_pf(pf_t):>10} | {lift:>+6.1f}%{flag}")


def gap_distribution(signals):
    """Distribución de gap_norm para entender el universo."""
    gnorms = [s["gap_norm"] for s in signals]
    n = len(gnorms)
    if n == 0:
        return
    bins = [
        ("<= -2.0 (muy profundo)", lambda g: g <= -2.0),
        ("(-2.0, -1.0]", lambda g: -2.0 < g <= -1.0),
        ("(-1.0, -0.5]", lambda g: -1.0 < g <= -0.5),
        ("(-0.5, 0.0]",  lambda g: -0.5 < g <= 0.0),
        ("(0.0, +0.5]",  lambda g: 0.0  < g <= 0.5),
        ("> +0.5 (sobre VWAP)", lambda g: g > 0.5),
    ]
    print("\nDistribución de gap_norm (close_5m - VWAP) / ATR5m:")
    for label, cond in bins:
        cnt = sum(1 for g in gnorms if cond(g))
        bar = "#" * int(cnt / n * 40)
        print(f"  {label:>26}: {cnt:>5} ({100*cnt/n:5.1f}%)  {bar}")
    below = sum(1 for g in gnorms if g <= 0)
    print(f"\n  Total señales: {n} | below VWAP: {below} ({100*below/n:.1f}%) | "
          f"above VWAP: {n-below} ({100*(n-below)/n:.1f}%)")


def main():
    print("Cargando datos 2016-2026...")
    days_all   = load_days(range(2016, 2027))
    days_train = [d for d in days_all if d.date < "2022-01-01"]
    days_test  = [d for d in days_all if d.date >= "2022-01-01"]
    print(f"Total: {len(days_all)} días  |  Train 2016-2021: {len(days_train)}  |  Test 2022-2026: {len(days_test)}")

    sigs_all   = collect_signals(days_all)
    sigs_train = [s for s in sigs_all if s["date"] < "2022-01-01"]
    sigs_test  = [s for s in sigs_all if s["date"] >= "2022-01-01"]
    print(f"Señales: {len(sigs_all)} total | {len(sigs_train)} train | {len(sigs_test)} test")

    gap_distribution(sigs_all)

    # ── PARTE 1: binario below vs above VWAP ─────────────────────────────────
    print("\n" + "=" * 70)
    print("PARTE 1 — Binario below vs above VWAP (delay=2 bars ~120s)")
    print("  Hipótesis H-VWAP: entradas bajo el VWAP tienen mejor outcome")
    print("=" * 70)
    analyze_binary(sigs_all,   delay=2, label="POOL 2016-2026")
    analyze_binary(sigs_train, delay=2, label="TRAIN 2016-2021")
    analyze_binary(sigs_test,  delay=2, label="TEST  2022-2026 (OOS)")

    # ── PARTE 2: tiered sizing 3 tiers ───────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"PARTE 2 — Tiered sizing {TIER_SIZES} × (bounds: {TIER_BOUNDS})")
    print("  Pregunta: ¿sizing proporcional al dip mejora el P&L total?")
    print("=" * 70)
    analyze_tiered(sigs_all, delay=2, bounds=TIER_BOUNDS, sizes=TIER_SIZES,
                   label="POOL 2016-2026")

    print("\nYear-by-year (delay=2, tiers default):")
    year_by_year(sigs_all, delay=2)

    analyze_tiered(sigs_train, delay=2, bounds=TIER_BOUNDS, sizes=TIER_SIZES,
                   label="TRAIN 2016-2021")
    analyze_tiered(sigs_test,  delay=2, bounds=TIER_BOUNDS, sizes=TIER_SIZES,
                   label="TEST  2022-2026 (OOS)")

    # ── PARTE 3: sweep del umbral Tier A ─────────────────────────────────────
    threshold_sweep(sigs_all, delay=2)

    # ── PARTE 4: robustez por delay ───────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PARTE 4 — Robustez del binario por delay (1 / 2 / 3 / 4 bars)")
    print("  Si el patrón desaparece al entrar más tarde → frágil")
    print("=" * 70)
    for delay in [1, 2, 3, 4]:
        print(f"\n  delay={delay} bar (~{delay*60}s):")
        for label, sigs in [("below VWAP (gap_norm<=0)", [s for s in sigs_all if s["gap_norm"] <= 0.0]),
                             ("above VWAP (gap_norm>0)",  [s for s in sigs_all if s["gap_norm"] >  0.0])]:
            pnls = []
            for sig in sigs:
                r = sim_entry(sig["day"], sig["seal_bar"], sig["atr5"], delay)
                if r is not None:
                    pnls.append(r["pnl"])
            if not pnls:
                continue
            n   = len(pnls)
            w   = sum(1 for p in pnls if p > 0)
            wlb = wilson_lb(w, n)
            pf  = pf_of(pnls)
            hit = 100 * w / n
            avg = sum(pnls) / n
            print(f"    {label}: n={n:>5} hit={hit:5.1f}% wLB={wlb*100:5.1f}% "
                  f"pf={fmt_pf(pf):>6} avg/sh={avg:+.5f}")


if __name__ == "__main__":
    main()
