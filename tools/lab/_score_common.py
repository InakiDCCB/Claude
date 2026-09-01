"""Score/seasonality compartidos por todos los scripts de tools/lab/ que evaluan un
indicador/sistema nuevo o re-evaluan uno existente (decision usuario 2026-08-28): el hit ratio
NO pondera el veredicto -- es dato de validez, se imprime pero nunca decide. Lo que manda es
P&L/PF. Cada corrida debe poder reportar si el sistema tiene edge solo en condiciones especificas
(estacionalidad dia/mes, regimen liq x vol) antes de descartarlo por el agregado plano.

Extraido de horizon_lab.py (antes vivia solo ahi) para que backtest_all_intraday.py,
backtest_all_daily_gt.py y horizon_lab.py compartan una sola definicion -- ver
feedback_hit_ratio_not_a_filter_research.md.

Trabaja sobre trade dicts {"day": "YYYY-MM-DD", "pnl": float, ...} (formato de tools/backtest.py
stats()) y objetos con .date/.h/.l/.c/.v (Day de tools/backtest.py) o cualquier objeto con esos
mismos atributos (duck typing -- td9s/GT diario adaptan sus propias estructuras a esta forma).
"""
from __future__ import annotations

import datetime as dt


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def horizon_score(s) -> dict:
    """0-100 = Performance(0-50, integro PF/expectancy) + RiskMgmt(0-50, n + mLL).
    Hit ratio NO pondera -- se reporta aparte, nunca decide. DEPLOY>=65 / PAPER>=45 / KILLED<45."""
    if s is None or s["n"] == 0:
        return {"performance": 0.0, "risk_mgmt": 0.0, "total": 0.0, "verdict": "KILLED"}
    pf = 3.0 if s["pf"] == float("inf") else s["pf"]
    perf = _clip((pf - 1.0) / 1.5, 0, 1) * 50
    risk = _clip(s["n"] / 30, 0, 1) * 25 + _clip((6 - s["mll"]) / 6, 0, 1) * 25
    total = perf + risk
    if s["n"] < 20:
        total *= _clip(s["n"] / 20, 0.3, 1.0)
    if s["pnl"] <= 0:
        total = min(total, 35)
    verdict = "DEPLOY" if total >= 65 else ("PAPER" if total >= 45 else "KILLED")
    return {"performance": round(perf, 1), "risk_mgmt": round(risk, 1),
            "total": round(total, 1), "verdict": verdict}


def wilson_lb(wins, n, z=1.96):
    if n == 0:
        return None
    p = wins / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (center - margin) / denom


def day_features(days):
    """Bucket liq/vol por dia via mediana de la propia ventana -- mismo espiritu que
    market_conditions.liquidity/volatility (rvol30/day_range_pct) pero offline, sin Supabase.
    `days`: iterable de objetos con .date/.h/.l/.c/.v (listas indexables)."""
    ranges = {d.date: (max(d.h) - min(d.l)) / d.c[0] * 100 for d in days}
    vols = {d.date: sum(d.v) for d in days}
    if not ranges:
        return {}
    vol_med = sorted(ranges.values())[len(ranges) // 2]
    liq_med = sorted(vols.values())[len(vols) // 2]
    return {d.date: {"volatility": "high" if ranges[d.date] >= vol_med else "low",
                      "liquidity": "high" if vols[d.date] >= liq_med else "low"}
            for d in days}


def seasonality_breakdown(trades, days, stats_fn) -> dict:
    """P&L/PF por weekday, mes y regimen liq x vol -- puramente informativo (nunca decide
    DEPLOY/PAPER/KILLED). `stats_fn`: la funcion stats() del motor correspondiente (recibe lista
    de trades, devuelve dict con n/hit/pnl/pf o None)."""
    if not trades:
        return {}
    feats = day_features(days)
    by_weekday, by_month, by_regime = {}, {}, {}
    for t in trades:
        d = dt.date.fromisoformat(t["day"])
        by_weekday.setdefault(d.strftime("%a"), []).append(t)
        by_month.setdefault(d.strftime("%Y-%m"), []).append(t)
        f = feats.get(t["day"], {})
        reg = f"{f.get('liquidity', '?')[:1]}liq_{f.get('volatility', '?')[:1]}vol"
        by_regime.setdefault(reg, []).append(t)

    def summarize(groups):
        out = {}
        for k, ts in groups.items():
            s = stats_fn(ts)
            if s:
                out[k] = {"n": s["n"], "hit": round(s["hit"], 1), "pnl": round(s["pnl"], 2),
                          "pf": "inf" if s["pf"] == float("inf") else round(s["pf"], 2)}
        return out

    return {"by_weekday": summarize(by_weekday), "by_month": summarize(by_month),
            "by_regime": summarize(by_regime)}


def print_seasonality(seas: dict, indent: str = "  ") -> None:
    labels = {"by_weekday": "dia semana", "by_month": "mes", "by_regime": "regimen liq/vol"}
    for key, title in labels.items():
        group = seas.get(key)
        if not group:
            continue
        print(f"{indent}{title}:")
        for k in sorted(group):
            v = group[k]
            pf_s = v["pf"] if isinstance(v["pf"], str) else f"{v['pf']:.2f}"
            flag = "  (n<3, ruido)" if v["n"] < 3 else ""
            print(f"{indent}  {k:<10} n={v['n']:>3}  hit={v['hit']:>5.1f}%  pnl={v['pnl']:>+7.2f}  "
                  f"PF={pf_s:<5}{flag}")
