"""S2 FVG — versión combinada de filtros (2026-08-19), construida sobre el detalle cruzado del
backtest de 10 años (ver project_systems_history.md): las tres condiciones que individualmente
mejoraban el pnl eran (a) slope_up & above_vwap, (b) risk (ancho del gap) 0.30-0.50, (c) evitar
específicamente el fill ordinal #2. Prueba la combinación (a)+(b) primero (son condiciones al
momento de la señal, aplicables como filter_fn de run_fvg), y por separado el efecto de excluir
ordinal=2 (requiere post-proceso porque el ordinal no se conoce hasta armar la secuencia del día).

Uso: python s2_fvg_combined_filter.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from backtest import stats, run_fvg

sys.path.insert(0, str(Path(__file__).parent))
from backtest_live_full_history import load_days, wilson_lb, fmt_stats

RECENT_YEARS = {"2023", "2024", "2025", "2026"}


def combined_filter(day, i):
    slope_ok = day.slope30[i] is not None and day.slope30[i] > 0
    vwap_ok = day.c[i] > day.vwap[i]
    mid = (day.l[i] + day.h[i - 2]) / 2
    risk = mid - (day.l[i - 2] - 0.02)
    risk_ok = 0.30 <= risk <= 0.50
    return slope_ok and vwap_ok and risk_ok


def report(name, trades):
    print(f"\n=== {name} ===")
    s_all = stats(trades)
    print(f"  POOL 2016-2026: {fmt_stats(s_all)}")
    recent = [t for t in trades if t["day"][:4] in RECENT_YEARS]
    sr = stats(recent)
    print(f"  RECENT 2023-2026: {fmt_stats(sr)}")
    by_year = {}
    for t in trades:
        by_year.setdefault(t["day"][:4], []).append(t)
    for year in sorted(by_year):
        print(f"  {year}: {fmt_stats(stats(by_year[year]))}")
    return s_all, sr


def drop_ordinal(trades, ordinal_to_drop):
    by_day = {}
    for t in trades:
        by_day.setdefault(t["day"], []).append(t)
    out = []
    for d in by_day:
        by_day[d].sort(key=lambda t: t["ei"])
        for idx, t in enumerate(by_day[d]):
            if idx + 1 != ordinal_to_drop:
                out.append(t)
    return out


def main():
    print("Cargando días 2016-2026...")
    days = load_days(range(2016, 2027))
    print(f"{len(days)} días\n")

    print("Corriendo S2 FVG BASE (sin filtro, C4=True)...")
    base = run_fvg(days, None, c4=True)
    report("S2 FVG BASE", base)

    print("\nCorriendo S2 FVG COMBINADO (slope_up & above_vwap & risk 0.30-0.50, C4=True)...")
    combined = run_fvg(days, combined_filter, c4=True)
    report("S2 FVG COMBINADO", combined)

    print("\nCorriendo S2 FVG BASE menos ordinal=2 (post-proceso, C4=True)...")
    base_no2 = drop_ordinal(base, 2)
    report("S2 FVG BASE sin ordinal=2", base_no2)

    print("\nCorriendo S2 FVG COMBINADO + sin ordinal=2...")
    combined_no2 = drop_ordinal(combined, 2)
    report("S2 FVG COMBINADO sin ordinal=2", combined_no2)


if __name__ == "__main__":
    main()
