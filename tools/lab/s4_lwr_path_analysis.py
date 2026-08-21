"""¿Qué hunde a S4 SWP y LWR pese a hit rate positivo, y se puede explotar el camino de precio
entre la entrada y la salida? Pedido explícito del usuario tras ver que ambos tienen hit% alto
(64.9% / 65.4%) pero PF<1 a 10 años.

Para cada trade grabamos el camino COMPLETO en R-múltiplos desde la entrada hasta el cierre forzado
de 15:55 (sin truncar en el SL/TP original) -- así se puede re-escanear el mismo camino con
cualquier combinación de SL/TP (más ajustada O más ancha que la actual) sin volver a simular desde
cero. Con eso:

1. **MFE/MAE** (excursión favorable/adversa máxima) separado por ganadoras vs perdedoras -- ¿las
   perdedoras alguna vez llegan a estar en ganancia? ¿las ganadoras se acercan mucho al SL antes de
   recuperar?
2. **Tiempo hasta el resultado** -- ¿las perdedoras tardan más/menos que las ganadoras?
3. **Camino promedio por barra** (R-múltiplo medio en offsets fijos) separado por resultado final --
   ¿hay una "firma" visible temprano que distinga ganadoras de perdedoras?
4. **Grid de SL/TP alternativos** re-escaneando el MISMO camino grabado -- responde directamente
   "¿un stop más ajustado o un TP distinto mejora el PF real?" sin necesidad de re-simular.

Uso: python s4_lwr_path_analysis.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from backtest import Day, sweep_reclaim, wick_reversal, ENTRY_MIN, ENTRY_MAX, FORCED  # noqa: E402

DATA_1MIN_DIR = Path(__file__).parents[1] / "data" / "qqq_1min"


def load_days(years):
    bydate = {}
    for year in years:
        path = DATA_1MIN_DIR / f"{year}.csv"
        if not path.exists():
            continue
        with path.open() as f:
            for row in csv.DictReader(f):
                date = row["t"][:10]
                bydate.setdefault(date, []).append(
                    {"t": row["t"], "o": float(row["o"]), "h": float(row["h"]),
                     "l": float(row["l"]), "c": float(row["c"]), "v": float(row["v"])})
    dates = sorted(bydate)
    days, prev = [], None
    for d in dates:
        bars = bydate[d]
        if len(bars) < 300:
            continue
        day = Day(d, bars, prev)
        days.append(day)
        prev = day
    return days


def record_path(day, entry_i, entry_px, risk):
    """(offset, o_r, l_r, h_r, c_r) en R-multiplos desde la entrada hasta forced-close (15:55),
    SIN truncar en ningun SL/TP original -- permite re-escanear con cualquier combinacion despues."""
    path = []
    for j in range(entry_i, min(day.n, FORCED + 1)):
        o_r = 0.0 if j == entry_i else (day.o[j] - entry_px) / risk
        l_r = (day.l[j] - entry_px) / risk
        h_r = (day.h[j] - entry_px) / risk
        c_r = (day.c[j] - entry_px) / risk
        path.append((j - entry_i, o_r, l_r, h_r, c_r))
        if j >= FORCED:
            break
    return path


def resolve(path, sl_r, tp_r):
    """Re-escanea un path grabado con SL/TP alternativo (en R). SL antes que TP en la misma barra
    (conservador, igual que simulate() del motor real)."""
    for offset, o_r, l_r, h_r, c_r in path:
        if l_r <= -sl_r:
            exit_r = o_r if o_r <= -sl_r else -sl_r
            return "SL", offset, exit_r
        if h_r >= tp_r:
            exit_r = o_r if o_r >= tp_r else tp_r
            return "TP", offset, exit_r
    last = path[-1]
    return "TIME", last[0], last[4]


def scan_signals(days, signal_fn, c4):
    """Replica el loop de entrada de run_market() pero graba el path completo en vez de resolver
    con simulate()."""
    trades = []
    for day in days:
        pos_until = -1
        consec_sl = 0
        for i in range(day.n - 1):
            e = i + 1
            if not (ENTRY_MIN <= e <= ENTRY_MAX) or e <= pos_until:
                continue
            if c4 and consec_sl >= 2:
                break
            sig = signal_fn(day, i)
            if sig is None:
                continue
            entry = day.o[e]
            if "sl_abs" in sig:
                sl = sig["sl_abs"]
            else:
                continue
            sl = round(sl, 2)
            if sl >= entry:
                continue
            risk = entry - sl
            tp = sig["tp"]
            tp_r = tp[1] if tp[0] == "r" else (tp[1] - entry) / risk
            path = record_path(day, e, entry, risk)
            outcome, offset, exit_r = resolve(path, 1.0, tp_r)
            trades.append({"day": day.date, "entry_i": e, "risk": risk, "tp_r": tp_r,
                           "path": path, "outcome": outcome, "offset": offset, "exit_r": exit_r})
            pos_until = e + offset
            consec_sl = consec_sl + 1 if exit_r <= 0 else 0
    return trades


def mfe_mae(trade):
    mfe = max(h for _, _, _, h, _ in trade["path"][:trade["offset"] + 1])
    mae = min(l for _, _, l, _, _ in trade["path"][:trade["offset"] + 1])
    return mfe, mae


def analyze(name, trades):
    print(f"\n{'#'*70}\n# {name}: {len(trades)} trades\n{'#'*70}")
    winners = [t for t in trades if t["exit_r"] > 0]
    losers = [t for t in trades if t["exit_r"] <= 0]
    print(f"Ganadoras: {len(winners)} ({len(winners)/len(trades)*100:.1f}%)  "
          f"Perdedoras: {len(losers)} ({len(losers)/len(trades)*100:.1f}%)")

    for label, group in (("GANADORAS", winners), ("PERDEDORAS", losers)):
        mfes = [mfe_mae(t)[0] for t in group]
        maes = [mfe_mae(t)[1] for t in group]
        offsets = [t["offset"] for t in group]
        mfes.sort(); maes.sort(); offsets.sort()
        n = len(group)
        print(f"\n  {label} (n={n}):")
        print(f"    MFE (excursion a favor maxima, R): mediana={mfes[n//2]:+.2f}  "
              f"p25={mfes[n//4]:+.2f}  p75={mfes[3*n//4]:+.2f}  "
              f"%que_llego_a_+0.3R={sum(1 for m in mfes if m>=0.3)/n*100:.1f}%")
        print(f"    MAE (excursion en contra maxima, R): mediana={maes[n//2]:+.2f}  "
              f"p25={maes[n//4]:+.2f}  p75={maes[3*n//4]:+.2f}  "
              f"%que_bajo_de_-0.5R={sum(1 for m in maes if m<=-0.5)/n*100:.1f}%")
        print(f"    Barras hasta el resultado: mediana={offsets[n//2]}  p25={offsets[n//4]}  p75={offsets[3*n//4]}")

    # --- camino promedio por barra (close_r) en offsets fijos, separado por resultado ---
    print("\n  Camino promedio (close, R-multiplo) por offset, ganadoras vs perdedoras:")
    OFFSETS = (1, 2, 3, 5, 8, 12, 20, 30)
    print(f"    {'offset':<8}{'winners_mean':>14}{'losers_mean':>14}{'winners_n':>11}{'losers_n':>11}")
    for off in OFFSETS:
        wv = [t["path"][off][4] for t in winners if off < len(t["path"])]
        lv = [t["path"][off][4] for t in losers if off < len(t["path"])]
        wm = f"{sum(wv)/len(wv):+.3f}" if wv else "n/a"
        lm = f"{sum(lv)/len(lv):+.3f}" if lv else "n/a"
        print(f"    {off:<8}{wm:>14}{lm:>14}{len(wv):>11}{len(lv):>11}")

    # --- grid SL/TP alternativo, re-escaneando el mismo path grabado ---
    print("\n  Grid SL x TP alternativo (re-escaneado sobre el mismo camino real, sin re-simular):")
    sl_grid = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2)
    tp_grid = (0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0)
    print(f"    {'SL\\TP':<8}" + "".join(f"{tp:>7.1f}" for tp in tp_grid))
    best = None
    for sl_r in sl_grid:
        row = []
        for tp_r in tp_grid:
            rets = []
            for t in trades:
                _, _, exit_r = resolve(t["path"], sl_r, tp_r)
                rets.append(exit_r)
            gw = sum(r for r in rets if r > 0)
            gl = -sum(r for r in rets if r <= 0)
            pf = gw / gl if gl > 0 else float("inf")
            row.append(pf)
            if best is None or pf > best[0]:
                best = (pf, sl_r, tp_r, sum(rets))
        print(f"    {sl_r:<8.1f}" + "".join(f"{pf:>7.2f}" if pf != float('inf') else f"{'inf':>7}" for pf in row))
    print(f"\n  MEJOR combo del grid: SL={best[1]}R TP={best[2]}R -> PF={best[0]:.2f} "
          f"(pnl_total={best[3]:+.1f}R, vs actual SL=1.0R TP={trades[0]['tp_r']}R)")
    # actual (config real) para referencia directa
    rets_actual = [t["exit_r"] for t in trades]
    gw = sum(r for r in rets_actual if r > 0); gl = -sum(r for r in rets_actual if r <= 0)
    pf_actual = gw / gl if gl > 0 else float("inf")
    print(f"  ACTUAL (SL=1.0R TP={trades[0]['tp_r']}R): PF={pf_actual:.2f} pnl_total={sum(rets_actual):+.1f}R")


def main():
    print("Cargando 10 años de 1-min...")
    days = load_days(range(2016, 2027))
    print(f"{len(days)} días cargados.")

    print("\nEscaneando S4 SWP (sweep_reclaim 0.5R, C4 on -- mismo config ya reportado)...")
    s4_trades = scan_signals(days, sweep_reclaim(("r", 0.5))(), c4=True)
    analyze("S4 SWP", s4_trades)

    print("\nEscaneando LWR (wick_reversal wt=0.60 rvol>=3.0 tp=0.5R, C4 off -- mismo config ya reportado)...")
    lwr_trades = scan_signals(days, wick_reversal(("r", 0.5), wick_thresh=0.60, min_rvol=3.0)(), c4=False)
    analyze("LWR", lwr_trades)


if __name__ == "__main__":
    main()
