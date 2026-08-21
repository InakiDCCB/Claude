"""Seguimiento de s4_lwr_path_analysis.py: el mejor combo del grid (SL=0.3R TP=1.0R) cayó en la
ESQUINA de lo probado (SL más chico y TP más grande de la grilla) -- hay que extender el grid para
ver si el óptimo real está más allá (y si se vuelve poco realista, ej. SL tan ajustado que el
slippage lo destruiría) + año-por-año para confirmar que la mejora no la arrastran 1-2 años.

Uso: python s4_lwr_path_analysis_v2.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from backtest import sweep_reclaim, wick_reversal  # noqa: E402
from s4_lwr_path_analysis import load_days, scan_signals, resolve  # noqa: E402


def pf_of(rets):
    gw = sum(r for r in rets if r > 0)
    gl = -sum(r for r in rets if r <= 0)
    return gw / gl if gl > 0 else float("inf")


def widened_grid(name, trades):
    print(f"\n=== {name}: grid extendido ===")
    sl_grid = (0.15, 0.2, 0.25, 0.3, 0.4, 0.5)
    tp_grid = (0.8, 1.0, 1.2, 1.5, 2.0)
    print(f"    {'SL\\TP':<8}" + "".join(f"{tp:>7.1f}" for tp in tp_grid))
    best = None
    for sl_r in sl_grid:
        row = []
        for tp_r in tp_grid:
            rets = [resolve(t["path"], sl_r, tp_r)[2] for t in trades]
            pf = pf_of(rets)
            row.append((pf, sum(rets)))
            if best is None or pf > best[0]:
                best = (pf, sl_r, tp_r, sum(rets))
        print(f"    {sl_r:<8.2f}" + "".join(f"{pf:>7.2f}" if pf != float('inf') else f"{'inf':>7}" for pf, _ in row))
    print(f"  MEJOR: SL={best[1]}R TP={best[2]}R -> PF={best[0]:.2f} pnl_total={best[3]:+.1f}R")
    return best


def year_by_year(name, trades, candidates):
    print(f"\n=== {name}: año-por-año para combos candidatos ===")
    by_year = {}
    for t in trades:
        by_year.setdefault(t["day"][:4], []).append(t)
    for sl_r, tp_r, label in candidates:
        print(f"\n  -- {label} (SL={sl_r}R TP={tp_r}R) --")
        rets_all = [resolve(t["path"], sl_r, tp_r)[2] for t in trades]
        print(f"    POOL: n={len(rets_all)} PF={pf_of(rets_all):.2f} pnl={sum(rets_all):+.1f}R")
        for year in sorted(by_year):
            rets_y = [resolve(t["path"], sl_r, tp_r)[2] for t in by_year[year]]
            if not rets_y:
                continue
            pf_y = pf_of(rets_y)
            pf_s = f"{pf_y:.2f}" if pf_y != float("inf") else "inf"
            print(f"      {year}: n={len(rets_y):>4} PF={pf_s:>5} pnl={sum(rets_y):+7.1f}R")


def main():
    print("Cargando 10 años...")
    days = load_days(range(2016, 2027))

    print("\nEscaneando S4 SWP...")
    s4_trades = scan_signals(days, sweep_reclaim(("r", 0.5))(), c4=True)
    best_s4 = widened_grid("S4 SWP", s4_trades)
    year_by_year("S4 SWP", s4_trades, [
        (1.0, 0.5, "ACTUAL"),
        (best_s4[1], best_s4[2], "MEJOR grid extendido"),
        (0.3, 0.8, "candidato conservador (SL ajustado, TP moderado)"),
    ])

    print("\nEscaneando LWR...")
    lwr_trades = scan_signals(days, wick_reversal(("r", 0.5), wick_thresh=0.60, min_rvol=3.0)(), c4=False)
    best_lwr = widened_grid("LWR", lwr_trades)
    year_by_year("LWR", lwr_trades, [
        (1.0, 0.5, "ACTUAL"),
        (best_lwr[1], best_lwr[2], "MEJOR grid extendido"),
        (0.3, 0.8, "candidato conservador (SL ajustado, TP moderado)"),
    ])


if __name__ == "__main__":
    main()
