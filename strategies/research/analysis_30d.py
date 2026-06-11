"""30-day deep analysis: day-context metrics (live-measurable), conditional system
performance, execution microstructure (fill speed, MAE/MFE), new systems, walk-forward.
Imports the engine from backtest.py.
"""
import json
import math
from pathlib import Path
from backtest import (Day, simulate, run_market, stats, LEVEL_FNS,
                      rsi2_dip, ema9_reclaim, vwap_pullback, sweep_reclaim,
                      make_level_bounce, gap_fill, vwap_band, ibs_5m)

DATA = Path(__file__).parent / "data" / "qqq_1min.json"
ENTRY_MIN, ENTRY_MAX, FORCED = 30, 375, 385


def build_days():
    bars = json.loads(DATA.read_text())
    bydate = {}
    for b in bars:
        bydate.setdefault(b["t"][:10], []).append(b)
    dates = sorted(bydate)
    days_all = {}
    prev = None
    for d in dates:
        days_all[d] = Day(d, bydate[d], prev)
        prev = days_all[d]
    for idx, d in enumerate(dates):
        day = days_all[d]
        vws = []
        for pd_ in dates[max(0, idx - 3):idx]:
            p = days_all[pd_]
            vws.append(sum((p.h[i] + p.l[i] + p.c[i]) / 3 * p.v[i] for i in range(p.n)) / sum(p.v))
        day.prior3_vw = vws
        # trailing 5-day daily range + first-30min volume baseline
        rngs, v30s = [], []
        for pd_ in dates[max(0, idx - 5):idx]:
            p = days_all[pd_]
            rngs.append(max(p.h) - min(p.l))
            v30s.append(sum(p.v[:30]))
        day.avg_range5 = sum(rngs) / len(rngs) if rngs else None
        day.avg_v30_5 = sum(v30s) / len(v30s) if v30s else None
    return [days_all[d] for d in dates], dates


def day_context(day):
    """All live-measurable by 10:30 ET, plus (separately) outcome diagnostics."""
    ctx = {}
    if day.pdc:
        ctx["gap_pct"] = 100 * (day.o[0] - day.pdc) / day.pdc
    if day.y_vah and day.y_val:
        ctx["open_loc"] = ("above_VAH" if day.o[0] > day.y_vah
                           else "below_VAL" if day.o[0] < day.y_val else "inside_VA")
    or_rng = day.or_high - day.or_low
    ctx["or30_rng"] = or_rng
    if day.avg_range5:
        ctx["or30_ratio"] = or_rng / day.avg_range5
    if day.avg_v30_5:
        ctx["rvol30"] = sum(day.v[:30]) / day.avg_v30_5
    # vwap crosses 9:30-10:30
    crosses = 0
    for i in range(1, 60):
        a = day.c[i - 1] - day.vwap[i - 1]
        b = day.c[i] - day.vwap[i]
        if a * b < 0:
            crosses += 1
    ctx["xvwap60"] = crosses
    ctx["first30_dir"] = 1 if day.c[29] > day.o[0] else -1
    # 5m ATR at 10:00 (k=5 -> not ready; use 1-min ATR proxy at idx 30)
    ctx["atr1m_1000"] = day.atr[30]
    # outcome diagnostics (NOT live-knowable)
    ctx["day_ret"] = 100 * (day.c[-1] - day.o[0]) / day.o[0]
    ctx["trend_score"] = abs(day.c[-1] - day.o[0]) / (max(day.h) - min(day.l))
    touch = sum(1 for i in range(60, FORCED) if day.l[i] <= day.vwap[i] <= day.h[i])
    ctx["vwap_touch_rate"] = touch / (FORCED - 60)
    return ctx


# ---------- FVG runner with metadata (fill speed, MAE/MFE) ----------

