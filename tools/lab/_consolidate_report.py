"""One-off: corre los 3 runners del roster completo (intraday, TD9S, GT diario), silencia su
stdout normal, y vuelca UN JSON consolidado + un resumen condensado (top-line + mejor/peor bucket
de estacionalidad y regimen por sistema) a stdout. Usado para armar el reporte final -- no es
parte del roster de tests en si (esos son backtest_all_intraday.py / backtest_all_td9s.py /
backtest_all_daily_gt.py, cada uno corrible independientemente)."""
import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import backtest_all_intraday as intraday_mod
import backtest_all_td9s as td9s_mod
import backtest_all_daily_gt as gt_mod


def run_intraday():
    days = intraday_mod.load_days(range(2016, 2027))
    out = {}
    for name, status, runner in intraday_mod.ROSTER:
        trades = runner(days)
        s = intraday_mod.stats(trades)
        sc = intraday_mod.horizon_score(s)
        seas = intraday_mod.seasonality_breakdown(trades, days, intraday_mod.stats)
        out[name] = {"status": status, "stats": s, "score": sc, "seasonality": seas}
    return out


def best_worst(seas, key):
    group = seas.get(key) or {}
    usable = {k: v for k, v in group.items() if v["n"] >= 10}
    if not usable:
        return None, None
    best = max(usable.items(), key=lambda kv: kv[1]["pf"] if isinstance(kv[1]["pf"], (int, float)) else 99)
    worst = min(usable.items(), key=lambda kv: kv[1]["pf"] if isinstance(kv[1]["pf"], (int, float)) else -99)
    return best, worst


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        combined = {}
        combined.update(run_intraday())
        combined.update(td9s_mod.main())
        combined.update(gt_mod.main())

    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("full_roster_results.json")
    out_path.write_text(json.dumps(combined, ensure_ascii=False, default=str, indent=2))

    print(f"{'sistema':<28}{'n':>7}{'hit%':>7}{'PF':>7}{'pnl/ret':>12}  mejor(wd/reg)  peor(wd/reg)")
    for name, v in combined.items():
        s = v["stats"]
        if not s:
            print(f"{name:<28}  n=0")
            continue
        pf = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "inf"
        bw_wd = best_worst(v["seasonality"], "by_weekday")
        bw_rg = best_worst(v["seasonality"], "by_regime")
        b_wd = f"{bw_wd[0][0]}={bw_wd[0][1]['pf']}" if bw_wd[0] else "-"
        w_wd = f"{bw_wd[1][0]}={bw_wd[1][1]['pf']}" if bw_wd[1] else "-"
        b_rg = f"{bw_rg[0][0]}={bw_rg[0][1]['pf']}" if bw_rg[0] else "-"
        w_rg = f"{bw_rg[1][0]}={bw_rg[1][1]['pf']}" if bw_rg[1] else "-"
        print(f"{name:<28}{s['n']:>7}{s['hit']:>6.1f}%{pf:>7}{s['pnl']:>+12.2f}  "
              f"best_wd:{b_wd} worst_wd:{w_wd}  best_reg:{b_rg} worst_reg:{w_rg}")
    print(f"\n[guardado] {out_path}")


if __name__ == "__main__":
    main()
