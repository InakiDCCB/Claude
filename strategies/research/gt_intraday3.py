"""GT Lote 2c — PM-reversión en régimen sobrevendido, lote enfocado (2026-07-03).

El Lote 2b (exploratorio, solo TRAIN visto) señaló la familia: día en sobreventa DIARIA que
además cae >=x% desde el open por la tarde -> comprar la debilidad hasta el cierre. Este lote
la somete al protocolo con variantes amplias y gates PRE-COMPROMETIDOS proporcionales a la
muestra intradía (TRAIN 5y vs 17y del lote diario):
  TRAIN  <2021        : n>=40, mean>0, t>=1.5
  VALID  2021-2023    : n>=25, p unilateral + BH-FDR q=0.10 sobre TODO el lote
  OOS    >=2024 LOCKED: una vez, listón PF>=1.5
Registro -> data/gt_batch2c_registry.json. VALID/OOS no fueron consultados en 2b (limpios).
"""
import json
from pathlib import Path

from gt_intraday import (DATA, COST, FDR_Q, TRAIN_END, VALID_END,
                         load_days, idx_at, ret_entry_exit, perf, p_one_sided)
from gt_intraday2 import daily_context, pm_down

TRAIN_N, VALID_N = 40, 25

CTX = {
    "rsi2d<10":   lambda c: c["rsi2d"] is not None and c["rsi2d"] < 10,
    "rsi2d<15":   lambda c: c["rsi2d"] is not None and c["rsi2d"] < 15,
    "2down":      lambda c: c["consec_dn"] >= 2,
    "2dn|rsi<10": lambda c: c["consec_dn"] >= 2 or (c["rsi2d"] is not None and c["rsi2d"] < 10),
}


def hypotheses():
    H = []
    for cn in CTX:
        for minute, mn in ((240, "1330"), (270, "1400"), (300, "1430")):
            for thr in (0.003, 0.005):
                H.append({"name": f"pmr_{cn}_{mn}_dn{thr*100:g}%", "family": "pm_oversold",
                          "dir": "long", "hold": None, "ctx": cn,
                          "fn": pm_down(minute, thr)})
    return H


def main():
    days = load_days()
    ctx = daily_context()
    dates = [d for d in days if d in ctx]
    splits = {"train": [d for d in dates if d < TRAIN_END],
              "valid": [d for d in dates if TRAIN_END <= d < VALID_END],
              "oos":   [d for d in dates if d >= VALID_END]}
    print(f"Lote 2c · TRAIN {len(splits['train'])} | VALID {len(splits['valid'])} | "
          f"OOS(locked) {len(splits['oos'])} · gates n>={TRAIN_N}/{VALID_N}\n")

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
        rec = {"name": h["name"], "family": h["family"], "ctx": h["ctx"], "train": s_tr}
        if s_tr and s_tr["n"] >= TRAIN_N and s_tr["mean_bps"] > 0 and s_tr["t"] >= 1.5:
            s_va = perf(rets_of(splits["valid"]))
            rec["valid"] = s_va
            if s_va and s_va["n"] >= VALID_N:
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

    print(f"Lote: {len(H)} | pasan train: {m} | sobreviven FDR: {len(survivors)}\n")
    for rec, rf in survivors:
        s_oo = perf(rf(splits["oos"]))
        rec["oos"] = s_oo
        v = rec["valid"]
        print(f"{rec['name']:<30} VALID n={v['n']} {v['mean_bps']:+.1f}bp t={v['t']} pf={v['pf']}"
              f"  ·  OOS " + (f"n={s_oo['n']} {s_oo['mean_bps']:+.1f}bp t={s_oo['t']} "
              f"win={s_oo['win']}% pf={s_oo['pf']}" if s_oo else "sin señales"))
    (DATA / "gt_batch2c_registry.json").write_text(json.dumps(registry, indent=1, default=str))
    print(f"\nRegistro ({len(registry)}) -> data/gt_batch2c_registry.json")


if __name__ == "__main__":
    main()