def run_fvg_meta(days, band=(0.50, 1.00), max_fills=2):
    trades = []
    for day in days:
        pending = None
        pos_until = -1
        fills = 0
        for i in range(day.n):
            if i <= pos_until:
                pending = None
                continue
            if pending is not None:
                if day.l[i] <= pending["px"]:
                    entry = min(day.o[i], pending["px"])
                    sl = pending["sl"]
                    if sl < entry:
                        risk = entry - sl
                        tp = entry + 2 * risk
                        # simulate with excursion tracking
                        cur = None
                        mae = mfe = 0.0
                        xi = xp = xt = None
                        for j in range(i, min(day.n, FORCED + 1)):
                            op = entry if j == i else day.o[j]
                            if j >= FORCED:
                                xi, xp, xt = j, day.o[j], "TIME"
                                break
                            mae = max(mae, entry - day.l[j])
                            mfe = max(mfe, day.h[j] - entry)
                            if day.l[j] <= sl:
                                xi, xp, xt = j, (op if op <= sl else sl), "SL"
                                break
                            if day.h[j] >= tp:
                                xi, xp, xt = j, (op if op >= tp else tp), "TP"
                                break
                        if xi is None:
                            xi, xp, xt = day.n - 1, day.c[-1], "TIME"
                        trades.append({"day": day.date, "ei": i, "entry": entry, "sl": sl,
                                       "xp": xp, "xt": xt, "pnl": xp - entry,
                                       "risk": round(entry - sl, 2),
                                       "fill_bars": i - pending["placed"],
                                       "bars_held": xi - i,
                                       "mae_r": mae / risk, "mfe_r": mfe / risk,
                                       "ordinal": fills + 1})
                        pos_until = xi
                        fills += 1
                    pending = None
                    continue
                if day.c[i] < pending["sl"] or i - pending["placed"] >= 60 or i > ENTRY_MAX + 10:
                    pending = None
            if max_fills is not None and fills >= max_fills:
                continue
            if pending is None and i >= 2 and ENTRY_MIN <= i + 1 <= ENTRY_MAX:
                if day.l[i] > day.h[i - 2]:
                    mid = round((day.l[i] + day.h[i - 2]) / 2, 2)
                    sl = round(day.l[i - 2] - 0.02, 2)
                    if band and not (band[0] <= mid - sl <= band[1]):
                        continue
                    pending = {"px": mid, "sl": sl, "placed": i}
    return trades


# ---------- market-system runner with MAE/MFE ----------

def run_market_meta(days, signal_fn, c4=False):
    trades = []
    for day in days:
        pos_until = -1
        consec = 0
        for i in range(day.n - 1):
            e = i + 1
            if not (ENTRY_MIN <= e <= ENTRY_MAX) or e <= pos_until:
                continue
            if c4 and consec >= 2:
                break
            sig = signal_fn(day, i)
            if sig is None:
                continue
            entry = day.o[e]
            if "sl_abs" in sig:
                sl = sig["sl_abs"]
            else:
                a = sig.get("atr5") if sig.get("atr5") is not None else day.atr[i]
                if a is None:
                    continue
                sl = entry - sig["sl_atr"] * a
            sl = round(sl, 2)
            if sl >= entry:
                continue
            tp_spec = sig["tp"]
            if tp_spec[0] == "atrx":
                tp_spec = ("abs", round(entry + tp_spec[1] * tp_spec[2], 2))
            risk = entry - sl
            tp_abs = entry + tp_spec[1] * risk if tp_spec[0] == "r" else (
                tp_spec[1] if tp_spec[0] == "abs" else None)
            ts = sig.get("time_stop")
            mae = mfe = 0.0
            xi = xp = xt = None
            for j in range(e, min(day.n, FORCED + 1)):
                op = entry if j == e else day.o[j]
                if j >= FORCED:
                    xi, xp, xt = j, day.o[j], "TIME"
                    break
                mae = max(mae, entry - day.l[j])
                mfe = max(mfe, day.h[j] - entry)
                if day.l[j] <= sl:
                    xi, xp, xt = j, (op if op <= sl else sl), "SL"
                    break
                if tp_abs and day.h[j] >= tp_abs:
                    xi, xp, xt = j, (op if op >= tp_abs else tp_abs), "TP"
                    break
                if ts is not None and j - e >= ts:
                    xi, xp, xt = j, day.c[j], "TIME"
                    break
            if xi is None:
                xi, xp, xt = day.n - 1, day.c[-1], "TIME"
            trades.append({"day": day.date, "ei": e, "entry": entry, "sl": sl, "xp": xp,
                           "xt": xt, "pnl": xp - entry, "risk": risk,
                           "bars_held": xi - e, "mae_r": mae / risk, "mfe_r": mfe / risk})
            pos_until = xi
            consec = consec + 1 if xp - entry <= 0 else 0
    return trades


