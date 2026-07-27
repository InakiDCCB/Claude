"""RUUT Cyclone (TD Sequential) — backtest sobre QQQ 5-min (2026-07-16).

Port del Pine `RUUT_Cyclone_V3_9.pine` (usuario): TD Setup 9 / Countdown 13 (DeMark) con
perfección (9P/13P) + filtros RSI14-zona (≤30 buy / ≥70 sell), EMA200 y MTF 15-min momentum.
SL = low − 2×ATR14(5m) · TP = close + 3×ATR14(5m) (espejo para short). Fidelidad: setup/cancel
portados; el "recycle" del countdown NO (simplificación documentada — afecta <5% de countdowns).

Objetivo (directiva usuario): "probar aumentar su asertividad en QQQ" → matriz señal × filtros ×
dirección sobre ~60 sesiones 1-min→5-min con mitades TUNE/TEST. La config ganadora (si la hay,
listón shadow: n≥15, PF≥1.5, mitades coherentes) va a shadow batch en /post-close (td_shadow.py).
"""
import json
from pathlib import Path

DATA = Path(__file__).parent / "data" / "qqq_1min.json"
SPLIT = "2026-06-10"          # mitades TUNE (<) / TEST (>=)


# ── Datos: 1-min → bloques 5-min continuos ───────────────────────────────────

def load():
    bars = json.load(DATA.open())
    byday = {}
    for b in bars:
        byday.setdefault(b["t"][:10], []).append(b)
    days = sorted(byday)
    blocks = []                                   # continuo multi-día
    for d in days:
        bs = byday[d]
        for i0 in range(0, len(bs), 5):
            grp = bs[i0:i0 + 5]
            blocks.append({"d": d, "i0": i0, "i1": min(i0 + len(grp) - 1, len(bs) - 1),
                           "o": grp[0]["o"], "h": max(x["h"] for x in grp),
                           "l": min(x["l"] for x in grp), "c": grp[-1]["c"],
                           "v": sum(x["v"] for x in grp)})
    return byday, days, blocks


