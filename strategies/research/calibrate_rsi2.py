"""RSI2-dip deep calibration: TP/SL distributions, avg win/loss, post-exit excursions
(money left on table / losses avoided), entry & exit variants.
Final config baseline: th<15 @5m seal, TP=0.5xATR5m, SL=1.0xATR5m, ts45, C4, skip open<VAL.
"""
import json
from pathlib import Path
from backtest import stats
from analysis_30d import build_days

ENTRY_MIN, ENTRY_MAX, FORCED = 30, 375, 385
POST = 30  # bars of post-exit tracking


def signals(day, thresh=15):
    """yield (i_signal, atr5) at each sealed 5-min bar with RSI2 < thresh."""
    for i in range(day.n):
        if (i + 1) % 5 != 0:
            continue
        k = (i + 1) // 5 - 1
        if k < 15 or day.f_rsi2[k] is None or day.f_atr[k] is None:
            continue
        if day.f_rsi2[k] < thresh:
            yield i, day.f_atr[k]


def run(days, tp_m=0.5, sl_m=1.0, ts=45, c4=True, gate_val=True,
        entry_mode="market", limit_off=0.0, limit_life=3,
        be_at_r=None, partial=None, delay_bars=0):
    """entry_mode: market (next open) | limit (at close - limit_off*atr5).
    partial: (tp1_r, tp2_r) -> 50% at tp1, BE stop, 50% at tp2."""
    trades = []
    misses = 0
    for day in days:
        if gate_val and day.y_val is not None and day.o[0] < day.y_val:
            continue
        pos_until = -1
        consec = 0
        for i, a5 in signals(day):
            e = i + 1
            if not (ENTRY_MIN <= e <= ENTRY_MAX) or e <= pos_until:
                continue
            if c4 and consec >= 2:
                break
            # ---- entry ----
            e0 = e + delay_bars
            if e0 > ENTRY_MAX:
                continue
            if entry_mode == "market":
                ei, entry = e0, day.o[e0]
            else:
                lim = round(day.c[i] - limit_off * a5, 2)
                ei = entry = None
                for j in range(e0, min(e0 + limit_life, ENTRY_MAX + 1)):
                    if day.l[j] <= lim:
                        ei, entry = j, min(day.o[j], lim)
                        break
                if ei is None:
                    misses += 1
                    continue
            risk = sl_m * a5
            sl = round(entry - risk, 2)
            tp = round(entry + tp_m * a5, 2)
            # ---- simulate ----
            if partial:
                tp1 = round(entry + partial[0] * risk, 2)
                tp2 = round(entry + partial[1] * risk, 2)
                half_done = False
                pnl = 0.0
                cur_sl = sl
                xi = None
                for j in range(ei, min(day.n, FORCED + 1)):
                    op = entry if j == ei else day.o[j]
                    if j >= FORCED:
                        rem = 0.5 if half_done else 1.0
                        pnl += rem * (day.o[j] - entry)
                        xi, xt = j, "TIME"
                        break
                    if day.l[j] <= cur_sl:
                        px = op if op <= cur_sl else cur_sl
                        rem = 0.5 if half_done else 1.0
                        pnl += rem * (px - entry)
                        xi, xt = j, ("BE" if half_done else "SL")
                        break
                    if not half_done and day.h[j] >= tp1:
                        px = op if op >= tp1 else tp1
                        pnl += 0.5 * (px - entry)
                        half_done = True
                        cur_sl = entry  # BE for runner
                    if half_done and day.h[j] >= tp2:
                        px = op if op >= tp2 else tp2
                        pnl += 0.5 * (px - entry)
                        xi, xt = j, "TP"
                        break
                    if ts is not None and j - ei >= ts:
                        rem = 0.5 if half_done else 1.0
                        pnl += rem * (day.c[j] - entry)
                        xi, xt = j, "TIME"
                        break
                if xi is None:
                    rem = 0.5 if half_done else 1.0
                    pnl += rem * (day.c[-1] - entry)
                    xi, xt = day.n - 1, "TIME"
                xp = entry + pnl  # synthetic
            else:
                cur_sl = sl
                xi = xp = xt = None
                mae = mfe = 0.0
                for j in range(ei, min(day.n, FORCED + 1)):
                    op = entry if j == ei else day.o[j]
                    if j >= FORCED:
                        xi, xp, xt = j, day.o[j], "TIME"
                        break
                    mae = max(mae, entry - day.l[j])
                    mfe = max(mfe, day.h[j] - entry)
                    if day.l[j] <= cur_sl:
                        xi, xp, xt = j, (op if op <= cur_sl else cur_sl), "SL"
                        break
                    if day.h[j] >= tp:
                        xi, xp, xt = j, (op if op >= tp else tp), "TP"
                        break
                    if ts is not None and j - ei >= ts:
                        xi, xp, xt = j, day.c[j], "TIME"
                        break
                    if be_at_r is not None and day.h[j] >= entry + be_at_r * risk:
                        cur_sl = max(cur_sl, entry)
                if xi is None:
                    xi, xp, xt = day.n - 1, day.c[-1], "TIME"
                pnl = xp - entry
            # post-exit excursion
            hi_post = lo_post = 0.0
            if xi + 1 < day.n:
                seg = range(xi + 1, min(day.n, xi + 1 + POST))
                hi_post = max(day.h[j] for j in seg) - (xp if not partial else entry + pnl)
                lo_post = min(day.l[j] for j in seg) - (xp if not partial else entry + pnl)
            trades.append({"day": day.date, "ei": ei, "entry": entry, "sl": sl, "tp": tp,
                           "atr5": a5, "xp": xp, "xt": xt, "pnl": pnl,
                           "risk_d": risk, "tp_d": tp_m * a5,
                           "mae": (mae if not partial else None),
                           "mfe": (mfe if not partial else None),
                           "hi_post": hi_post, "lo_post": lo_post})
            pos_until = xi
            consec = consec + 1 if pnl <= 0 else 0
    return trades, misses