def pstats(name, ts):
    s = stats(ts)
    if not s:
        print(f"{name:<18} n=0")
        return
    print(f"{name:<18} n={s['n']:>4} hit={s['hit']:5.1f}% pnl={s['pnl']:>+8.2f} "
          f"mean={s['mean']:+.3f}±{s['se']:.3f} PF={s['pf']:4.2f} mLL={s['mll']}")


def main():
    all_days, dates = build_days()
    days = [d for d in all_days if d.date >= "2026-04-27"]   # 32 sessions, warm levels
    LEVEL_FNS.update({
        "VAL": lambda day: [day.y_val],
        "VPOC": lambda day: [day.y_vpoc],
        "PDL": lambda day: [day.pdl],
        "PDC": lambda day: [day.pdc],
        "KEY": lambda day: [day.y_val, day.y_vpoc, day.pdl, day.pdc],
        "Y3VW": lambda day: day.prior3_vw,
    })
    print(f"Backtest window: {days[0].date}..{days[-1].date} ({len(days)} sessions)")

    ctx = {d.date: day_context(d) for d in days}

    # ---- context table (compact) ----
    print("\nDAY CONTEXT (live-measurable by 10:30):")
    print(f"{'date':<11}{'gap%':>6}{'open_loc':>10}{'orR':>6}{'rvol':>6}{'xVW':>4}"
          f"{'d30':>4} | {'ret%':>6}{'trend':>6}{'vwapT':>6}")
    for d in days:
        c = ctx[d.date]
        print(f"{d.date:<11}{c.get('gap_pct', 0):>6.2f}{c.get('open_loc', '?'):>10}"
              f"{c.get('or30_ratio', 0):>6.2f}{c.get('rvol30', 0):>6.2f}{c['xvwap60']:>4}"
              f"{c['first30_dir']:>4} | {c['day_ret']:>6.2f}{c['trend_score']:>6.2f}"
              f"{c['vwap_touch_rate']:>6.2f}")

    # ---- headline systems over 32 days ----
    print("\nSYSTEMS over 32 sessions (out-of-sample for params tuned on 06-01..10):")
    res = {}
    res["FVG_f2_r0510"] = run_fvg_meta(days, band=(0.50, 1.00), max_fills=2)
    res["FVG_first2"] = run_fvg_meta(days, band=None, max_fills=2)
    res["FVG_all"] = run_fvg_meta(days, band=None, max_fills=None)
    res["RSI2_t04_th15_C4"] = run_market_meta(days, rsi2_dip(0.4, thresh=15, sl_mult=1.0)(), c4=True)
    res["RSI2_t05_th10_C4"] = run_market_meta(days, rsi2_dip(0.5, thresh=10, sl_mult=1.0)(), c4=True)
    res["E9RC_05R"] = run_market_meta(days, ema9_reclaim(("r", 0.5))(), c4=False)
    res["VWAPPB_C4"] = run_market_meta(days, vwap_pullback(45, 65)(), c4=True)
    res["SWP_05R"] = run_market_meta(days, sweep_reclaim(("r", 0.5))(), c4=False)
    res["GAPFILL"] = run_market_meta(days, gap_fill()(), c4=False)
    res["VPOC_b_1R"] = run_market_meta(days, make_level_bounce("VPOC", tp=("r", 1.0))(), c4=False)
    for k, v in res.items():
        pstats(k, v)

    # ---- conditional hit ratios ----
    def cond_table(name, ts, label, bucket_fn):
        groups = {}
        for t in ts:
            b = bucket_fn(ctx[t["day"]])
            if b is None:
                continue
            groups.setdefault(b, []).append(t)
        parts = []
        for b in sorted(groups):
            s = stats(groups[b])
            parts.append(f"{b}: n={s['n']} {s['hit']:.0f}% {s['pnl']:+.1f}")
        print(f"  {name:<18} {label:<10} " + " | ".join(parts))

    print("\nCONDITIONAL HIT (xvwap60 chop detector: lo<=2, mid 3-5, hi>=6):")
    xb = lambda c: ("lo" if c["xvwap60"] <= 2 else "hi" if c["xvwap60"] >= 6 else "mid")
    for k in ("FVG_first2", "RSI2_t04_th15_C4", "E9RC_05R", "VWAPPB_C4", "VPOC_b_1R"):
        cond_table(k, res[k], "xvwap", xb)

    print("\nCONDITIONAL HIT (open_loc vs yesterday VA):")
    ob = lambda c: c.get("open_loc")
    for k in ("FVG_first2", "RSI2_t04_th15_C4", "E9RC_05R", "VWAPPB_C4", "VPOC_b_1R"):
        cond_table(k, res[k], "open_loc", ob)

    print("\nCONDITIONAL HIT (rvol30: lo<0.85, mid, hi>1.15):")
    rb = lambda c: (None if "rvol30" not in c else
                    "lo" if c["rvol30"] < 0.85 else "hi" if c["rvol30"] > 1.15 else "mid")
    for k in ("FVG_first2", "RSI2_t04_th15_C4", "E9RC_05R", "VWAPPB_C4"):
        cond_table(k, res[k], "rvol30", rb)

    print("\nCONDITIONAL HIT (gap: dn<-0.25, flat, up>0.25):")
    gb = lambda c: (None if "gap_pct" not in c else
                    "dn" if c["gap_pct"] < -0.25 else "up" if c["gap_pct"] > 0.25 else "flat")
    for k in ("FVG_first2", "RSI2_t04_th15_C4", "E9RC_05R", "VWAPPB_C4"):
        cond_table(k, res[k], "gap", gb)

    # ---- microstructure: FVG fill speed & ordinal ----
    print("\nFVG fill-speed (bars placement->fill) x outcome [FVG_first2]:")
    fs = {}
    for t in res["FVG_first2"]:
        b = "0-1" if t["fill_bars"] <= 1 else "2-5" if t["fill_bars"] <= 5 else "6+"
        fs.setdefault(b, []).append(t)
    for b in ("0-1", "2-5", "6+"):
        if b in fs:
            s = stats(fs[b])
            print(f"  fill {b:<4} n={s['n']:>3} hit={s['hit']:5.1f}% pnl={s['pnl']:+7.2f}")
    print("FVG ordinal (1st vs 2nd fill) [FVG_first2]:")
    for o in (1, 2):
        ts = [t for t in res["FVG_first2"] if t["ordinal"] == o]
        if ts:
            s = stats(ts)
            print(f"  fill#{o} n={s['n']:>3} hit={s['hit']:5.1f}% pnl={s['pnl']:+7.2f}")

    # ---- MAE/MFE ----
    def excursions(name, ts):
        w = [t for t in ts if t["pnl"] > 0]
        l = [t for t in ts if t["pnl"] <= 0]
        if not w or not l:
            return
        wm = sorted(t["mae_r"] for t in w)
        lf = sorted(t["mfe_r"] for t in l)
        bh = sorted(t["bars_held"] for t in w)
        p = lambda arr, q: arr[min(len(arr) - 1, int(q * len(arr)))]
        print(f"  {name:<18} winners MAE p50={p(wm,0.5):.2f}R p75={p(wm,0.75):.2f}R "
              f"p90={p(wm,0.9):.2f}R | losers MFE p50={p(lf,0.5):.2f}R p75={p(lf,0.75):.2f}R"
              f" | win bars p50={p(bh,0.5)} p90={p(bh,0.9)}")
    print("\nMAE/MFE (R units):")
    for k in ("FVG_first2", "FVG_f2_r0510", "RSI2_t04_th15_C4", "E9RC_05R", "VWAPPB_C4"):
        excursions(k, res[k])

    # ================= ROUND 2 =================

    # ---- RSI2 stop-tightening grid (MAE-driven) ----
    print("\nRSI2 grid OOS (th15, C4) sl x tp:")
    for slm in (0.7, 0.8, 1.0):
        line = f"  sl={slm:.1f}"
        for tpm in (0.4, 0.5):
            ts = run_market_meta(days, rsi2_dip(tpm, thresh=15, sl_mult=slm)(), c4=True)
            s = stats(ts)
            line += f"   tp{tpm}: n={s['n']:>3} {s['hit']:5.1f}% {s['pnl']:>+7.2f} PF={s['pf']:4.2f}"
        print(line)

    # ---- RSI2 + open_loc gate ----
    def rsi2_gated(day, i, base=rsi2_dip(0.4, thresh=15, sl_mult=1.0)()):
        if day.y_val is not None and day.o[0] < day.y_val:
            return None
        return base(day, i)
    ts = run_market_meta(days, rsi2_gated, c4=True)
    pstats("RSI2_skipBelowVAL", ts)
    res["RSI2_gated"] = ts

    # ---- FVG: fill#1 only, fast-fill only ----
    def run_fvg_v(band, max_fills, expiry):
        return run_fvg_meta2(days, band, max_fills, expiry)
    print("\nFVG variants OOS:")
    for nm, band, mf, ex in (("FVG_fill1", None, 1, 60),
                             ("FVG_fill1_band", (0.50, 1.00), 1, 60),
                             ("FVG_fill1_fast", None, 1, 2),
                             ("FVG_fill2_fast", None, 2, 2),
                             ("FVG_fast_all", None, None, 2)):
        ts = run_fvg_v(band, mf, ex)
        pstats(nm, ts)
        res[nm] = ts

    # ---- SWP confirm + variant ----
    for nm, tp in (("SWP_075R", ("r", 0.75)), ("SWP_1R", ("r", 1.0))):
        pstats(nm, run_market_meta(days, sweep_reclaim(tp)(), c4=False))

    # ---- Meta-playbook: day-selector vs always-on ----
    # components per day: RSI2(gated) always; FVG_fill1_fast + VWAPPB only if xvwap60>=6;
    # GAPFILL only if gap<-0.3%
    print("\nMETA-PLAYBOOK per-day (selector) vs ALWAYS-ALL:")
    comp = {
        "RSI2": res["RSI2_gated"],
        "FVG": res["FVG_fill1_fast"],
        "VWAPPB": res["VWAPPB_C4"],
        "GAPF": res["GAPFILL"],
    }
    sel_pnl = {}
    all_pnl = {}
    sel_trades = []
    for d in days:
        c = ctx[d.date]
        chop = c["xvwap60"] >= 6
        gapdn = c.get("gap_pct", 0) < -0.3
        dayp_sel = 0.0
        dayp_all = 0.0
        for nm, ts in comp.items():
            dts = [t for t in ts if t["day"] == d.date]
            p = sum(t["pnl"] for t in dts)
            dayp_all += p
            use = (nm == "RSI2") or (nm in ("FVG", "VWAPPB") and chop) or (nm == "GAPF" and gapdn)
            if use:
                dayp_sel += p
                sel_trades.extend(dts)
        sel_pnl[d.date] = dayp_sel
        all_pnl[d.date] = dayp_all
    s_sel = stats(sel_trades)
    print(f"  SELECTOR: n={s_sel['n']} hit={s_sel['hit']:.1f}% pnl={s_sel['pnl']:+.2f} "
          f"PF={s_sel['pf']:.2f} | days+ {sum(1 for v in sel_pnl.values() if v > 0)}/"
          f"{sum(1 for v in sel_pnl.values() if abs(v) > 1e-9)} traded")
    at = [t for ts in comp.values() for t in ts]
    s_all = stats(at)
    print(f"  ALWAYS:   n={s_all['n']} hit={s_all['hit']:.1f}% pnl={s_all['pnl']:+.2f} "
          f"PF={s_all['pf']:.2f} | days+ {sum(1 for v in all_pnl.values() if v > 0)}/"
          f"{sum(1 for v in all_pnl.values() if abs(v) > 1e-9)}")

    # ---- walk-forward: tune 04-27..05-22, test 05-26..06-10 ----
    print("\nWALK-FORWARD (tune<=05-22, test>=05-26):")
    d_tr = [d for d in days if d.date <= "2026-05-22"]
    d_te = [d for d in days if d.date >= "2026-05-26"]
    candidates = {
        "RSI2_t04_th15_C4": lambda dd: run_market_meta(dd, rsi2_dip(0.4, thresh=15, sl_mult=1.0)(), True),
        "RSI2_t05_th10_C4": lambda dd: run_market_meta(dd, rsi2_dip(0.5, thresh=10, sl_mult=1.0)(), True),
        "RSI2_t04_s08_C4": lambda dd: run_market_meta(dd, rsi2_dip(0.4, thresh=15, sl_mult=0.8)(), True),
        "FVG_fill1": lambda dd: run_fvg_meta2(dd, None, 1, 60),
        "FVG_fill1_fast": lambda dd: run_fvg_meta2(dd, None, 1, 2),
        "VWAPPB_C4": lambda dd: run_market_meta(dd, vwap_pullback(45, 65)(), True),
        "SWP_05R": lambda dd: run_market_meta(dd, sweep_reclaim(("r", 0.5))(), False),
    }
    for nm, fn in candidates.items():
        s1 = stats(fn(d_tr))
        s2 = stats(fn(d_te))
        f = lambda s: f"n={s['n']:>3} {s['hit']:5.1f}% {s['pnl']:>+7.2f} PF={s['pf']:4.2f}" if s else "n=0"
        print(f"  {nm:<18} TUNE {f(s1)} | TEST {f(s2)}")

    # ---- week-by-week consistency of finalists ----
    print("\nWEEKLY PnL of finalists:")
    weeks = {}
    for d in days:
        wk = d.date[:8] + "W"  # group by month-week approx: use ISO week
    import datetime
    def wk_of(ds):
        y, m, dd_ = map(int, ds.split("-"))
        return datetime.date(y, m, dd_).isocalendar()[1]
    finals = ["RSI2_gated", "FVG_fill1_fast", "VWAPPB_C4", "SWP_05R", "GAPFILL"]
    wkset = sorted({wk_of(d.date) for d in days})
    print(f"{'system':<16}" + "".join(f"  W{w:<5}" for w in wkset))
    for nm in finals:
        ts = res.get(nm) or []
        line = f"{nm:<16}"
        for w in wkset:
            p = sum(t["pnl"] for t in ts if wk_of(t["day"]) == w)
            line += f"{p:>+8.2f}"
        print(line)

    json.dump({k: v for k, v in res.items()},
              open(Path(__file__).parent / "data" / "trades_30d.json", "w"), default=str)
    print("\nsaved trades_30d.json")


