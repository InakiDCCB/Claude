"""GT-1 + GT-2 — Fábrica de señales Golden Ticket + protocolo anti-overfit (2026-07-03).

Lote 1: hipótesis DIARIAS sobre QQQ operables intradía (retorno open→close — sin overnight,
compatible con el loop). Features externas (SPY/TLT/VIX) SOLO como contexto (decisión usuario:
QQQ único operable). Costos: 3 bps por round-trip (spread QQQ ~1c + margen slippage).

GT-2 (el corazón — sin esto la búsqueda fabrica oro falso):
  TRAIN  <2017         : filtro suave (n>=80, mean>0, t>=1.5)
  VALID  2017-2022     : p-value unilateral + corrección Benjamini-Hochberg FDR q=0.10 sobre TODO el lote
  OOS    >=2023 LOCKED : solo los sobrevivientes FDR lo tocan, UNA vez, reportado con veredicto
  Registro COMPLETO (también fallos) -> data/gt_batch1_registry.json (anti-hallazgos automáticos).
La promoción a shadow/live sigue el pipeline de siempre (listón PF>=1.5-1.65 OOS + decisión usuario).
"""
import csv
import json
import math
from pathlib import Path

DATA = Path(__file__).parent / "data"
COST = 0.0003          # 3 bps round-trip
FDR_Q = 0.10
TRAIN_END, VALID_END = "2017-01-01", "2023-01-01"


def load_daily(name):
    p = DATA / f"gt_daily_{name}.csv"
    out = {}
    with p.open() as f:
        for r in csv.DictReader(f):
            out[r["date"]] = {k: float(r[k]) for k in ("open", "high", "low", "close", "volume")}
    return out


def pct_rank(window, x):
    if not window:
        return None
    return sum(1 for w in window if w <= x) / len(window)


