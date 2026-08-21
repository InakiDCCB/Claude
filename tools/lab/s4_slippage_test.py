"""S4 SWP: prueba los dos combos candidatos (conservador SL=0.3R/TP=0.8R y mejor-del-grid
SL=0.15R/TP=1.2R, ver s4_lwr_path_analysis_v2.py) bajo un modelo de SLIPPAGE explícito -- el motor
base resuelve por toque exacto de máximo/mínimo de barra, sin fricción. Acá se resta un slippage en
dólares (típico spread QQQ ~$0.01-0.02, más un buffer conservador) tanto al SL (peor fill, más
pérdida) como al TP (peor fill, menos ganancia) para ver si el edge sobrevive fricción realista.

Uso: python s4_slippage_test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from backtest import sweep_reclaim  # noqa: E402
from s4_lwr_path_analysis import load_days, scan_signals  # noqa: E402


def resolve_slip(path, sl_r, tp_r, risk, slip_dollars):
    slip_r = slip_dollars / risk
    for offset, o_r, l_r, h_r, c_r in path:
        if l_r <= -sl_r:
            base = o_r if o_r <= -sl_r else -sl_r
            return "SL", offset, base - slip_r
        if h_r >= tp_r:
            base = o_r if o_r >= tp_r else tp_r
            return "TP", offset, base - slip_r
    last = path[-1]
    return "TIME", last[0], last[4]


def pf_of(rets):
    gw = sum(r for r in rets if r > 0)
    gl = -sum(r for r in rets if r <= 0)
    return gw / gl if gl > 0 else float("inf")


def main():
    print("Cargando 10 años y escaneando S4 SWP...")
    days = load_days(range(2016, 2027))
    trades = scan_signals(days, sweep_reclaim(("r", 0.5))(), c4=True)
    print(f"{len(trades)} trades.\n")

    candidates = [
        (1.0, 0.5, "ACTUAL"),
        (0.3, 0.8, "Conservador"),
        (0.15, 1.2, "Mejor del grid"),
    ]
    slippages = (0.0, 0.01, 0.02, 0.03, 0.05)

    for sl_r, tp_r, label in candidates:
        print(f"=== {label} (SL={sl_r}R TP={tp_r}R) ===")
        print(f"  {'slippage':<10}{'PF':>8}{'pnl_total_R':>14}{'hit%':>8}")
        for slip in slippages:
            rets = []
            for t in trades:
                _, _, exit_r = resolve_slip(t["path"], sl_r, tp_r, t["risk"], slip)
                rets.append(exit_r)
            pf = pf_of(rets)
            pf_s = f"{pf:.2f}" if pf != float("inf") else "inf"
            hit = sum(1 for r in rets if r > 0) / len(rets) * 100
            print(f"  ${slip:<9.2f}{pf_s:>8}{sum(rets):>14.1f}{hit:>8.1f}")
        print()

    # --- año-por-año con slippage=$0.02 (asuncion central) para los 3 combos ---
    print("\n=== Año-por-año con slippage=$0.02 (asunción central) ===")
    by_year = {}
    for t in trades:
        by_year.setdefault(t["day"][:4], []).append(t)
    for sl_r, tp_r, label in candidates:
        print(f"\n  -- {label} --")
        for year in sorted(by_year):
            rets_y = [resolve_slip(t["path"], sl_r, tp_r, t["risk"], 0.02)[2] for t in by_year[year]]
            pf_y = pf_of(rets_y)
            pf_s = f"{pf_y:.2f}" if pf_y != float("inf") else "inf"
            print(f"    {year}: n={len(rets_y):>4} PF={pf_s:>5} pnl={sum(rets_y):+7.1f}R")


if __name__ == "__main__":
    main()
