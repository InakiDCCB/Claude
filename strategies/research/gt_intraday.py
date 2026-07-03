"""GT Lote 2 — hipótesis INTRADÍA sobre 1-min QQQ (2026-07-03).

Familias plantilla (acordadas al cerrar Lote 1): reacciones k-min (mean reversion a shocks
de precio), microestructura de volumen (climax) y condicional-por-hora (drift/reversión PM).
Máx 1 señal/día/hipótesis (primer trigger) — retornos comparables al o2c del Lote 1.

Mismo protocolo GT-2 que gt_factory.py, splits adaptados al rango 2016->2026 del 1-min SIP:
  TRAIN  <2021         : filtro suave (n>=80, mean>0, t>=1.5)
  VALID  2021-2023     : p unilateral + Benjamini-Hochberg FDR q=0.10 sobre TODO el lote
  OOS    >=2024 LOCKED : solo sobrevivientes FDR, UNA vez
  Registro COMPLETO -> data/gt_batch2_registry.json (anti-hallazgos automáticos).
Costos 3 bps round-trip. Señales computables en batch /post-close (patrón smc_shadow.py).
Nota volumen: umbrales RELATIVOS (ratio vs avg 20 bloques del mismo feed) para tolerar
la diferencia SIP (backtest) vs IEX (loop en vivo).
"""
import csv
import datetime as dt
import gzip
import json
import math
from pathlib import Path

DATA = Path(__file__).parent / "data"
COST = 0.0003
FDR_Q = 0.10
TRAIN_END, VALID_END = "2021-01-01", "2024-01-01"
YEARS = range(2016, 2027)


# ── RTH / DST (regla US post-2007, sin tz externas) ─────────────────────────

def _nth_sunday(y, month, nth):
    d = dt.date(y, month, 1)
    first_sun = 1 + (6 - d.weekday()) % 7
    return dt.date(y, month, first_sun + 7 * (nth - 1))


def _utc_offset_hours(d):
    return 4 if _nth_sunday(d.year, 3, 2) <= d < _nth_sunday(d.year, 11, 1) else 5


def load_days():
    """{fecha_ET: {"m": [min desde 9:30], "o","h","l","c","v": listas}} solo RTH."""
    days = {}
    for y in YEARS:
        p = DATA / f"gt_qqq_1min_{y}.csv.gz"
        if not p.exists():
            continue
        with gzip.open(p, "rt") as f:
            for r in csv.reader(f):
                if r[0] == "t":
                    continue
                ts = dt.datetime.strptime(r[0], "%Y-%m-%dT%H:%M:%SZ")
                et = ts - dt.timedelta(hours=_utc_offset_hours(ts.date()))
                mins = (et.hour - 9) * 60 + et.minute - 30
                if not (0 <= mins < 390):
                    continue
                d = days.setdefault(et.date().isoformat(), {k: [] for k in "mohlcv"})
                d["m"].append(mins)
                d["o"].append(float(r[1])); d["h"].append(float(r[2]))
                d["l"].append(float(r[3])); d["c"].append(float(r[4]))
                d["v"].append(float(r[5]))
    return dict(sorted(days.items()))


def idx_at(day, minute):
    """Índice del último bar con m <= minute (None si ninguno)."""
    m = day["m"]
    lo, hi, best = 0, len(m) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if m[mid] <= minute:
            best = mid; lo = mid + 1
        else:
            hi = mid - 1
    return best


def ret_entry_exit(day, sig_i, hold, dir_):
    """Entry = open del bar siguiente a la señal; exit = close a +hold min (o último bar).
    hold=None => hasta el último bar (cierre 15:55-16:00)."""
    if sig_i + 1 >= len(day["m"]):
        return None
    e_i = sig_i + 1
    entry = day["o"][e_i]
    x_i = len(day["m"]) - 1 if hold is None else (idx_at(day, day["m"][e_i] + hold) or e_i)
    if x_i <= e_i - 1:
        return None
    exit_ = day["c"][x_i]
    r = exit_ / entry - 1
    return (r if dir_ == "long" else -r) - COST


# ── Familias de hipótesis ────────────────────────────────────────────────────
# Cada hipótesis: fn(day) -> índice del bar señal (o None). Ventana 10:00-15:00.

def react(k, x, direction):
    """Retorno de los últimos k min <= -x (long) o >= +x (short)."""
    def fn(day):
        m, c = day["m"], day["c"]
        for i in range(len(m)):
            if not (30 <= m[i] <= 330):
                continue
            j = idx_at(day, m[i] - k)
            if j is None or m[i] - m[j] < k * 0.6:
                continue
            r = c[i] / c[j] - 1
            if (direction == "long" and r <= -x) or (direction == "short" and r >= x):
                return i
        return None
    return fn


