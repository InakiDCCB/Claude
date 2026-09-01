"""Crossovers / confluencia entre TODOS los sistemas que NO califican para shadow/live bajo la
metodologia nueva (score=100% PF, ver feedback_hit_ratio_not_a_filter_research.md) -- pedido
usuario 2026-08-28: "probemos hacer los crossovers entre si con aquellos que no cumplan... busquemos
mayor amplitud y mas indicadores".

Idea: un sistema aislado puede no tener edge, pero si DOS señales distintas confirman el mismo
dia (confluencia), la coincidencia podria filtrar los dias/momentos de mayor calidad. Se prueba en
dos niveles:
  1. CONFLUENCIA POR DIA: de los trades de A, separar los que cayeron en un dia donde B TAMBIEN
     disparo (aunque sea en otro momento) vs los que no -- compara PF de ambos subgrupos.
  2. CONFLUENCIA POR BARRA (±10 barras, mismo dia): version mas estricta, solo para los pares que
     sobreviven el filtro de nivel 1 -- evita correr la version cara sobre las ~120 combinaciones.

Universo (18 sistemas intradia KILLED + 5 diarios Golden Ticket no-LIVE, ver ROSTER de
backtest_all_intraday.py / backtest_all_td9s.py / backtest_new_indicators.py / backtest_all_daily_gt.py):
14 LONG x 14 LONG (91 pares) + 9 SHORT x 9 SHORT (36 pares) intradia, + 4x4 diario (6 pares) --
127 pruebas en total. Con ese volumen, el riesgo de falso positivo por comparaciones multiples es
real (misma leccion que project_breadth_research.md / gt_exhaustive_sweep.py) -- el umbral de
"candidato" exige PF>=1.4 simultaneo en AMBOS subgrupos-espejo (A confluente Y B confluente) con
n>=30 cada uno, y se reporta el conteo total de pruebas para que cualquier lectura del resultado
lo tenga en cuenta.

Uso: python crossover_search.py [--json out.json]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest import stats
from backtest_all_intraday import load_days, ROSTER as INTRADAY_ROSTER
from backtest_all_td9s import RSI_MIN as TD9S_RSI_MIN, SLIPPAGE as TD9S_SLIP
from td9s_full_matrix import load_bydate, build_5min_blocks, simulate_1min
from td_backtest import rsi as td_rsi, atr as td_atr, td_signals
from indicators_ext import (macd_cross, bb_reversion, stoch_reversal, with_adx_filter,
                            attach_ext_indicators)
from backtest import run_market, rsi2_dip
from backtest_short import run_market_short
from _score_common import wilson_lb

# direccion de cada sistema del roster intradia (ver backtest_all_intraday.ROSTER)
INTRADAY_DIRECTION = {
    "S1 RSI2": "long", "S2 FVG": "long", "S3 VWAPPB": "long", "S4 SWP": "long", "S5 GAPF": "long",
    "S6 SWP-short": "short", "LWR long": "long", "LWR short": "short", "OB": "long", "OBNB": "long",
    "SMC estructura BOS+CHoCH": "long", "RSI2-short (mirror)": "short",
    "VWAPPB-short (mirror)": "short", "GAPF-short (mirror)": "short",
}

NEW_IND_ROSTER = [
    ("MACD cross long", "long", lambda days: run_market(days, macd_cross("long", ("r", 1.5))(), c4=True)),
    ("MACD cross short", "short", lambda days: run_market_short(days, macd_cross("short", ("r", 1.5))(), c4=True)),
    ("BB reversion long", "long", lambda days: run_market(days, bb_reversion("long", ("r", 1.0))(), c4=True)),
    ("BB reversion short", "short", lambda days: run_market_short(days, bb_reversion("short", ("r", 1.0))(), c4=True)),
    ("Stoch reversal long", "long", lambda days: run_market(days, stoch_reversal("long", ("r", 1.0))(), c4=True)),
    ("Stoch reversal short", "short", lambda days: run_market_short(days, stoch_reversal("short", ("r", 1.0))(), c4=True)),
    ("RSI2+ADX<20", "long", lambda days: run_market(
        days, with_adx_filter(rsi2_dip(0.5, thresh=15, sl_mult=1.0, time_stop=15), max_adx=20)(), c4=True)),
    ("MACD+ADX>25", "long", lambda days: run_market(
        days, with_adx_filter(macd_cross("long", ("r", 1.5)), min_adx=25)(), c4=True)),
]


def load_td9s_trades():
    bydate = load_bydate(range(2016, 2027))
    blocks = build_5min_blocks(bydate)
    r14 = td_rsi([b["c"] for b in blocks])
    a14 = td_atr(blocks)
    sigs = td_signals(blocks)
    trades = []
    for s in sigs:
        if s["side"] != "short" or s["kind"] != "S9P":
            continue
        i = s["i"]
        if a14[i] is None or r14[i] is None or r14[i] < TD9S_RSI_MIN:
            continue
        b = blocks[i]
        entry = b["c"]
        sl, tp = entry + 2 * a14[i], entry - 3 * a14[i]
        r = simulate_1min(bydate, b["d"], b["i1"], "short", entry, sl, tp, TD9S_SLIP)
        if r is None:
            continue
        trades.append({"day": b["d"], "ei": None, "pnl": r})
    return trades


def build_all_intraday(days):
    pool = {}
    for name, _status, runner in INTRADAY_ROSTER:
        pool[name] = {"dir": INTRADAY_DIRECTION[name], "trades": runner(days)}
    for name, direction, runner in NEW_IND_ROSTER:
        pool[name] = {"dir": direction, "trades": runner(days)}
    pool["TD9S"] = {"dir": "short", "trades": load_td9s_trades()}
    return pool


def confluence_pairs(pool, direction):
    names = [n for n, v in pool.items() if v["dir"] == direction]
    results = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a_name, b_name = names[i], names[j]
            a_trades, b_trades = pool[a_name]["trades"], pool[b_name]["trades"]
            days_a = {t["day"] for t in a_trades}
            days_b = {t["day"] for t in b_trades}
            overlap_days = days_a & days_b
            if len(overlap_days) < 10:
                continue
            a_conf = [t for t in a_trades if t["day"] in days_b]
            a_noconf = [t for t in a_trades if t["day"] not in days_b]
            b_conf = [t for t in b_trades if t["day"] in days_a]
            b_noconf = [t for t in b_trades if t["day"] not in days_a]
            sa_c, sa_n = stats(a_conf), stats(a_noconf)
            sb_c, sb_n = stats(b_conf), stats(b_noconf)
            if not (sa_c and sb_c):
                continue
            results.append({
                "a": a_name, "b": b_name, "direction": direction,
                "overlap_days": len(overlap_days),
                "a_conf": sa_c, "a_noconf": sa_n, "b_conf": sb_c, "b_noconf": sb_n,
            })
    return results


def _causal_split(subject_trades, confirmer_trades, window):
    """De `subject_trades`, separa los que tienen un trade de `confirmer_trades` EN EL PASADO
    (mismo dia, 0 <= subject.ei - confirmer.ei <= window) -- causal: el confirmador tuvo que
    haber disparado ANTES O EN la barra de entrada del sujeto para poder usarse como filtro en
    tiempo real. Una version simetrica (+-window, admite confirmacion futura) es look-ahead bias
    y da resultados irreales -- detectado 2026-08-28 en S1 RSI2 x SMC estructura: PF 0.83->3.77
    con ventana simetrica se derrumbaba a ~1.03-1.13 en cuanto se exigia causalidad. Ver
    feedback_lookahead_bias_research.md."""
    by_day = {}
    for t in confirmer_trades:
        by_day.setdefault(t["day"], []).append(t["ei"])
    conf, noconf = [], []
    for t in subject_trades:
        eis = by_day.get(t["day"])
        if eis and any(0 <= t["ei"] - e <= window for e in eis):
            conf.append(t)
        else:
            noconf.append(t)
    return conf, noconf


def confluence_pairs_bar(pool, direction, window=10):
    """Confluencia CAUSAL: para el par (A,B), evalua en ambos sentidos -- A filtrado por B en el
    pasado reciente, y B filtrado por A en el pasado reciente -- cada uno es una hipotesis de
    filtro distinta (no simetrica), no una sola confluencia mutua. Excluye TD9S (bloques 5-min,
    indices no comparables en base 1-min)."""
    names = [n for n, v in pool.items() if v["dir"] == direction and n != "TD9S"]
    results = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a_name, b_name = names[i], names[j]
            a_trades, b_trades = pool[a_name]["trades"], pool[b_name]["trades"]
            a_conf, a_noconf = _causal_split(a_trades, b_trades, window)
            b_conf, b_noconf = _causal_split(b_trades, a_trades, window)
            sa_c, sa_n = stats(a_conf), stats(a_noconf)
            sb_c, sb_n = stats(b_conf), stats(b_noconf)
            if not (sa_c and sb_c) or sa_c["n"] < 10 or sb_c["n"] < 10:
                continue
            results.append({
                "a": a_name, "b": b_name, "direction": direction, "window_bars": window,
                "overlap_days": len({t["day"] for t in a_conf}),
                "a_conf": sa_c, "a_noconf": sa_n, "b_conf": sb_c, "b_noconf": sb_n,
            })
    return results


def pf_of(s):
    return None if s is None else (99.0 if s["pf"] == float("inf") else s["pf"])


def is_candidate(r, min_pf=1.4, min_n=30):
    pa, pb = pf_of(r["a_conf"]), pf_of(r["b_conf"])
    if pa is None or pb is None:
        return False
    return pa >= min_pf and pb >= min_pf and r["a_conf"]["n"] >= min_n and r["b_conf"]["n"] >= min_n


def asymmetric_filter_candidates(results, min_pf=1.8, min_n=150, max_noconf_pf=1.1):
    """No exige mejora mutua -- una señal B usada como FILTRO/CONTEXTO de A (A solo se toma si B
    tambien disparo cerca), aunque B por si sola no mejore. Mas comun en la practica que la
    confluencia simetrica. Umbral mas estricto en n (150, no 30) porque al no exigir el lado B
    el espacio de busqueda efectivo es 2x -- mismo n_tests reportado pero doble de hipotesis reales."""
    out = []
    for r in results:
        for side, other in (("a", "b"), ("b", "a")):
            sc, sn = r[f"{side}_conf"], r[f"{side}_noconf"]
            pc, pn = pf_of(sc), pf_of(sn)
            if pc is None or sc["n"] < min_n:
                continue
            if pc >= min_pf and (pn is None or pn <= max_noconf_pf):
                out.append({"signal": r[side], "filter": r[other], "direction": r["direction"],
                           "level": "barra" if "window_bars" in r else "dia",
                           "n_conf": sc["n"], "pf_conf": pc, "pf_noconf": pn})
    out.sort(key=lambda x: -x["pf_conf"])
    return out


def _s(x):
    return f"{x:.2f}" if x is not None else "n/a"


def row_str(r):
    pa_c, pa_n = pf_of(r["a_conf"]), pf_of(r["a_noconf"])
    pb_c, pb_n = pf_of(r["b_conf"]), pf_of(r["b_noconf"])
    return (f"{r['a']:<26} x {r['b']:<26}  overlap_dias={r['overlap_days']:>5}  "
            f"{r['a']}: PF {_s(pa_n)}->{_s(pa_c)} (n={r['a_conf']['n']})   "
            f"{r['b']}: PF {_s(pb_n)}->{_s(pb_c)} (n={r['b_conf']['n']})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()

    print("Cargando barras 1-min 2016-2026...")
    days = load_days(range(2016, 2027))
    print(f"{len(days)} dias. Precomputando MACD/BB/Stoch/ADX...")
    attach_ext_indicators(days)
    print("Corriendo los 21 sistemas intradia (18 previos + TD9S + 7 nuevos)...\n")
    pool = build_all_intraday(days)
    for name, v in pool.items():
        print(f"  {name:<28} dir={v['dir']:<5} n={len(v['trades'])}")

    day_results = []
    for direction in ("long", "short"):
        rs = confluence_pairs(pool, direction)
        day_results.extend(rs)
        print(f"\n=== Confluencia por DIA (NO causal -- incluye confirmacion futura del mismo dia, "
              f"solo diagnostico exploratorio) -- direccion {direction.upper()} ({len(rs)} pares) ===")
        for r in sorted(rs, key=lambda r: -(pf_of(r["a_conf"]) + pf_of(r["b_conf"]))):
            print("  " + row_str(r))

    bar_results = []
    for direction in ("long", "short"):
        rs = confluence_pairs_bar(pool, direction, window=10)
        bar_results.extend(rs)
        print(f"\n=== Confluencia por BARRA CAUSAL (confirmador en los ultimos 10 min, nunca en el "
              f"futuro) -- direccion {direction.upper()} ({len(rs)} pares con n_conf>=10) ===")
        for r in sorted(rs, key=lambda r: -(pf_of(r["a_conf"]) + pf_of(r["b_conf"]))):
            print("  " + row_str(r))

    # Los "candidatos" y el filtro asimetrico SOLO se evaluan sobre bar_results (causal) -- el
    # nivel por dia (day_results) no es causal (ver aviso arriba) y NO se usa para declarar
    # ningun hallazgo, solo se imprime como contexto exploratorio.
    n_tests = len(day_results) + len(bar_results)
    candidates = [r for r in bar_results if is_candidate(r)]
    print(f"\n{'='*90}\nTotal de pares probados: {n_tests} (dia={len(day_results)}, NO causal, solo "
          f"exploratorio + barra={len(bar_results)}, CAUSAL -- los candidatos solo salen de barra)")
    print(f"Candidatos (PF>=1.4 en AMBOS lados, causal, n>=30 cada uno): {len(candidates)}")
    for r in candidates:
        print("  ** " + row_str(r))
    if not candidates:
        print("  Ninguno sobrevive el umbral conjunto -- ver seccion de 'casi' mas abajo para matices.")
        near = sorted([r for r in bar_results if pf_of(r["a_conf"]) and pf_of(r["b_conf"])],
                      key=lambda r: -(pf_of(r["a_conf"]) + pf_of(r["b_conf"])))[:8]
        print("\n  Top 8 causales por PF combinado (referencia, NO candidatos):")
        for r in near:
            print("    " + row_str(r))

    asym = asymmetric_filter_candidates(bar_results)
    print(f"\n{'='*90}\nFILTRO ASIMETRICO CAUSAL (B confirmando A en los ultimos 10 min, sin exigir "
          f"mejora mutua; PF>=1.8, n>=150, base<=1.1): {len(asym)} hallazgos")
    for x in asym[:15]:
        print(f"  {x['signal']:<26} SOLO cuando {x['filter']:<26} confirmo en los ultimos 10 min: "
              f"PF {_s(x['pf_noconf'])}->{x['pf_conf']:.2f}  n={x['n_conf']}")

    if a.json:
        Path(a.json).write_text(json.dumps({"pairs_by_day_noncausal": day_results,
                                            "pairs_by_bar_causal": bar_results, "asymmetric": asym},
                                           ensure_ascii=False, default=str, indent=2))
        print(f"\n[guardado] {a.json}")


if __name__ == "__main__":
    main()
