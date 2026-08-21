"""Order Flow Indicator (OFI) — calibracion de dos hipotesis sobre tools/data/qqq_trades.json.

Regla de tick (client-side, Alpaca no expone lado del trade): uptick=compra agresiva,
downtick=venta agresiva, sin cambio=hereda. Agregado por barra 1-min via
backtest.attach_orderflow() -> day.delta (buy_vol-sell_vol) / day.cvd (acumulado sesion).

(a) Confirmacion LWR: exigir delta[i]>0 en el bar de rechazo de mecha, mejora hit/PF vs LWR base?
(b) Senal propia: divergencia CVD (precio hace minimo de sesion, CVD no) -> fade alcista.

Uso: python calibrate_ofi.py [--since 2026-04-20]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lab"))

from backtest import stats, run_market, wick_reversal, attach_orderflow
from analysis_30d import build_days
from horizon_lab import horizon_score

TRADES_FILE = Path(__file__).parent / "data" / "qqq_trades.json"
TP_MODES = [("r", 0.5), ("r", 1.0), ("r", 1.5)]


def load_trades_by_day():
    trades = json.loads(TRADES_FILE.read_text())
    by_day = {}
    for t in trades:
        by_day.setdefault(t["t"][:10], []).append(t)
    return by_day


def _row(label, s, sc):
    if s is None:
        return f"  {label:<30} n=0"
    pf = "  inf" if s["pf"] == float("inf") else f"{s['pf']:5.2f}"
    return (f"  {label:<30} n={s['n']:>3}  hit={s['hit']:>5.1f}%  pnl={s['pnl']:>+7.2f}/sh  "
            f"PF={pf}  mLL={s['mll']:>2}  score={sc['total']:>5.1f} [{sc['verdict']}]")


def wick_reversal_of(tp, wick_thresh=0.60, min_rvol=3.0, require_delta_pos=False):
    """Wrapper sobre wick_reversal (backtest.py) que opcionalmente exige delta[i]>0."""
    base_factory = wick_reversal(tp, wick_thresh=wick_thresh, min_rvol=min_rvol)

    def factory():
        base_fn = base_factory()

        def fn(day, i):
            sig = base_fn(day, i)
            if sig is None:
                return None
            if require_delta_pos:
                if not hasattr(day, "delta") or i >= len(day.delta) or day.delta[i] <= 0:
                    return None
            return sig
        return fn
    return factory


def cvd_divergence_long(tp):
    """Precio hace minimo de sesion en la barra i pero CVD NO hace minimo nuevo -> fade alcista."""
    def factory():
        def fn(day, i):
            if not hasattr(day, "cvd") or i < 5:
                return None
            if day.l[i] > min(day.l[:i + 1]):
                return None                       # no es minimo de sesion
            if day.cvd[i] <= min(day.cvd[:i]):
                return None                       # CVD tambien hizo minimo -> sin divergencia
            return {"sl_abs": round(day.l[i] - 0.05, 2), "tp": tp}
        return fn
    return factory


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    all_days, _ = build_days()
    days = [d for d in all_days if a.since is None or d.date >= a.since]
    trades_by_day = load_trades_by_day()

    attached, missing = 0, 0
    for day in days:
        tr = trades_by_day.get(day.date)
        if tr is None:
            missing += 1
            continue
        attach_orderflow(day, tr)
        attached += 1

    print("=" * 78)
    print(f"OFI calibration  ·  QQQ  ·  {days[0].date} -> {days[-1].date}  "
          f"({len(days)} sesiones, {attached} con order-flow, {missing} sin trades cacheados)")
    print("=" * 78)

    days_of = [d for d in days if hasattr(d, "delta")]

    print("\n=== (a) LWR base vs LWR + delta[i]>0 ===")
    for tp in TP_MODES:
        t_base = run_market(days_of, wick_reversal_of(tp, require_delta_pos=False)(), c4=False)
        t_filt = run_market(days_of, wick_reversal_of(tp, require_delta_pos=True)(), c4=False)
        s_base, s_filt = stats(t_base), stats(t_filt)
        sc_base, sc_filt = horizon_score(s_base), horizon_score(s_filt)
        print(_row(f"base tp={tp}", s_base, sc_base))
        print(_row(f"+delta>0 tp={tp}", s_filt, sc_filt))

    print("\n=== (b) CVD divergence (fade alcista en minimo de sesion sin minimo de CVD) ===")
    best = None
    for tp in TP_MODES:
        t = run_market(days_of, cvd_divergence_long(tp)(), c4=False)
        t4 = run_market(days_of, cvd_divergence_long(tp)(), c4=True)
        s0, s4 = stats(t), stats(t4)
        sc0, sc4 = horizon_score(s0), horizon_score(s4)
        print(_row(f"tp={tp} base", s0, sc0))
        print(_row(f"tp={tp} +C4", s4, sc4))
        for tag, s, sc in ((f"tp={tp} base", s0, sc0), (f"tp={tp} +C4", s4, sc4)):
            if best is None or sc["total"] > best[2]["total"]:
                best = (tag, s, sc)

    print("\n" + "=" * 78)
    if best:
        tag, s, sc = best
        print(f"MEJOR (b) CVD divergence: {tag}  ->  Horizon Score {sc['total']}/100  ->  {sc['verdict']}")
    print("=" * 78)


if __name__ == "__main__":
    main()
