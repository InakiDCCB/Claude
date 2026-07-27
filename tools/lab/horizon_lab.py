"""Horizon Shadow Lab — frase en lenguaje natural -> backtest sobre TU motor -> veredicto.

Reimplementacion del pipeline "Horizon AI Quant Agent" NATIVA a este repo:

    frase --[horizon_parser]--> Strategy IR --[compile]--> run_market/run_fvg(qqq_1min)
          --> stats() --> Horizon Score (DEPLOY/PAPER/KILLED)

Reutiliza INTEGRAMENTE backtest.py (Day, simulate, run_market, run_fvg, stats, factories)
y backtest_short.py (motor espejo). NO coloca ordenes, NO escribe en Supabase, NO toca el
loop ni cycle_prompt. Es un acelerador OFFLINE de la directiva STANDING "nuevos sistemas"
(ver memoria project_new_systems_research). Distinto del "shadow" del loop (que loggea
senales en analysis_log) — esto es un laboratorio de hipotesis.

Uso:
    python horizon_lab.py "FVG con maximo 2 fills al dia"
    python horizon_lab.py "RSI2 sobrevendido por debajo de 10" --since 2026-05-01
    python horizon_lab.py "sweep de maximos en corto" --no-llm
    python horizon_lab.py "pullback a VWAP" --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))   # permite `from backtest import ...`

from backtest import (Day, stats, run_market, run_fvg, rsi2_dip, vwap_pullback,
                      sweep_reclaim, gap_fill, ema9_reclaim, vwap_band, red_run)
from backtest_short import (run_market_short, run_fvg_short, rsi2_pop, vwap_rejection,
                            sweep_rejection, gap_fade)
from horizon_parser import parse, StrategyIR

DATA = Path(__file__).parent / "data" / "qqq_1min.json"


def build_days(since: str = "2026-05-01"):
    bars = json.loads(DATA.read_text())
    bydate: dict[str, list] = {}
    for b in bars:
        bydate.setdefault(b["t"][:10], []).append(b)
    dates = sorted(bydate)
    days_all, prev = {}, None
    for d in dates:
        days_all[d] = Day(d, bydate[d], prev)
        prev = days_all[d]
    return [days_all[d] for d in dates if d >= since]


# ----------------------- IR -> trades (compilador) -----------------------

def compile_ir(ir: StrategyIR, days, c4: bool):
    p, sig, long = ir.params, ir.signal, ir.direction == "long"

    if sig == "rsi2":
        f = (rsi2_dip if long else rsi2_pop)(
            p["tp"], thresh=p["thresh"], sl_mult=p["sl"], time_stop=int(p["time_stop"]))
        return (run_market if long else run_market_short)(days, f(), c4)

    if sig == "vwap_pullback":
        tp = ("r", p["tp_r"])
        if long:
            f = vwap_pullback(p["rsi_lo"], p["rsi_hi"], tp=tp, be_at_r=p.get("be_at_r"))
            return run_market(days, f(), c4)
        f = vwap_rejection(p["rsi_lo"], p["rsi_hi"], tp=tp)
        return run_market_short(days, f(), c4)

    if sig == "sweep":
        f = (sweep_reclaim if long else sweep_rejection)(("r", p["tp_r"]), min_depth=p["min_depth"])
        return (run_market if long else run_market_short)(days, f(), c4)

    if sig == "gap_fill":
        f = (gap_fill if long else gap_fade)(p["min_gap"])
        return (run_market if long else run_market_short)(days, f(), c4)

    if sig == "fvg":
        filt = _fvg_filter(p, long)
        return (run_fvg(days, filt, c4, max_fills=p.get("max_fills")) if long
                else run_fvg_short(days, filt, c4, max_fills=p.get("max_fills")))

    if sig == "ema9_reclaim":
        return run_market(days, ema9_reclaim(("r", p["tp_r"]))(), c4)
    if sig == "vwap_band":
        return run_market(days, vwap_band(p["mult"], ("r", p["tp_r"]))(), c4)
    if sig == "red_run":
        tp = ("fpc",) if p["tp"] == "fpc" else ("r", float(p["tp"]))
        return run_market(days, red_run(tp, run_len=int(p["run_len"]))(), c4)

    raise ValueError(f"signal no compilable: {sig}")


def _fvg_filter(p, long):
    lo, hi = p.get("risk_lo"), p.get("risk_hi")
    if lo is None or hi is None:
        return None
    if long:
        def filt(day, i, lo=lo, hi=hi):
            mid = (day.l[i] + day.h[i - 2]) / 2
            return lo <= mid - (day.l[i - 2] - 0.02) <= hi
    else:
        def filt(day, i, lo=lo, hi=hi):
            mid = (day.h[i] + day.l[i - 2]) / 2
            return lo <= (day.h[i - 2] + 0.02) - mid <= hi
    return filt


# ----------------------- Horizon Score (calibrado al playbook) -----------------------

def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def horizon_score(s) -> dict:
    """0-100 = Performance(0-50) + RiskMgmt(0-50), sobre las metricas del repo.
    Referencias del playbook: portfolio 69% hit PF 1.90 = DEPLOY; PF~1.0 (E9RC/VPOC) = KILLED.
    NO garantiza rentabilidad: filtra rapido lo que claramente no tiene edge."""
    if s is None or s["n"] == 0:
        return {"performance": 0.0, "risk_mgmt": 0.0, "total": 0.0, "verdict": "KILLED"}
    pf = 3.0 if s["pf"] == float("inf") else s["pf"]
    perf = _clip((pf - 1.0) / 1.5, 0, 1) * 35 + _clip((s["hit"] - 50) / 30, 0, 1) * 15
    risk = _clip(s["n"] / 30, 0, 1) * 25 + _clip((6 - s["mll"]) / 6, 0, 1) * 25
    total = perf + risk
    if s["n"] < 20:                      # muestra chica -> penaliza (anti-overfit)
        total *= _clip(s["n"] / 20, 0.3, 1.0)
    if s["pnl"] <= 0:                     # expectancy negativa nunca pasa
        total = min(total, 35)
    verdict = "DEPLOY" if total >= 65 else ("PAPER" if total >= 45 else "KILLED")
    return {"performance": round(perf, 1), "risk_mgmt": round(risk, 1),
            "total": round(total, 1), "verdict": verdict}


# ----------------------- pipeline / CLI -----------------------

def _row(label, s, sc):
    if s is None:
        return f"  {label:<10} n=0"
    pf = "  inf" if s["pf"] == float("inf") else f"{s['pf']:5.2f}"
    return (f"  {label:<10} n={s['n']:>3}  hit={s['hit']:>5.1f}%  pnl={s['pnl']:>+7.2f}/sh  "
            f"mean={s['mean']:>+6.3f}±{s['se']:.3f}  PF={pf}  mLL={s['mll']:>2}  "
            f"score={sc['total']:>5.1f} [{sc['verdict']}]")


def run_pipeline(sentence: str, since: str = "2026-05-01", use_llm: bool = True) -> dict:
    days = build_days(since)
    ir = parse(sentence, use_llm=use_llm)

    print("=" * 72)
    print("HORIZON SHADOW LAB  ·  frase -> IR -> backtest (QQQ 1-min) -> veredicto")
    print("=" * 72)
    print(f"[01 Parse]  {sentence!r}")
    print(f"[02 IR]     {json.dumps(ir.to_dict(), ensure_ascii=False)}")
    print(f"[03-04 Backtest]  ventana={since}->{days[-1].date}  sesiones={len(days)}  universo=QQQ")

    t_base = compile_ir(ir, days, c4=False)
    t_c4 = compile_ir(ir, days, c4=True)
    s_base, s_c4 = stats(t_base), stats(t_c4)
    sc_base, sc_c4 = horizon_score(s_base), horizon_score(s_c4)
    print(_row("base", s_base, sc_base))
    print(_row("+C4", s_c4, sc_c4))

    # El veredicto se toma sobre la mejor de las dos variantes
    best_sc, best_lbl = (sc_c4, "+C4") if sc_c4["total"] >= sc_base["total"] else (sc_base, "base")
    print(f"\n[05 Validate]  Horizon Score = {best_sc['total']}/100 ({best_lbl})  ->  {best_sc['verdict']}")
    print("[06-07]        " + {
        "DEPLOY": "candidato fuerte -> promover a SHADOW del loop (5 sesiones) antes de LIVE.",
        "PAPER":  "edge marginal -> shadow-logging y vigilar sobreajuste / n.",
        "KILLED": "sin edge suficiente en esta ventana -> descartar o re-especificar.",
    }[best_sc["verdict"]])
    print("=" * 72)

    return {"ir": ir.to_dict(), "since": since, "sessions": len(days),
            "base": {"stats": s_base, "score": sc_base},
            "c4": {"stats": s_c4, "score": sc_c4},
            "verdict": best_sc["verdict"], "score": best_sc["total"]}


def main() -> int:
    ap = argparse.ArgumentParser(description="Horizon Shadow Lab (offline, QQQ 1-min)")
    ap.add_argument("sentence", nargs="+")
    ap.add_argument("--since", default="2026-05-01", help="primera sesion (YYYY-MM-DD)")
    ap.add_argument("--no-llm", action="store_true", help="fuerza el parser por reglas")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        out = run_pipeline(" ".join(a.sentence), since=a.since, use_llm=not a.no_llm)
    except ValueError as e:
        print(f"[horizon-lab] no se pudo compilar la estrategia: {e}")
        return 2
    if a.json:
        print("\n" + json.dumps(out, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
