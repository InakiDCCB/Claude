"""
Sweep del umbral de abort de latencia para S1 RSI2.

Pregunta: ¿en qué punto (segundos desde el sello 5-min) el PF de RSI2 colapsa?
La spec actual aborta en >150s. ¿Es ese el cliff real o se puede relajar?

Modelo:
  - Señal en bar i (cierre del bloque 5-min sellado, igual que en vivo)
  - Agente llega con latencia L segundos → entra en bar i + ceil(L/60)
  - SL/TP se recalculan desde el precio de entrada real (igual que en vivo)
  - abort_threshold: si L > threshold, NO se entra (señal descartada)

Para cada threshold en [0,30,60,90,120,150,180,210,240,300]s se reporta:
  - n de señales que pasan el threshold
  - subset que se ejecuta (lat <= threshold, entra en bar correspondiente)
  - PF, hit%, pnl/sh del subset

Adicionalmente, barrido por delay fijo (1..5 bars) sin abort para ver la curva de degradación.

Uso: uv run python tools/lab/rsi2_abort_sweep.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from backtest import Day, stats, simulate
import csv, math

DATA_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"
ENTRY_MIN = 30   # bar 30 ~ 10:00 ET (alineado al backtest original)
ENTRY_MAX = 370  # bar 370 ~ 15:40 ET (PASSIVE v3.1.20)

TP_MULT  = 0.5   # spec: tp = entry + 0.5×atr5m
SL_MULT  = 1.0   # spec: sl = entry − 1.0×atr5m
THRESH   = 15    # RSI2 < 15
TIME_STOP = 15   # minutos (15 barras 1-min)


def wilson_lb(wins, n, z=1.96):
    if n == 0:
        return None
    p = wins / n
    d = 1 + z*z/n
    c = p + z*z/(2*n)
    m = z*((p*(1-p)/n + z*z/(4*n*n))**0.5)
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
                bydate.setdefault(date, []).append(
                    {"t": row["t"], "o": float(row["o"]), "h": float(row["h"]),
                     "l": float(row["l"]), "c": float(row["c"]), "v": float(row["v"])})
    dates = sorted(bydate)
    days = []
    prev = None
    for d in dates:
        bars = bydate[d]
        if len(bars) < 300:
            continue
        day = Day(d, bars, prev)
        days.append(day)
        prev = day
    return days


def collect_signals(days):
    """Devuelve todos los momentos donde RSI2 < THRESH al sellar un bloque 5-min."""
    signals = []
    for day in days:
        for i in range(day.n - 9):  # PARTE 4 usa delay hasta 8 barras → seal_bar+8 < day.n-1
            if (i + 1) % 5 != 0:
                continue
            k = (i + 1) // 5 - 1
            if k < 14:  # ATR necesita 15 bloques (≈10:45)
                continue
            if day.f_rsi2 is None or day.f_rsi2[k] is None:
                continue
            if day.f_rsi2[k] >= THRESH:
                continue
            if day.f_atr is None or day.f_atr[k] is None:
                continue
            bar_et = ENTRY_MIN <= (i + 1) <= ENTRY_MAX
            if not bar_et:
                continue
            signals.append({
                "day": day,
                "seal_bar": i,       # índice del último bar del bloque
                "atr5": day.f_atr[k],
                "rsi2": day.f_rsi2[k],
            })
    return signals


def simulate_entry_at_delay(day, seal_bar, atr5, delay_bars):
    """
    Simula una entrada con delay_bars barras de retraso respecto al sello.
    delay_bars=1 → entra en el primer bar tras el sello (comportamiento base del motor).
    Devuelve (pnl, exit_type) o None si no hay barra disponible o sl>=entry.
    """
    entry_bar = seal_bar + delay_bars
    if entry_bar >= day.n - 1:
        return None
    entry = day.o[entry_bar]
    sl = round(entry - SL_MULT * atr5, 2)
    if sl >= entry:
        return None
    tp = ("abs", round(entry + TP_MULT * atr5, 2))
    xi, xp, xt = simulate(day, entry_bar, entry, sl, tp, None, TIME_STOP)
    pnl = xp - entry
    return {"pnl": pnl, "xt": xt, "entry": entry, "sl": sl, "tp": tp[1]}


def fmt(label, trades_pnl):
    n = len(trades_pnl)
    if n == 0:
        return f"{label:>12}: n=0"
    wins = sum(1 for p in trades_pnl if p > 0)
    total_gain = sum(p for p in trades_pnl if p > 0)
    total_loss = abs(sum(p for p in trades_pnl if p <= 0))
    pf = total_gain / total_loss if total_loss > 0 else float("inf")
    hit = 100 * wins / n
    wlb = wilson_lb(wins, n)
    pnl_sh = sum(trades_pnl) / n
    return (f"{label:>12}: n={n:>4} hit={hit:5.1f}% wLB={wlb*100:5.1f}% "
            f"pf={pf:5.2f} pnl/sh={pnl_sh:+.4f}")


def h1_time_filter_analysis(signals):
    """
    H1: ¿Un filtro horario mejora S1 RSI2 de forma robusta?
    Compara full universe (10:00-15:40) vs restricted (12:00-15:40).
    delay=1 bar en ambos (baseline).
    Reporta: PF global, year-by-year, y el costo de excluir la manana.
    """
    print("\n" + "=" * 70)
    print("H1 — Filtro horario: ¿excluir 10:00-12:00 mejora S1 RSI2?")
    print("  FULL:   10:00-15:40 (bars 30-370)")
    print("  FILTER: 12:00-15:40 (bars 149-370)")
    print("=" * 70)

    # Bar 0=9:30 ET; bloque 145-149 sella en bar 149 → primer sello ≥12:00 ET.
    BAR_12 = 149  # índice i del primer sello 5-min en 12:00 ET (bars 145-149)

    full_by_year, filt_by_year = {}, {}
    full_all, filt_all = [], []

    for sig in signals:
        year = sig["day"].date[:4]
        r = simulate_entry_at_delay(sig["day"], sig["seal_bar"], sig["atr5"], 1)
        if r is None:
            continue
        pnl = r["pnl"]
        full_by_year.setdefault(year, []).append(pnl)
        full_all.append(pnl)
        if sig["seal_bar"] >= BAR_12:
            filt_by_year.setdefault(year, []).append(pnl)
            filt_all.append(pnl)

    def pf(pnls):
        g = sum(p for p in pnls if p > 0)
        l = abs(sum(p for p in pnls if p <= 0))
        return g / l if l > 0 else float("inf")

    def hit(pnls):
        return 100 * sum(1 for p in pnls if p > 0) / len(pnls) if pnls else 0

    print(f"\n{'Año':>5} | {'FULL n':>7} {'PF':>6} {'Hit%':>6} | {'>=12h n':>8} {'PF':>6} {'Hit%':>6} | delta-PF")
    print("-" * 72)
    years = sorted(set(full_by_year) | set(filt_by_year))
    for y in years:
        f = full_by_year.get(y, [])
        r = filt_by_year.get(y, [])
        pf_f = pf(f)
        pf_r = pf(r) if r else 0
        print(f"  {y} | {len(f):>7} {pf_f:>6.3f} {hit(f):>5.1f}% | {len(r):>8} {pf_r:>6.3f} {hit(r):>5.1f}% | {pf_r - pf_f:>+.3f}")

    print("-" * 72)
    pf_full = pf(full_all)
    pf_filt = pf(filt_all)
    morning_n = len(full_all) - len(filt_all)
    print(f"TOTAL | {len(full_all):>7} {pf_full:>6.3f} {hit(full_all):>5.1f}% | {len(filt_all):>8} {pf_filt:>6.3f} {hit(filt_all):>5.1f}% | {pf_filt - pf_full:>+.3f}")
    print(f"\nCosto de excluir 10:00-12:00: {morning_n} senales descartadas ({100*morning_n/len(full_all):.1f}% del total)")
    print(f"Ganancia de PF: {pf_full:.3f} -> {pf_filt:.3f} ({pf_filt - pf_full:+.3f})")
    wlb_full = wilson_lb(sum(1 for p in full_all if p > 0), len(full_all))
    wlb_filt = wilson_lb(sum(1 for p in filt_all if p > 0), len(filt_all))
    print(f"Wilson LB hit: {wlb_full*100:.1f}% (full) vs {wlb_filt*100:.1f}% (>=12h)")

    # Fraction of years where filter improves PF
    better = sum(1 for y in years if pf(filt_by_year.get(y,[])) > pf(full_by_year.get(y,[])))
    print(f"Filtro mejora PF en {better}/{len(years)} anos")


def main():
    print("Cargando datos 2016-2026...")
    days = load_days(range(2016, 2027))
    print(f"{len(days)} dias cargados.")

    print("\nExtrayendo senales RSI2 (RSI2<15, ATR valido, 10:00-15:40)...")
    signals = collect_signals(days)
    print(f"{len(signals)} senales encontradas.\n")

    # ── PARTE 1: degradación por delay fijo (1..6 bars) ──────────────────────
    print("=" * 70)
    print("PARTE 1 — Degradacion por delay fijo (misma senal, entrada tardia)")
    print("  delay=1 bar (~60s) = comportamiento base del motor")
    print("  delay=2 (~120s), 3 (~180s), 4 (~240s), 5 (~300s)")
    print("=" * 70)

    for delay in range(1, 7):
        results = []
        for sig in signals:
            r = simulate_entry_at_delay(sig["day"], sig["seal_bar"], sig["atr5"], delay)
            if r is not None:
                results.append(r["pnl"])
        lat_approx = delay * 60
        print(fmt(f"delay={delay}b(~{lat_approx}s)", results))

    # ── PARTE 2: efecto del threshold de abort ───────────────────────────────
    print("\n" + "=" * 70)
    print("PARTE 2 — Efecto del umbral de abort")
    print("  Modelo: entra todas las senales al peor delay posible para ese threshold")
    print("  delay_bars = ceil(thr/60); thresholds con igual delay se omiten (filas duplicadas)")
    print("=" * 70)

    thresholds = [60, 90, 120, 150, 180, 210, 240, 300]
    seen_delays = {}
    for thr in thresholds:
        delay = max(1, math.ceil(thr / 60))
        if delay in seen_delays:
            print(f"  abort<={thr:>3}s: (mismo delay={delay}b que abort<={seen_delays[delay]}s — omitido)")
            continue
        seen_delays[delay] = thr
        passed = []
        for sig in signals:
            r = simulate_entry_at_delay(sig["day"], sig["seal_bar"], sig["atr5"], delay)
            if r is not None:
                passed.append(r["pnl"])
        print(fmt(f"abort<={thr}s(d={delay}b)", passed))

    # ── PARTE 3: bucket horario ───────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PARTE 3 — PF por franja horaria (delay=1, baseline)")
    print("  Franjas: 10:00-12:00 / 12:00-14:00 / 14:00-15:40")
    print("=" * 70)

    bands = {
        "10:00-12:00": (30, 119),
        "12:00-14:00": (120, 239),
        "14:00-15:40": (240, 370),
    }
    for name, (lo, hi) in bands.items():
        results = []
        for sig in signals:
            if not (lo <= sig["seal_bar"] <= hi):
                continue
            r = simulate_entry_at_delay(sig["day"], sig["seal_bar"], sig["atr5"], 1)
            if r is not None:
                results.append(r["pnl"])
        print(fmt(name, results))

    # ── PARTE 4: cliff exacto ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PARTE 4 — Curva de degradacion fina (delay 1..8 bars, ~60-480s)")
    print("  Muestra donde cae el PF por debajo de 1.0")
    print("=" * 70)

    for delay in range(1, 9):
        results = []
        for sig in signals:
            r = simulate_entry_at_delay(sig["day"], sig["seal_bar"], sig["atr5"], delay)
            if r is not None:
                results.append(r["pnl"])
        n = len(results)
        if n == 0:
            continue
        wins = sum(1 for p in results if p > 0)
        gain = sum(p for p in results if p > 0)
        loss = abs(sum(p for p in results if p <= 0))
        pf = gain / loss if loss > 0 else float("inf")
        flag = " << CLIFF (PF<1)" if pf < 1.0 else (" << CAUTION (PF<1.1)" if pf < 1.1 else "")
        print(f"  delay={delay} bar (~{delay*60:>3}s): n={n} pf={pf:.3f} hit={100*wins/n:.1f}%{flag}")

    # ── H1: análisis de filtro horario ────────────────────────────────────────
    h1_time_filter_analysis(signals)


if __name__ == "__main__":
    main()