def vclimax(mult, red=True):
    """Bloque 5-min con volumen >= mult x avg(20 bloques previos) y cuerpo rojo -> señal
    en el último bar del bloque."""
    def fn(day):
        m = day["m"]
        blocks = {}                      # bloque -> (vol, first_i, last_i)
        for i in range(len(m)):
            b = m[i] // 5
            vol, fi, li = blocks.get(b, (0.0, i, i))
            blocks[b] = (vol + day["v"][i], min(fi, i), max(li, i))
        keys = sorted(blocks)
        for bi, b in enumerate(keys):
            if bi < 20 or not (30 <= b * 5 <= 330):
                continue
            avg = sum(blocks[kk][0] for kk in keys[bi - 20:bi]) / 20
            vol, fi, li = blocks[b]
            if avg <= 0 or vol < mult * avg:
                continue
            if red and day["c"][li] >= day["o"][fi]:
                continue
            return li
        return None
    return fn


def hour_cond(minute, thr, mode):
    """A `minute` (desde 9:30): ret open->ahora vs umbral. mode: cont (>=+thr) / rev (<=-thr)."""
    def fn(day):
        i = idx_at(day, minute)
        if i is None or day["m"][i] < minute - 10:
            return None
        r = day["c"][i] / day["o"][0] - 1
        if (mode == "cont" and r >= thr) or (mode == "rev" and r <= -thr):
            return i
        return None
    return fn


def hypotheses():
    H = []
    def add(name, fam, dir_, hold, fn):
        H.append({"name": name, "family": fam, "dir": dir_, "hold": hold, "fn": fn})
    # R · reacciones k-min (mean reversion long / fade short)
    for k in (15, 30, 60):
        for x in (0.005, 0.008):
            for hold, hn in ((30, "h30"), (60, "h60"), (None, "hEOD")):
                add(f"rx_dn{k}m{x*100:g}%_{hn}", "reaction", "long", hold,
                    react(k, x, "long"))
    for k in (15, 30):
        for x in (0.008,):
            add(f"rx_up{k}m{x*100:g}%_h60s", "reaction", "short", 60, react(k, x, "short"))
    # V · volume climax (reversión tras pánico)
    for mult in (2.5, 3.5):
        for hold, hn in ((30, "h30"), (60, "h60"), (None, "hEOD")):
            add(f"vc_x{mult:g}red_{hn}", "volume", "long", hold, vclimax(mult))
    # H · condicional por hora (drift PM / reversión PM)
    for minute, mn in ((60, "1030"), (210, "1300"), (270, "1400"), (330, "1500")):
        for thr in (0.003, 0.005):
            add(f"hc_{mn}_up{thr*100:g}%_cont", "hourcond", "long", None,
                hour_cond(minute, thr, "cont"))
            add(f"hc_{mn}_dn{thr*100:g}%_rev", "hourcond", "long", None,
                hour_cond(minute, thr, "rev"))
    return H


# ── Protocolo (idéntico a gt_factory) ────────────────────────────────────────

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
    days = load_days()
    dates = list(days)
    print(f"Días RTH: {len(dates)} ({dates[0]} -> {dates[-1]})")
    splits = {"train": [d for d in dates if d < TRAIN_END],
              "valid": [d for d in dates if TRAIN_END <= d < VALID_END],
              "oos":   [d for d in dates if d >= VALID_END]}
    print(f"TRAIN {len(splits['train'])} | VALID {len(splits['valid'])} | "
          f"OOS(locked) {len(splits['oos'])}  · costo {COST*1e4:g} bps\n")

    H = hypotheses()
    registry, stage1 = [], []
    for h in H:
        def rets_of(dlist, h=h):
            out = []
            for d in dlist:
                day = days[d]
                if len(day["m"]) < 100:          # días rotos/half-day muy corto
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
               "hold": h["hold"], "train": s_tr}
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
        print(f"{'señal':<26}{'dir':<7}{'VALID n/mean/t/pf':<28}{'OOS n/mean/t/pf':<28}veredicto")
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
            print(f"{rec['name']:<26}{rec['dir']:<7}{vs:<28}{os_:<28}{ver}")
    (DATA / "gt_batch2_registry.json").write_text(json.dumps(registry, indent=1, default=str))
    print(f"\nRegistro completo ({len(registry)} hipótesis, incl. fallos) -> data/gt_batch2_registry.json")


if __name__ == "__main__":
    main()
