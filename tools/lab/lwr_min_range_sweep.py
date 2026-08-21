"""LWR: el problema no es el SL/TP, es que su R natural ($0.13-0.24 mediana) es tan chico que
cualquier SL ajustado cae en centavos -- del orden del spread/ruido de QQQ. `min_range` (rango
mínimo O-H-L-C de la vela de rechazo) hoy es 0.02, casi sin efecto -- prácticamente cualquier vela
califica. Este barrido sube `min_range` para exigir velas de rechazo más grandes (R natural más
grande) y re-evalúa los dos combos candidatos (conservador y "adaptado" del mejor-del-grid) con
slippage=$0.02, para encontrar un punto donde el combo agresivo se vuelva ejecutable sin perder el
edge.

Uso: python lwr_min_range_sweep.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from backtest import wick_reversal  # noqa: E402
from s4_lwr_path_analysis import load_days, scan_signals  # noqa: E402


def resolve_slip(path, sl_r, tp_r, risk, slip_dollars):
    slip_r = slip_dollars / risk
    for offset, o_r, l_r, h_r, c_r in path:
        if l_r <= -sl_r:
            base = o_r if o_r <= -sl_r else -sl_r
            return base - slip_r
        if h_r >= tp_r:
            base = o_r if o_r >= tp_r else tp_r
            return base - slip_r
    return path[-1][4]


def pf_of(rets):
    gw = sum(r for r in rets if r > 0)
    gl = -sum(r for r in rets if r <= 0)
    return gw / gl if gl > 0 else float("inf")


def main():
    print("Cargando 10 años...")
    days = load_days(range(2016, 2027))

    min_ranges = (0.02, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.70)
    combos = [(1.0, 0.5, "actual"), (0.3, 0.8, "conservador"), (0.15, 1.2, "adaptado-agresivo")]

    print(f"\n{'min_range':<10}{'n_signals':>10}{'1R_$_mediana':>14}{'1R_$_p25':>10}"
          + "".join(f"{'PF_'+c[2]+'(slip2c)':>20}" for c in combos))
    for mr in min_ranges:
        sig = wick_reversal(("r", 0.5), wick_thresh=0.60, buffer_sl=0.05, min_range=mr, min_rvol=3.0)()
        trades = scan_signals(days, sig, c4=False)
        if not trades:
            print(f"{mr:<10.2f}{'0 trades':>10}")
            continue
        risks = sorted(t["risk"] for t in trades)
        n = len(risks)
        pf_strs = []
        for sl_r, tp_r, label in combos:
            rets = [resolve_slip(t["path"], sl_r, tp_r, t["risk"], 0.02) for t in trades]
            pf = pf_of(rets)
            pf_strs.append(f"{pf:.2f}" if pf != float("inf") else "inf")
        print(f"{mr:<10.2f}{n:>10}{risks[n//2]:>14.3f}{risks[n//4]:>10.3f}"
              + "".join(f"{p:>20}" for p in pf_strs))

    # --- detalle año-por-año para un min_range candidato razonable (0.30) con ambos combos ---
    print("\n\n=== Detalle año-por-año, min_range=0.30, slippage=$0.02 ===")
    sig = wick_reversal(("r", 0.5), wick_thresh=0.60, buffer_sl=0.05, min_range=0.30, min_rvol=3.0)()
    trades = scan_signals(days, sig, c4=False)
    print(f"n total = {len(trades)}")
    risks = sorted(t["risk"] for t in trades)
    print(f"1R $ mediana={risks[len(risks)//2]:.3f}  p25={risks[len(risks)//4]:.3f}  p75={risks[3*len(risks)//4]:.3f}")
    by_year = {}
    for t in trades:
        by_year.setdefault(t["day"][:4], []).append(t)
    for sl_r, tp_r, label in combos:
        print(f"\n  -- {label} (SL={sl_r}R TP={tp_r}R) --")
        rets_all = [resolve_slip(t["path"], sl_r, tp_r, t["risk"], 0.02) for t in trades]
        print(f"    POOL: n={len(rets_all)} PF={pf_of(rets_all):.2f} pnl={sum(rets_all):+.1f}R")
        for year in sorted(by_year):
            rets_y = [resolve_slip(t["path"], sl_r, tp_r, t["risk"], 0.02) for t in by_year[year]]
            if not rets_y:
                continue
            pf_y = pf_of(rets_y)
            pf_s = f"{pf_y:.2f}" if pf_y != float("inf") else "inf"
            print(f"      {year}: n={len(rets_y):>4} PF={pf_s:>5} pnl={sum(rets_y):+7.1f}R")


if __name__ == "__main__":
    main()