def run_fvg_meta2(days, band, max_fills, expiry):
    """run_fvg_meta with configurable expiry (bars of pending life)."""
    trades = []
    for day in days:
        pending = None
        pos_until = -1
        fills = 0
        for i in range(day.n):
            if i <= pos_until:
                pending = None
                continue
            if pending is not None:
                if day.l[i] <= pending["px"]:
                    entry = min(day.o[i], pending["px"])
                    sl = pending["sl"]
                    if sl < entry:
                        risk = entry - sl
                        tp = entry + 2 * risk
                        xi = xp = xt = None
                        for j in range(i, min(day.n, FORCED + 1)):
                            op = entry if j == i else day.o[j]
                            if j >= FORCED:
                                xi, xp, xt = j, day.o[j], "TIME"
                                break
                            if day.l[j] <= sl:
                                xi, xp, xt = j, (op if op <= sl else sl), "SL"
                                break
                            if day.h[j] >= tp:
                                xi, xp, xt = j, (op if op >= tp else tp), "TP"
                                break
                        if xi is None:
                            xi, xp, xt = day.n - 1, day.c[-1], "TIME"
                        trades.append({"day": day.date, "ei": i, "entry": entry, "sl": sl,
                                       "xp": xp, "xt": xt, "pnl": xp - entry,
                                       "fill_bars": i - pending["placed"],
                                       "ordinal": fills + 1})
                        pos_until = xi
                        fills += 1
                    pending = None
                    continue
                if day.c[i] < pending["sl"] or i - pending["placed"] >= expiry or i > ENTRY_MAX + 10:
                    pending = None
            if max_fills is not None and fills >= max_fills:
                continue
            if pending is None and i >= 2 and ENTRY_MIN <= i + 1 <= ENTRY_MAX:
                if day.l[i] > day.h[i - 2]:
                    mid = round((day.l[i] + day.h[i - 2]) / 2, 2)
                    sl = round(day.l[i - 2] - 0.02, 2)
                    if band and not (band[0] <= mid - sl <= band[1]):
                        continue
                    pending = {"px": mid, "sl": sl, "placed": i}
    return trades


if __name__ == "__main__":
    main()