def pct(arr, q):
    if not arr:
        return float("nan")
    a = sorted(arr)
    return a[min(len(a) - 1, int(q * len(a)))]


def line(name, ts, misses=None):
    s = stats(ts)
    if not s:
        print(f"{name:<26} n=0")
        return
    m = f" miss={misses}" if misses else ""
    print(f"{name:<26} n={s['n']:>3} hit={s['hit']:5.1f}% pnl={s['pnl']:>+7.2f} "
          f"avgW={s['aw']:+.3f} avgL={s['al']:+.3f} PF={s['pf']:4.2f}{m}")


def main():
    all_days, _ = build_days()
    days = [d for d in all_days if d.date >= "2026-04-27"]

    # ---------- baseline anatomy ----------
    ts, _ = run(days)
    s = stats(ts)
    print(f"BASELINE (tp0.5/sl1.0/ts45/C4/gateVAL): n={s['n']} hit={s['hit']:.1f}% "
          f"pnl={s['pnl']:+.2f} PF={s['pf']:.2f}")
    tpd = [t["tp_d"] for t in ts]
    sld = [t["risk_d"] for t in ts]
    print(f"TP dist $: p25={pct(tpd,0.25):.2f} p50={pct(tpd,0.5):.2f} p75={pct(tpd,0.75):.2f} "
          f"min={min(tpd):.2f} max={max(tpd):.2f}")
    print(f"SL dist $: p25={pct(sld,0.25):.2f} p50={pct(sld,0.5):.2f} p75={pct(sld,0.75):.2f} "
          f"min={min(sld):.2f} max={max(sld):.2f}")
    w = [t for t in ts if t["pnl"] > 0]
    l = [t for t in ts if t["pnl"] <= 0]
    print(f"avg win  = {sum(t['pnl'] for t in w)/len(w):+.3f} $/sh  (median {pct([t['pnl'] for t in w],0.5):+.3f})")
    print(f"avg loss = {sum(t['pnl'] for t in l)/len(l):+.3f} $/sh  (median {pct([t['pnl'] for t in l],0.5):+.3f})")
    by = {}
    for t in ts:
        by.setdefault(t["xt"], []).append(t)
    for k, v in sorted(by.items()):
        print(f"  exit {k:<5} n={len(v):>3} ({100*len(v)/len(ts):.0f}%) avg={sum(t['pnl'] for t in v)/len(v):+.3f}")

    # post-exit: money left on table / saved
    w_tp = [t for t in ts if t["xt"] == "TP"]
    l_sl = [t for t in ts if t["xt"] == "SL"]
    t_tm = [t for t in ts if t["xt"] == "TIME"]
    print(f"\nPOST-EXIT 30min:")
    print(f"  TP winners: extra move above exit p50={pct([t['hi_post'] for t in w_tp],0.5):+.2f} "
          f"p75={pct([t['hi_post'] for t in w_tp],0.75):+.2f} $/sh (dejado en mesa)")
    rec = sum(1 for t in l_sl if t["hi_post"] >= (t["entry"] - t["xp"]))
    print(f"  SL losers: bounce above exit p50={pct([t['hi_post'] for t in l_sl],0.5):+.2f}; "
          f"{rec}/{len(l_sl)} recuperan hasta entry en 30min (stop 'innecesario')")
    drop = pct([t['lo_post'] for t in l_sl], 0.5)
    print(f"  SL losers: caida extra post-stop p50={drop:+.2f} (perdida evitada)")
    print(f"  TIME exits: move after p50 hi={pct([t['hi_post'] for t in t_tm],0.5):+.2f} "
          f"lo={pct([t['lo_post'] for t in t_tm],0.5):+.2f}")

    # ---------- exit calibration ----------
    print("\nEXIT variants:")
    for nm, kw in [
        ("tp0.4", dict(tp_m=0.4)),
        ("tp0.5 (base)", dict()),
        ("tp0.6", dict(tp_m=0.6)),
        ("tp0.75", dict(tp_m=0.75)),
        ("tp0.5 ts30", dict(ts=30)),
        ("tp0.5 ts15", dict(ts=15)),
        ("tp0.75 BE@0.4", dict(tp_m=0.75, be_at_r=0.4)),
        ("tp1.0 BE@0.5", dict(tp_m=1.0, be_at_r=0.5)),
        ("partial 0.5R/1.0R+BE", dict(partial=(0.5, 1.0))),
        ("partial 0.4R/0.8R+BE", dict(partial=(0.4, 0.8))),
        ("sl1.25 tp0.5", dict(sl_m=1.25)),
    ]:
        t2, _ = run(days, **kw)
        line(nm, t2)

    # ---------- entry calibration ----------
    print("\nENTRY variants (same exits tp0.5/sl1.0):")
    for nm, kw in [
        ("market next-open (base)", dict()),
        ("limit @close life3", dict(entry_mode="limit", limit_off=0.0, limit_life=3)),
        ("limit @close life5", dict(entry_mode="limit", limit_off=0.0, limit_life=5)),
        ("limit close-0.1ATR life5", dict(entry_mode="limit", limit_off=0.1, limit_life=5)),
        ("limit close-0.2ATR life5", dict(entry_mode="limit", limit_off=0.2, limit_life=5)),
    ]:
        t2, miss = run(days, **kw)
        line(nm, t2, miss)

    # ---------- combo: best entry + best exit ----------
    print("\nCOMBOS:")
    for nm, kw in [
        ("limit@close + tp0.5", dict(entry_mode="limit", limit_life=5)),
        ("limit@close + partial", dict(entry_mode="limit", limit_life=5, partial=(0.5, 1.0))),
        ("limit-0.1ATR + tp0.6", dict(entry_mode="limit", limit_off=0.1, limit_life=5, tp_m=0.6)),
    ]:
        t2, miss = run(days, **kw)
        line(nm, t2, miss)


if __name__ == "__main__":
    main()