def rsi(vals, n=14):
    out = [None] * len(vals)
    if len(vals) < n + 1:
        return out
    g = l = 0.0
    for k in range(1, n + 1):
        d = vals[k] - vals[k - 1]
        g += max(d, 0); l += max(-d, 0)
    ag, al = g / n, l / n
    out[n] = 100 - 100 / (1 + (ag / al if al else 1e9))
    for k in range(n + 1, len(vals)):
        d = vals[k] - vals[k - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[k] = 100 - 100 / (1 + (ag / al if al else 1e9))
    return out


def ema(vals, n):
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    s = sum(vals[:n]) / n
    out[n - 1] = s
    k = 2 / (n + 1)
    for i in range(n, len(vals)):
        s = vals[i] * k + s * (1 - k)
        out[i] = s
    return out


def atr(blocks, n=14):
    out = [None] * len(blocks)
    trs = []
    for i, b in enumerate(blocks):
        pc = blocks[i - 1]["c"] if i else b["c"]
        trs.append(max(b["h"] - b["l"], abs(b["h"] - pc), abs(b["l"] - pc)))
    if len(trs) < n:
        return out
    a = sum(trs[:n]) / n
    out[n - 1] = a
    for i in range(n, len(trs)):
        a = (a * (n - 1) + trs[i]) / n
        out[i] = a
    return out


# ── TD Sequential (setup + countdown, fiel al Pine salvo recycle) ────────────

def td_signals(blocks):
    """Devuelve señales: {i, side:'long'|'short', kind:'S9'|'S9P'|'C13'|'C13P'}"""
    n = len(blocks)
    c = [b["c"] for b in blocks]; h = [b["h"] for b in blocks]; l = [b["l"] for b in blocks]
    sL = [0] * n; sS = [0] * n                     # setupLong (buy) / setupShort (sell)
    out = []
    LONG, SHORT, CANC = -1, 1, 0
    last = CANC; setupHigh = setupLow = None
    cdL = cdS = 0
    for i in range(5, n):
        # setup (Pine: setupLong cuenta closes < close[4])
        sL[i] = 0 if c[i] > c[i - 4] else (1 if (sL[i - 1] == 0 and c[i - 1] > c[i - 5] and c[i] < c[i - 4])
                                           else (0 if sL[i - 1] == 0 else sL[i - 1] + 1))
        sS[i] = 0 if c[i] < c[i - 4] else (1 if (sS[i - 1] == 0 and c[i - 1] < c[i - 5] and c[i] > c[i - 4])
                                           else (0 if sS[i - 1] == 0 else sS[i - 1] + 1))
        nine = None
        if sL[i] == 9:
            perf = l[i] <= l[i - 2] and l[i] <= l[i - 3] or (l[i - 1] <= l[i - 2] and l[i - 1] <= l[i - 3])
            nine = ("long", "S9P" if perf else "S9")
            last = LONG; setupHigh = max(h[i - 8:i + 1]); setupLow = min(l[i - 8:i + 1]); cdL = cdS = 0
        elif sS[i] == 9:
            perf = h[i] >= h[i - 2] and h[i] >= h[i - 3] or (h[i - 1] >= h[i - 2] and h[i - 1] >= h[i - 3])
            nine = ("short", "S9P" if perf else "S9")
            last = SHORT; setupHigh = max(h[i - 8:i + 1]); setupLow = min(l[i - 8:i + 1]); cdL = cdS = 0
        if nine:
            out.append({"i": i, "side": nine[0], "kind": nine[1]})
            continue
        # cancel countdown (Pine): buy-cd cancela si low > setupHigh; sell-cd si high < setupLow
        if last == LONG and setupHigh is not None and l[i] > setupHigh:
            last = CANC; cdL = 0
        if last == SHORT and setupLow is not None and h[i] < setupLow:
            last = CANC; cdS = 0
        # countdown (buy: close < low[2]; sell: close > high[2])
        if last == LONG and i >= 2:
            if c[i] < l[i - 2]:
                cdL += 1
                if cdL == 13:
                    out.append({"i": i, "side": "long", "kind": "C13"})
                    last = CANC; cdL = 0
        if last == SHORT and i >= 2:
            if c[i] > h[i - 2]:
                cdS += 1
                if cdS == 13:
                    out.append({"i": i, "side": "short", "kind": "C13"})
                    last = CANC; cdS = 0
    return out


# ── Simulación (1-min, fill limit ≤3 barras, SL-first, cierre 15:55) ─────────

def simulate(byday, sig_day, i1, side, entry, sl, tp):
    bs = byday[sig_day]
    fi = None
    for j in range(i1 + 1, min(i1 + 4, len(bs))):
        if (side == "long" and bs[j]["l"] <= entry) or (side == "short" and bs[j]["h"] >= entry):
            fi = j; break
    if fi is None:
        return None                                # MISS
    cutoff = len(bs) - 5                           # ~15:55
    for j in range(fi, len(bs)):
        b = bs[j]
        if side == "long":
            if b["l"] <= sl:  return sl - entry
            if b["h"] >= tp:  return tp - entry
        else:
            if b["h"] >= sl:  return entry - sl
            if b["l"] <= tp:  return entry - tp
        if j >= cutoff:
            return (b["c"] - entry) if side == "long" else (entry - b["c"])
    return (bs[-1]["c"] - entry) if side == "long" else (entry - bs[-1]["c"])


def stats(rets):
    n = len(rets)
    if n == 0:
        return None
    w = sum(1 for r in rets if r > 0)
    gw = sum(r for r in rets if r > 0); gl = -sum(r for r in rets if r <= 0)
    return {"n": n, "hit": 100 * w / n, "pnl": sum(rets),
            "pf": (gw / gl) if gl > 0 else float("inf")}


def row(tag, s):
    if not s:
        return f"{tag:<34} n=0"
    pf = f"{s['pf']:.2f}" if s['pf'] != float('inf') else "inf"
    return f"{tag:<34} n={s['n']:<4} hit={s['hit']:5.1f}% pnl={s['pnl']:+7.2f}/sh pf={pf}"


def main():
    byday, days, blocks = load()
    closes = [b["c"] for b in blocks]
    r14 = rsi(closes); e200 = ema(closes, 200); a14 = atr(blocks)
    # MTF 15-min: bloques de 3×5min → momentum close > close[4] (15m)
    m15 = [blocks[i]["c"] for i in range(2, len(blocks), 3)]
    def mtf_bull(i):
        k = (i - 2) // 3
        return k >= 4 and m15[min(k, len(m15)-1)] > m15[min(k, len(m15)-1) - 4]
    sigs = td_signals(blocks)
    print(f"Bloques 5-min: {len(blocks)} · {len(days)} días ({days[0]}→{days[-1]}) · señales TD crudas: {len(sigs)}")

    FILTERS = {
        "raw":      lambda s, i: True,
        "rsi":      lambda s, i: r14[i] is not None and (r14[i] <= 30 if s == "long" else r14[i] >= 70),
        "ema":      lambda s, i: e200[i] is not None and ((closes[i] > e200[i]) if s == "long" else (closes[i] < e200[i])),
        "mtf":      lambda s, i: mtf_bull(i) if s == "long" else not mtf_bull(i),
        "rsi+ema":  lambda s, i: FILTERS["rsi"](s, i) and FILTERS["ema"](s, i),
        "rsi_soft": lambda s, i: r14[i] is not None and (r14[i] <= 40 if s == "long" else r14[i] >= 60),
    }
    for side in ("long", "short"):
        for kinds, kn in ((("S9", "S9P"), "S9+9P"), (("S9P",), "9P"), (("C13",), "C13")):
            for fname, ffn in FILTERS.items():
                rets_all, rets_tune, rets_test = [], [], []
                for s in sigs:
                    if s["side"] != side or s["kind"] not in kinds:
                        continue
                    i = s["i"]
                    if a14[i] is None or not ffn(side, i):
                        continue
                    b = blocks[i]
                    if side == "long":
                        entry = b["c"]; sl = b["l"] - 2 * a14[i]; tp = b["c"] + 3 * a14[i]
                    else:
                        entry = b["c"]; sl = b["h"] + 2 * a14[i]; tp = b["c"] - 3 * a14[i]
                    r = simulate(byday, b["d"], b["i1"], side, entry, sl, tp)
                    if r is None:
                        continue
                    rets_all.append(r)
                    (rets_tune if b["d"] < SPLIT else rets_test).append(r)
                s_all = stats(rets_all)
                if s_all and s_all["n"] >= 10:
                    st, sv = stats(rets_tune), stats(rets_test)
                    halves = (f" | TUNE n={st['n']} pf={st['pf']:.2f}" if st else " | TUNE n=0") + \
                             (f" TEST n={sv['n']} pf={sv['pf']:.2f}" if sv else " TEST n=0")
                    print(row(f"{side} {kn} [{fname}]", s_all) + halves)


if __name__ == "__main__":
    main()
