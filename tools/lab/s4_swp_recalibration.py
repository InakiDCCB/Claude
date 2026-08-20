"""Recalibración de S4 SWP (2026-08-19): el backtest de 10 años mostró TP=0.5R/SL=1R con hit%
64.7% pool -> PF 0.93 (breakeven teórico requiere hit=SL/(SL+TP)=66.7%, no se alcanza la mayoría de
los años). Barre TP en R (SL sigue siendo estructural: sweep_low - 0.05, sin cambios) y min_depth/
within para encontrar una calibración con PF>1 robusto full+recent+año-por-año.

Uso: python s4_swp_recalibration.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from backtest import stats, run_market, sweep_reclaim

sys.path.insert(0, str(Path(__file__).parent))
from backtest_live_full_history import load_days, wilson_lb, fmt_stats

RECENT_YEARS = {"2023", "2024", "2025", "2026"}


def main():
    print("Cargando días 2016-2026...")
    days = load_days(range(2016, 2027))
    print(f"{len(days)} días\n")

    print("=== Grid TP (R) x min_depth, SL estructural sin cambios, C4=True ===")
    print(f"{'TP(R)':<8}{'min_depth':<11}{'n(pool)':>9}{'hit%':>7}{'wilsonLB':>10}{'PF':>7}"
          f"{'pnl(pool)':>11}{'n(rec)':>8}{'hit%(rec)':>10}{'PF(rec)':>9}{'pnl(rec)':>10}")
    best = []
    for tp_r in (0.3, 0.4, 0.5, 0.6, 0.75, 1.0, 1.25, 1.5):
        for min_depth in (0.01, 0.10, 0.30):
            trades = run_market(days, sweep_reclaim(("r", tp_r), min_depth=min_depth)(), c4=True)
            s = stats(trades)
            if s is None or s["n"] < 20:
                continue
            recent = [t for t in trades if t["day"][:4] in RECENT_YEARS]
            sr = stats(recent)
            pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "inf"
            wlb = wilson_lb(s["w"], s["n"])
            if sr:
                pfr_s = f"{sr['pf']:.2f}" if sr["pf"] != float("inf") else "inf"
                print(f"{tp_r:<8}{min_depth:<11}{s['n']:>9}{s['hit']:>6.1f}%{wlb*100:>9.1f}%"
                      f"{pf_s:>7}{s['pnl']:>11.2f}{sr['n']:>8}{sr['hit']:>9.1f}%{pfr_s:>9}{sr['pnl']:>10.2f}")
                best.append((tp_r, min_depth, s, sr))
            else:
                print(f"{tp_r:<8}{min_depth:<11}{s['n']:>9}{s['hit']:>6.1f}%{wlb*100:>9.1f}%"
                      f"{pf_s:>7}{s['pnl']:>11.2f}{'--':>8}{'--':>10}{'--':>9}{'--':>10}")

    # candidatos con PF>1 tanto en pool como en reciente
    print("\n=== Candidatos con PF>1.0 en AMBAS columnas (pool y reciente) ===")
    candidates = [(tp, md, s, sr) for tp, md, s, sr in best
                  if s["pf"] > 1.0 and sr["pf"] > 1.0]
    if not candidates:
        print("  Ninguno.")
    for tp, md, s, sr in candidates:
        print(f"  TP={tp}R min_depth={md}: pool PF={s['pf']:.2f} n={s['n']} | "
              f"recent PF={sr['pf']:.2f} n={sr['n']}")
        # año por año para los candidatos
        trades = run_market(days, sweep_reclaim(("r", tp), min_depth=md)(), c4=True)
        by_year = {}
        for t in trades:
            by_year.setdefault(t["day"][:4], []).append(t)
        for yr in sorted(by_year):
            sy = stats(by_year[yr])
            print(f"      {yr}: {fmt_stats(sy)}")


if __name__ == "__main__":
    main()