def rsi(closes, n):
    """RSI Wilder sobre la lista completa; devuelve lista alineada."""
    out = [None] * len(closes)
    if len(closes) < n + 1:
        return out
    g = l = 0.0
    for k in range(1, n + 1):
        d = closes[k] - closes[k - 1]
        g += max(d, 0); l += max(-d, 0)
    ag, al = g / n, l / n
    out[n] = 100 - 100 / (1 + (ag / al if al else 1e9))
    for k in range(n + 1, len(closes)):
        d = closes[k] - closes[k - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[k] = 100 - 100 / (1 + (ag / al if al else 1e9))
    return out


def build_rows():
    qqq, spy, tlt, vix = (load_daily(n) for n in ("qqq", "spy", "tlt", "vix"))
    dates = sorted(qqq)
    closes = [qqq[d]["close"] for d in dates]
    rsi2, rsi14 = rsi(closes, 2), rsi(closes, 14)
    rows = []
    for i in range(210, len(dates)):
        d, dp = dates[i], dates[i - 1]
        o, c, cp = qqq[d]["open"], qqq[d]["close"], qqq[dp]["close"]
        hist = closes[:i]                       # closes hasta i-1 (causal)
        ret1 = cp / closes[i - 2] - 1
        ret5 = cp / closes[i - 6] - 1
        consec_dn = consec_up = 0
        for k in range(i - 1, 0, -1):
            if closes[k] < closes[k - 1]:
                if consec_up: break
                consec_dn += 1
            elif closes[k] > closes[k - 1]:
                if consec_dn: break
                consec_up += 1
            else:
                break
        ma20 = sum(hist[-20:]) / 20
        hi20, lo20 = max(hist[-20:]), min(hist[-20:])
        hi50 = max(hist[-50:])
        rets10 = [hist[-k] / hist[-k - 1] - 1 for k in range(1, 11)]
        rvol10 = (sum(r * r for r in rets10) / 10) ** 0.5
        # externos (features de contexto, con fecha del cierre previo)
        vx = vix.get(dp, {}).get("close"); vxp = None
        if vx is not None:
            win = [vix[x]["close"] for x in dates[max(0, i - 253):i] if x in vix]
            vxp = pct_rank(win, vx)
        vx2 = vix.get(dates[i - 2], {}).get("close")
        vix_chg = (vx / vx2 - 1) if (vx and vx2) else None
        sq = None
        if dp in spy and dates[i - 6] in spy:
            sq = ret5 - (spy[dp]["close"] / spy[dates[i - 6]]["close"] - 1)
        tl = None
        if dp in tlt and dates[i - 6] in tlt:
            tl = tlt[dp]["close"] / tlt[dates[i - 6]]["close"] - 1
        y, m, dd = d.split("-")
        import datetime as _dt
        dow = _dt.date(int(y), int(m), int(dd)).weekday()
        tom = (i + 3 < len(dates) and dates[i + 3][5:7] != m) or (dates[max(i - 3, 0)][5:7] != m)
        rows.append({
            "date": d, "o2c": c / o - 1, "gap": o / cp - 1,
            "ret1": ret1, "ret5": ret5, "consec_dn": consec_dn, "consec_up": consec_up,
            "rsi2": rsi2[i - 1], "rsi14": rsi14[i - 1],
            "dist_ma20": cp / ma20 - 1, "brk_hi20": cp >= hi20, "brk_hi50": cp >= hi50,
            "brk_lo20": cp <= lo20, "rvol10": rvol10,
            "vix": vx, "vix_pct": vxp, "vix_chg": vix_chg, "spyqqq5": sq, "tlt5": tl,
            "dow": dow, "tom": tom,
        })
    return rows


def hypotheses():
    H = []
    def add(name, fam, dir_, fn):
        H.append({"name": name, "family": fam, "dir": dir_, "fn": fn})
    # A · mean reversion (long)
    for x in (0.005, 0.01, 0.015, 0.02):
        add(f"mr_ret1<-{x*100:g}%", "meanrev", "long", lambda r, x=x: r["ret1"] < -x)
    for k in (2, 3, 4):
        add(f"mr_{k}down", "meanrev", "long", lambda r, k=k: r["consec_dn"] >= k)
    for t in (5, 10, 15, 25):
        add(f"mr_rsi2<{t}", "meanrev", "long", lambda r, t=t: r["rsi2"] is not None and r["rsi2"] < t)
    for x in (0.003, 0.005, 0.01):
        add(f"mr_gapdn<-{x*100:g}%", "meanrev", "long", lambda r, x=x: r["gap"] < -x)
    for x in (0.02, 0.03):
        add(f"mr_ma20<-{x*100:g}%", "meanrev", "long", lambda r, x=x: r["dist_ma20"] < -x)
    # B · momentum (long)
    add("mo_hi20", "momentum", "long", lambda r: r["brk_hi20"])
    add("mo_hi50", "momentum", "long", lambda r: r["brk_hi50"])
    for x in (0.01, 0.02):
        add(f"mo_ret5>{x*100:g}%", "momentum", "long", lambda r, x=x: r["ret5"] > x)
    for x in (0.003, 0.005):
        add(f"mo_gapup>{x*100:g}%", "momentum", "long", lambda r, x=x: r["gap"] > x)
    # C · estacionalidad (long)
    for w, nm in ((0, "lun"), (1, "mar"), (2, "mie"), (3, "jue"), (4, "vie")):
        add(f"se_{nm}", "season", "long", lambda r, w=w: r["dow"] == w)
    add("se_tom", "season", "long", lambda r: r["tom"])
    # D · VIX-condicional (mean-rev × régimen de vol)
    base = {"ret1<-1%": lambda r: r["ret1"] < -0.01,
            "rsi2<10": lambda r: r["rsi2"] is not None and r["rsi2"] < 10,
            "3down": lambda r: r["consec_dn"] >= 3,
            "gapdn<-0.5%": lambda r: r["gap"] < -0.005}
    for bn, bf in base.items():
        add(f"vx_{bn}_vixhi", "vixcond", "long",
            lambda r, bf=bf: bf(r) and r["vix_pct"] is not None and r["vix_pct"] > 0.67)
        add(f"vx_{bn}_vixlo", "vixcond", "long",
            lambda r, bf=bf: bf(r) and r["vix_pct"] is not None and r["vix_pct"] < 0.33)
        add(f"vx_{bn}_vix>25", "vixcond", "long",
            lambda r, bf=bf: bf(r) and r["vix"] is not None and r["vix"] > 25)
    # E · cross-asset
    add("cx_qqq_lag_spy", "cross", "long", lambda r: r["spyqqq5"] is not None and r["spyqqq5"] < -0.01)
    add("cx_qqq_lead_spy", "cross", "long", lambda r: r["spyqqq5"] is not None and r["spyqqq5"] > 0.01)
    add("cx_tlt_up_ret1dn", "cross", "long",
        lambda r: r["tlt5"] is not None and r["tlt5"] > 0.01 and r["ret1"] < -0.01)
    add("cx_vixspike_ret1dn", "cross", "long",
        lambda r: r["vix_chg"] is not None and r["vix_chg"] > 0.10 and r["ret1"] < -0.01)
    # F · shorts (espejo selectivo)
    for x in (0.01, 0.015):
        add(f"sh_ret1>+{x*100:g}%", "short", "short", lambda r, x=x: r["ret1"] > x)
    for t in (90, 95):
        add(f"sh_rsi2>{t}", "short", "short", lambda r, t=t: r["rsi2"] is not None and r["rsi2"] > t)
    add("sh_gapup>1%", "short", "short", lambda r: r["gap"] > 0.01)
    add("sh_lo20", "short", "short", lambda r: r["brk_lo20"])
    add(f"sh_{3}up", "short", "short", lambda r: r["consec_up"] >= 3)
    return H


def perf(rets):
    n = len(rets)
    if n == 0:
        return None
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / max(n - 1, 1)
    sd = var ** 0.5
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    gw = sum(r for r in rets if r > 0)
    gl = -sum(r for r in rets if r <= 0)
    return {"n": n, "mean_bps": round(mean * 1e4, 2), "t": round(t, 2),
            "win": round(100 * sum(1 for r in rets if r > 0) / n, 1),
            "pf": round(gw / gl, 2) if gl > 0 else float("inf"),
            "tot_pct": round(100 * mean * n, 1)}


def p_one_sided(t):
    return 0.5 * (1 - math.erf(t / math.sqrt(2)))


def main():
    rows = build_rows()
    print(f"Filas evaluables: {len(rows)} ({rows[0]['date']} -> {rows[-1]['date']})")
    tr = [r for r in rows if r["date"] < TRAIN_END]
    va = [r for r in rows if TRAIN_END <= r["date"] < VALID_END]
    oo = [r for r in rows if r["date"] >= VALID_END]
    print(f"TRAIN {len(tr)} | VALID {len(va)} | OOS(locked) {len(oo)}  · costo {COST*1e4:g} bps\n")

    H = hypotheses()
    registry = []
    stage1 = []
    for h in H:
        def rets_of(sub, h=h):     # h ligado por default-arg (late-binding bug si no)
            out = []
            for r in sub:
                try:
                    if h["fn"](r):
                        out.append((r["o2c"] if h["dir"] == "long" else -r["o2c"]) - COST)
                except TypeError:
                    pass
            return out
        s_tr = perf(rets_of(tr))
        rec = {"name": h["name"], "family": h["family"], "dir": h["dir"], "train": s_tr}
        if s_tr and s_tr["n"] >= 80 and s_tr["mean_bps"] > 0 and s_tr["t"] >= 1.5:
            s_va = perf(rets_of(va))
            rec["valid"] = s_va
            if s_va and s_va["n"] >= 40:
                rec["p_valid"] = round(p_one_sided(s_va["t"]), 4)
                stage1.append((rec, rets_of))
            else:
                rec["stage"] = "descartada_valid_n"
        else:
            rec["stage"] = "descartada_train"
        registry.append(rec)

    # Benjamini-Hochberg FDR sobre los p-values de VALID
    stage1.sort(key=lambda x: x[0]["p_valid"])
    m = len(stage1)
    survivors = []
    for rank, (rec, rf) in enumerate(stage1, 1):
        if rec["p_valid"] <= FDR_Q * rank / m:
            survivors = stage1[:rank]      # BH: todos hasta el mayor rank que cumple
    for rec, _ in stage1:
        rec["stage"] = "rechazada_fdr"
    for rec, _ in survivors:
        rec["stage"] = "SOBREVIVE_FDR"

    print(f"Lote: {len(H)} hipótesis | pasan train: {m} | sobreviven FDR(q={FDR_Q}): {len(survivors)}\n")
    if survivors:
        print(f"{'señal':<24}{'dir':<7}{'VALID n/mean/t/pf':<26}{'OOS n/mean/t/pf':<26}veredicto")
        for rec, rf in survivors:
            s_oo = perf(rf(oo))
            rec["oos"] = s_oo
            v = rec["valid"]
            vs = f"{v['n']}/{v['mean_bps']:+.1f}bp/t{v['t']}/pf{v['pf']}"
            if s_oo:
                os_ = f"{s_oo['n']}/{s_oo['mean_bps']:+.1f}bp/t{s_oo['t']}/pf{s_oo['pf']}"
                ver = ("CANDIDATA (gate usuario)" if s_oo["mean_bps"] > 0 and s_oo["pf"] >= 1.1
                       else "no generaliza OOS")
            else:
                os_, ver = "sin señales", "sin datos OOS"
            print(f"{rec['name']:<24}{rec['dir']:<7}{vs:<26}{os_:<26}{ver}")
    (DATA / "gt_batch1_registry.json").write_text(json.dumps(registry, indent=1, default=str))
    print(f"\nRegistro completo ({len(registry)} hipótesis, incl. fallos) -> data/gt_batch1_registry.json")


if __name__ == "__main__":
    main()
