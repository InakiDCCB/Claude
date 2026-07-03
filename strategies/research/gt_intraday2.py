"""GT Lote 2b — intradía CONDICIONADO a contexto diario (2026-07-03).

Lección del Lote 2 (42/42 muertas en TRAIN): los triggers intradía naive (reacciones k-min,
volume climax, hora) NO tienen edge incondicional. Lote 2b cruza esos mismos triggers con el
régimen DIARIO (sobreventa/gap) — donde el Lote 1 sí encontró edge (gt_rsi2d, gt_3down).

Mismo protocolo GT-2 (TRAIN <2021 / VALID 2021-2023 + BH-FDR q=0.10 / OOS >=2024 bloqueado).
Lote nuevo => FDR fresco sobre TODO este lote. Registro -> data/gt_batch2b_registry.json.
"""
import csv
import json
import math
from pathlib import Path

from gt_intraday import (DATA, COST, FDR_Q, TRAIN_END, VALID_END,
                         load_days, idx_at, ret_entry_exit, react, vclimax,
                         perf, p_one_sided)


# ── Contexto diario causal (features al cierre de AYER) ─────────────────────

def daily_context():
    rows = {}
    with (DATA / "gt_daily_qqq.csv").open() as f:
        data = list(csv.DictReader(f))
    closes = [float(r["close"]) for r in data]
    dates = [r["date"] for r in data]
    opens = {r["date"]: float(r["open"]) for r in data}
    # RSI2 Wilder
    rsi2 = [None] * len(closes)
    if len(closes) > 3:
        g = l = 0.0
        for k in (1, 2):
            d = closes[k] - closes[k - 1]
            g += max(d, 0); l += max(-d, 0)
        ag, al = g / 2, l / 2
        rsi2[2] = 100 - 100 / (1 + (ag / al if al else 1e9))
        for k in range(3, len(closes)):
            d = closes[k] - closes[k - 1]
            ag = (ag + max(d, 0)) / 2
            al = (al + max(-d, 0)) / 2
            rsi2[k] = 100 - 100 / (1 + (ag / al if al else 1e9))
    for i in range(5, len(dates)):
        consec_dn = 0
        for k in range(i - 1, 0, -1):
            if closes[k] < closes[k - 1]:
                consec_dn += 1
            else:
                break
        rows[dates[i]] = {"rsi2d": rsi2[i - 1], "consec_dn": consec_dn,
                          "prev_close": closes[i - 1], "open": opens[dates[i]],
                          "ret1": closes[i - 1] / closes[i - 2] - 1}
    return rows


# ── Triggers intradía adicionales ────────────────────────────────────────────

def open_drop(x):
    """A las 10:00: precio x% bajo el open del día."""
    def fn(day):
        i = idx_at(day, 30)
        if i is None or day["m"][i] < 20:
            return None
        return i if day["c"][i] / day["o"][0] - 1 <= -x else None
    return fn


def hold_above_open(minute):
    """A `minute`: el precio sigue >= open del día (gap-and-go hold)."""
    def fn(day):
        i = idx_at(day, minute)
        if i is None or day["m"][i] < minute - 10:
            return None
        return i if day["c"][i] >= day["o"][0] else None
    return fn


def pm_down(minute, x):
    """A `minute`: día abajo >= x% desde el open."""
    def fn(day):
        i = idx_at(day, minute)
        if i is None or day["m"][i] < minute - 10:
            return None
        return i if day["c"][i] / day["o"][0] - 1 <= -x else None
    return fn


# ── Hipótesis: contexto diario × trigger intradía ───────────────────────────

CTX = {
    "rsi2d<5":  lambda c: c["rsi2d"] is not None and c["rsi2d"] < 5,
    "rsi2d<10": lambda c: c["rsi2d"] is not None and c["rsi2d"] < 10,
    "2down":    lambda c: c["consec_dn"] >= 2,
    "3down":    lambda c: c["consec_dn"] >= 3,
    "gapdn":    lambda c: c["open"] / c["prev_close"] - 1 <= -0.003,
    "gapup":    lambda c: c["open"] / c["prev_close"] - 1 >= 0.003,
}


