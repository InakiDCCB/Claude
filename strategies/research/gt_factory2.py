"""GT Lote 1b — familias DIARIAS no exploradas en Lote 1 (2026-07-03).

Features nuevos desde el OHLCV diario de ayer (causales): posición del cierre en el rango
(clr), ratio de volumen vs avg20, compresión de rango (NR7/inside), rango extremo (WR),
proximidad a mínimos 20/50d, e interacciones con RSI2 diario. Retorno o2c de HOY (idéntico
al Lote 1 — operable intradía, sin overnight). Protocolo y gates ORIGINALES de gt_factory:
  TRAIN <2017 (n>=80, mean>0, t>=1.5) · VALID 2017-2022 (n>=40) + BH-FDR q=0.10 · OOS >=2023 LOCKED.
Registro -> data/gt_batch1b_registry.json.
"""
import json
from pathlib import Path

from gt_factory import (DATA, COST, FDR_Q, TRAIN_END, VALID_END,
                        load_daily, rsi, perf, p_one_sided)


def build_rows():
    qqq = load_daily("qqq")
    dates = sorted(qqq)
    closes = [qqq[d]["close"] for d in dates]
    vols = [qqq[d]["volume"] for d in dates]
    rsi2 = rsi(closes, 2)
    rngs = [qqq[d]["high"] - qqq[d]["low"] for d in dates]
    rows = []
    for i in range(210, len(dates)):
        d, dp = dates[i], dates[i - 1]
        o, c = qqq[d]["open"], qqq[d]["close"]
        y = qqq[dp]                                   # barra de AYER (causal)
        cp = y["close"]
        rng = y["high"] - y["low"]
        clr = (cp - y["low"]) / rng if rng > 0 else 0.5
        red = cp < y["open"]
        ret1 = cp / closes[i - 2] - 1
        v_avg20 = sum(vols[i - 21:i - 1]) / 20
        volx = y["volume"] / v_avg20 if v_avg20 > 0 else None
        nr7 = rng <= min(rngs[i - 7:i])
        nr4 = rng <= min(rngs[i - 4:i])
        inside = y["high"] < qqq[dates[i - 2]]["high"] and y["low"] > qqq[dates[i - 2]]["low"]
        wr_hist = sorted(rngs[i - 101:i - 1])
        wr90 = rng >= wr_hist[int(0.9 * len(wr_hist))] if wr_hist else False
        lo20 = min(closes[i - 21:i - 1])
        lo50 = min(closes[i - 51:i - 1])
        rows.append({
            "date": d, "o2c": c / o - 1,
            "clr": clr, "red": red, "ret1": ret1, "volx": volx,
            "nr7": nr7, "nr4": nr4, "inside": inside, "wr90": wr90,
            "near_lo20": cp <= lo20 * 1.01, "near_lo50": cp <= lo50 * 1.02,
            "rsi2": rsi2[i - 1],
        })
    return rows


def hypotheses():
    H = []
    def add(name, fam, dir_, fn):
        H.append({"name": name, "family": fam, "dir": dir_, "fn": fn})
    # A · posición del cierre en el rango (capitulación / euforia)
    add("clr<0.2", "closepos", "long", lambda r: r["clr"] < 0.2)
    add("clr<0.1", "closepos", "long", lambda r: r["clr"] < 0.1)
    add("clr<0.2_red", "closepos", "long", lambda r: r["clr"] < 0.2 and r["red"])
    add("clr<0.2_ret1<-1%", "closepos", "long", lambda r: r["clr"] < 0.2 and r["ret1"] < -0.01)
    add("clr>0.9_sh", "closepos", "short", lambda r: r["clr"] > 0.9)
    # B · volumen (capitulación con volumen / dry-up)
    add("volx>2_dn", "volume", "long", lambda r: r["volx"] and r["volx"] > 2 and r["ret1"] < 0)
    add("volx>1.5_dn", "volume", "long", lambda r: r["volx"] and r["volx"] > 1.5 and r["ret1"] < 0)
    add("volx>2_clr<0.3", "volume", "long", lambda r: r["volx"] and r["volx"] > 2 and r["clr"] < 0.3)
    add("volx<0.6", "volume", "long", lambda r: r["volx"] and r["volx"] < 0.6)
    add("volx>2_up_sh", "volume", "short", lambda r: r["volx"] and r["volx"] > 2 and r["ret1"] > 0)
    # C · compresión de rango
    add("nr7", "compress", "long", lambda r: r["nr7"])
    add("nr7_sh", "compress", "short", lambda r: r["nr7"])
    add("nr4_inside", "compress", "long", lambda r: r["nr4"] and r["inside"])
    add("inside", "compress", "long", lambda r: r["inside"])
    # D · rango extremo (wide-range reversal)
    add("wr90_red", "widerange", "long", lambda r: r["wr90"] and r["red"])
    add("wr90_red_clr<0.25", "widerange", "long", lambda r: r["wr90"] and r["red"] and r["clr"] < 0.25)
    # E · proximidad a mínimos
    add("near_lo20", "nearlow", "long", lambda r: r["near_lo20"])
    add("near_lo50", "nearlow", "long", lambda r: r["near_lo50"])
    # F · interacciones con RSI2 diario (features nuevos × edge conocido)
    add("rsi2<10_volx>1.5", "interact", "long",
        lambda r: r["rsi2"] is not None and r["rsi2"] < 10 and r["volx"] and r["volx"] > 1.5)
    add("rsi2<10_clr<0.3", "interact", "long",
        lambda r: r["rsi2"] is not None and r["rsi2"] < 10 and r["clr"] < 0.3)
    return H


def main():
    rows = build_rows()
    tr = [r for r in rows if r["date"] < TRAIN_END]
    va = [r for r in rows if TRAIN_END <= r["date"] < VALID_END]
    oo = [r for r in rows if r["date"] >= VALID_END]
    print(f"Lote 1b · filas {len(rows)} | TRAIN {len(tr)} | VALID {len(va)} | OOS(locked) {len(oo)}\n")

    H = hypotheses()
    registry, stage1 = [], []
    for h in H:
        def rets_of(sub, h=h):
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
        s_oo = perf(rf(oo))
        rec["oos"] = s_oo
        v = rec["valid"]
        print(f"{rec['name']:<24}{rec['dir']:<7} VALID n={v['n']} {v['mean_bps']:+.1f}bp t={v['t']} "
              f"pf={v['pf']}  ·  OOS " + (f"n={s_oo['n']} {s_oo['mean_bps']:+.1f}bp t={s_oo['t']} "
              f"win={s_oo['win']}% pf={s_oo['pf']}" if s_oo else "sin señales"))
    (DATA / "gt_batch1b_registry.json").write_text(json.dumps(registry, indent=1, default=str))
    print(f"\nRegistro ({len(registry)}) -> data/gt_batch1b_registry.json")


if __name__ == "__main__":
    main()