def hypotheses():
    H = []
    def add(name, fam, dir_, hold, ctx, fn):
        H.append({"name": name, "family": fam, "dir": dir_, "hold": hold,
                  "ctx": ctx, "fn": fn})
    # CR · dip intradía en régimen de sobreventa diaria
    for cn in ("rsi2d<10", "2down", "3down"):
        for k, x in ((30, 0.005), (15, 0.005)):
            for hold, hn in ((60, "h60"), (None, "hEOD")):
                add(f"cr_{cn}_dip{k}m_{hn}", "ctx_reaction", "long", hold, cn,
                    react(k, x, "long"))
        add(f"cr_{cn}_opendrop_hEOD", "ctx_reaction", "long", None, cn, open_drop(0.003))
    # CV · volume climax en sobreventa diaria
    for cn in ("rsi2d<10", "2down"):
        for hold, hn in ((60, "h60"), (None, "hEOD")):
            add(f"cv_{cn}_vcx2.5_{hn}", "ctx_volume", "long", hold, cn, vclimax(2.5))
    # GG · gap-and-go (contexto momentum diario)
    for cn in ("gapup",):
        for minute, mn in ((30, "1000"), (60, "1030")):
            add(f"gg_{cn}_hold{mn}_hEOD", "gap_go", "long", None, cn,
                hold_above_open(minute))
    # GF2 · gap-down: dip adicional post-open (NO reclaim: eso es gapf_v3)
    for cn in ("gapdn",):
        add(f"gf2_{cn}_opendrop_hEOD", "gap2", "long", None, cn, open_drop(0.003))
        add(f"gf2_{cn}_dip30_hEOD", "gap2", "long", None, cn, react(30, 0.005, "long"))
    # PM · tarde abajo en régimen de sobreventa (reversión al cierre)
    for cn in ("rsi2d<10", "2down", "3down"):
        for minute, mn in ((270, "1400"), (330, "1500")):
            add(f"pm_{cn}_dn{mn}_hEOD", "ctx_pm", "long", None, cn, pm_down(minute, 0.005))
    return H


def main():
    days = load_days()
    ctx = daily_context()
    dates = [d for d in days if d in ctx]
    print(f"Días RTH con contexto diario: {len(dates)} ({dates[0]} -> {dates[-1]})")
    splits = {"train": [d for d in dates if d < TRAIN_END],
              "valid": [d for d in dates if TRAIN_END <= d < VALID_END],
              "oos":   [d for d in dates if d >= VALID_END]}
    print(f"TRAIN {len(splits['train'])} | VALID {len(splits['valid'])} | "
          f"OOS(locked) {len(splits['oos'])}  · costo {COST*1e4:g} bps\n")

    H = hypotheses()
    registry, stage1 = [], []
    for h in H:
        cfn = CTX[h["ctx"]]
        def rets_of(dlist, h=h, cfn=cfn):
            out = []
            for d in dlist:
                if not cfn(ctx[d]):
                    continue
                day = days[d]
                if len(day["m"]) < 100:
                    continue
                i = h["fn"](day)
                if i is None:
                    continue
                r = ret_entry_exit(day, i, h["hold"], h["dir"])
                if r is not None:
                    out.append(r)
            return out
        s_tr = perf(rets_of(splits["train"]))
        rec = {"name": h["name"], "family": h["family"], "dir": h["dir"],
               "hold": h["hold"], "ctx": h["ctx"], "train": s_tr}
        if s_tr and s_tr["n"] >= 80 and s_tr["mean_bps"] > 0 and s_tr["t"] >= 1.5:
            s_va = perf(rets_of(splits["valid"]))
            rec["valid"] = s_va
            if s_va and s_va["n"] >= 40:
                rec["p_valid"] = round(p_one_sided(s_va["t"]), 4)
                stage1.append((rec, rets_of))
            else:
                rec["stage"] = "descartada_valid_n"
        else:
            rec["stage"] = "descartada_train"
        registry.append(rec)

    stage1.sort(key=lambda x: x[0]["p_valid"])
    m = len(stage1)
    survivors = []
    for rank, (rec, rf) in enumerate(stage1, 1):
        if rec["p_valid"] <= FDR_Q * rank / m:
            survivors = stage1[:rank]
    for rec, _ in stage1:
        rec["stage"] = "rechazada_fdr"
    for rec, _ in survivors:
        rec["stage"] = "SOBREVIVE_FDR"

    print(f"Lote: {len(H)} hipótesis | pasan train: {m} | sobreviven FDR(q={FDR_Q}): {len(survivors)}\n")
    if survivors:
        print(f"{'señal':<30}{'VALID n/mean/t/pf':<28}{'OOS n/mean/t/pf':<28}veredicto")
        for rec, rf in survivors:
            s_oo = perf(rf(splits["oos"]))
            rec["oos"] = s_oo
            v = rec["valid"]
            vs = f"{v['n']}/{v['mean_bps']:+.1f}bp/t{v['t']}/pf{v['pf']}"
            if s_oo:
                os_ = f"{s_oo['n']}/{s_oo['mean_bps']:+.1f}bp/t{s_oo['t']}/pf{s_oo['pf']}"
                ver = ("CANDIDATA (gate usuario)" if s_oo["mean_bps"] > 0 and s_oo["pf"] >= 1.5
                       else "positiva OOS (< listón)" if s_oo["mean_bps"] > 0
                       else "no generaliza OOS")
            else:
                os_, ver = "sin señales", "sin datos OOS"
            print(f"{rec['name']:<30}{vs:<28}{os_:<28}{ver}")
    (DATA / "gt_batch2b_registry.json").write_text(json.dumps(registry, indent=1, default=str))
    print(f"\nRegistro completo ({len(registry)} hipótesis) -> data/gt_batch2b_registry.json")


if __name__ == "__main__":
    main()
