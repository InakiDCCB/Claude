"""Backtest QQQ SHORT-side intraday systems — exact mirror of the LONG playbook.

Purpose: measure whether the v3.0 edge is symmetric on the short side, so we know if
enabling shorts (user decision 2026-06-16) is justified before touching cycle_prompt.

Design: reuses the direction-neutral `Day` precompute from backtest.py. Mirrors the
fill/exit engine (SL ABOVE entry, TP BELOW, short pnl = entry - exit) and each of the 5
live/shadow systems into its bearish twin:

  LONG signal                          ->  SHORT mirror
  ------------------------------------------------------------------
  FVG  gap UP (low[i] > high[i-2])      ->  gap DOWN (high[i] < low[i-2]), short the midpoint
  VWAPPB pullback to VWAP from above    ->  rally-rejection at VWAP from below
  RSI2(5m) < thr  (oversold dip)        ->  RSI2(5m) > 100-thr (overbought pop)
  SWP sweep session LOW + reclaim       ->  sweep session HIGH + rejection
  GAPF gap-down -> reclaim EMA9, tp=pdc ->  gap-up -> lose EMA9, fade to pdc

Conservative fills identical to LONG engine: signal on sealed bar -> entry next bar open;
SL before TP intra-bar; forced close 15:55 ET. C4 = 2 consecutive losers -> system off.
"""
import json
from pathlib import Path

from backtest import Day, stats, ENTRY_MIN, ENTRY_MAX, FORCED, run_fvg, run_market, \
    rsi2_dip, vwap_pullback, sweep_reclaim, gap_fill

DATA = Path(__file__).parent / "data" / "qqq_1min.json"


# ---------------- mirrored fill/exit engine ----------------

def simulate_short(day, entry_i, entry_px, sl, tp_spec, time_stop=None):
    """Mirror of backtest.simulate. SL is ABOVE entry; profit when price falls."""
    risk = sl - entry_px
    tp_abs = None
    if tp_spec[0] == "r":
        tp_abs = entry_px - tp_spec[1] * risk
    elif tp_spec[0] == "abs":
        tp_abs = tp_spec[1]
    for j in range(entry_i, min(day.n, FORCED + 1)):
        op = entry_px if j == entry_i else day.o[j]
        if j >= FORCED:
            return j, day.o[j], "TIME"
        if day.h[j] >= sl:                       # SL first (intra-bar, conservative)
            return j, (op if op >= sl else sl), "SL"
        tp = tp_abs
        if tp_spec[0] == "vwap":
            tp = day.vwap[j] if day.vwap[j] and day.vwap[j] < entry_px else None
        if tp is not None and day.l[j] <= tp:
            return j, (op if op <= tp else tp), "TP"
        if tp_spec[0] == "fpc" and j > entry_i and day.c[j] < entry_px:
            return j, day.c[j], "TP"
        if time_stop is not None and j - entry_i >= time_stop:
            return j, day.c[j], "TIME"
    j = day.n - 1
    return j, day.c[j], "TIME"


def run_market_short(days, signal_fn, c4=False):
    trades = []
    for day in days:
        pos_until = -1
        consec_sl = 0
        for i in range(day.n - 1):
            e = i + 1
            if not (ENTRY_MIN <= e <= ENTRY_MAX) or e <= pos_until:
                continue
            if c4 and consec_sl >= 2:
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
                sl = entry + sig["sl_atr"] * a
            sl = round(sl, 2)
            if sl <= entry:
                continue
            tp = sig["tp"]
            if tp[0] == "atrx":                  # entry - mult * given_atr
                tp = ("abs", round(entry - tp[1] * tp[2], 2))
            xi, xp, xt = simulate_short(day, e, entry, sl, tp, sig.get("time_stop"))
            pnl = entry - xp
            trades.append({"day": day.date, "ei": e, "entry": entry, "sl": sl,
                           "xi": xi, "xp": xp, "xt": xt, "pnl": pnl})
            pos_until = xi
            consec_sl = consec_sl + 1 if pnl <= 0 else 0
    return trades


def run_fvg_short(days, filter_fn=None, c4=False, expiry=60, max_fills=None):
    """Mirror of run_fvg: bearish FVG (high[i] < low[i-2]); short the midpoint on a rally
    back up into the gap; SL above the gap; tp = 2R below."""
    trades = []
    for day in days:
        pending = None
        pos_until = -1
        consec_sl = 0
        fills = 0
        for i in range(day.n):
            if i <= pos_until:
                pending = None
                continue
            if pending is not None:
                if day.h[i] >= pending["px"]:    # price rallies up into midpoint -> short fill
                    entry = max(day.o[i], pending["px"])
                    sl = pending["sl"]
                    if sl > entry:
                        xi, xp, xt = simulate_short(day, i, entry, sl, ("r", 2.0))
                        pnl = entry - xp
                        trades.append({"day": day.date, "ei": i, "entry": entry, "sl": sl,
                                       "xi": xi, "xp": xp, "xt": xt, "pnl": pnl})
                        pos_until = xi
                        consec_sl = consec_sl + 1 if pnl <= 0 else 0
                        fills += 1
                    pending = None
                    continue
                if day.c[i] > pending["sl"] or i - pending["placed"] >= expiry or i > ENTRY_MAX + 10:
                    pending = None
            if c4 and consec_sl >= 2:
                continue
            if max_fills is not None and fills >= max_fills:
                continue
            if pending is None and i >= 2 and ENTRY_MIN <= i + 1 <= ENTRY_MAX:
                if day.h[i] < day.l[i - 2]:       # gap DOWN (bearish FVG)
                    if filter_fn is not None and not filter_fn(day, i):
                        continue
                    mid = round((day.h[i] + day.l[i - 2]) / 2, 2)
                    sl = round(day.h[i - 2] + 0.02, 2)
                    pending = {"px": mid, "sl": sl, "placed": i}
    return trades


# ---------------- mirrored system factories ----------------

def rsi2_pop(tp_mode, thresh=85, sl_mult=1.0, time_stop=45, require_below_pdh=False):
    """Mirror of rsi2_dip: short when RSI2(5m) > thresh (overbought pop)."""
    def factory():
        def fn(day, i):
            if (i + 1) % 5 != 0:
                return None
            k = (i + 1) // 5 - 1
            if k < 15 or day.f_rsi2[k] is None or day.f_rsi2[k] <= thresh or day.f_atr[k] is None:
                return None
            if require_below_pdh and (day.pdh is None or day.c[i] >= day.pdh):
                return None
            a5 = day.f_atr[k]
            tp = ("fpc",) if tp_mode == "fpc" else ("atrx", tp_mode, a5)
            return {"sl_atr": sl_mult, "atr5": a5, "tp": tp, "time_stop": time_stop}
        return fn
    return factory


def vwap_rejection(rsi_lo, rsi_hi, tp=("r", 1.0)):
    """Mirror of vwap_pullback: price below VWAP, rallies up to touch it, red bar -> short."""
    def factory():
        def fn(day, i):
            if i < 15 or day.rsi14[i] is None or day.atr[i] is None:
                return None
            if day.c[i] >= day.vwap[i] or day.h[i] < day.vwap[i] * 0.999:
                return None                       # must close below VWAP & have tagged it from below
            if day.c[i] >= day.o[i] or not (rsi_lo <= day.rsi14[i] <= rsi_hi):
                return None                       # red bar, rsi in band
            return {"sl_atr": 2.0, "tp": tp}
        return fn
    return factory


def sweep_rejection(tp, min_depth=0.01, within=3):
    """Mirror of sweep_reclaim: sweep session HIGH then reject (red bar, volume) -> short."""
    def factory():
        def fn(day, i):
            if i < 5 or day.avgv5[i] is None:
                return None
            for j in range(max(1, i - within), i):
                ph = day.prev_high[j]
                if ph is None or day.h[j] <= ph + min_depth:
                    continue
                sweep_high = max(day.h[j:i + 1])
                if day.c[i] < ph and day.v[i] >= 1.5 * day.avgv5[i] and day.c[i] < day.o[i]:
                    return {"sl_abs": round(sweep_high + 0.05, 2), "tp": tp}
            return None
        return fn
    return factory


def gap_fade(min_gap=0.003):
    """Mirror of gap_fill: gap UP >= 0.3%, lose EMA9 from above while still > pdc -> short to pdc."""
    def factory():
        fired = set()

        def fn(day, i):
            if day.pdc is None or day.date in fired or i < ENTRY_MIN:
                return None
            if (day.o[0] - day.pdc) / day.pdc < min_gap:      # require gap UP
                return None
            if day.ema9[i] is None or day.c[i] >= day.ema9[i] or day.c[i] <= day.pdc:
                return None                                    # closed below EMA9 but still above pdc
            fired.add(day.date)
            return {"sl_abs": round(max(day.h[:i + 1]) + 0.10, 2), "tp": ("abs", day.pdc)}
        return fn
    return factory


# ---------------- driver ----------------

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
    return [days_all[d] for d in dates if d >= "2026-06-01"]


def day_trend(day):
    """Classify the session by close-vs-open and where close sits vs VWAP."""
    ret = (day.c[-1] - day.o[0]) / day.o[0] * 100
    return ret


def main():
    days = build_days()
    print(f"Sessions: {len(days)} ({days[0].date} -> {days[-1].date})\n")

    # final LONG configs (from final_portfolio.py) for side-by-side reference
    _rsi2_long_base = rsi2_dip(0.5, thresh=15, sl_mult=1.0)()

    def rsi2_long_final(day, i):
        if day.y_val is not None and day.o[0] < day.y_val:
            return None
        return _rsi2_long_base(day, i)

    _rsi2_short_base = rsi2_pop(0.5, thresh=85, sl_mult=1.0)()

    def rsi2_short_final(day, i):
        # mirror gate: skip if open above yesterday VAH (mirror of LONG "open below VAL")
        if day.y_vah is not None and day.o[0] > day.y_vah:
            return None
        return _rsi2_short_base(day, i)

    print("=== SYSTEM-BY-SYSTEM: LONG (actual playbook) vs SHORT (mirror) ===")
    print(f"{'system':<10}{'side':<7}{'N':>4}{'HIT%':>7}{'PnL/sh':>9}{'mean':>8}{'PF':>6}{'mLL':>4}")

    def line(nm, side, ts):
        s = stats(ts)
        if s is None:
            print(f"{nm:<10}{side:<7}{'0':>4}")
            return None
        pf = f"{s['pf']:.2f}" if s['pf'] != float('inf') else "inf"
        print(f"{nm:<10}{side:<7}{s['n']:>4}{s['hit']:>7.1f}{s['pnl']:>+9.2f}"
              f"{s['mean']:>+8.3f}{pf:>6}{s['mll']:>4}")
        return s

    pairs = [
        ("RSI2", run_market(days, rsi2_long_final, c4=True),
                 run_market_short(days, rsi2_short_final, c4=True)),
        ("FVG_f2", run_fvg(days, None, False, max_fills=2),
                   run_fvg_short(days, None, False, max_fills=2)),
        ("VWAPPB", run_market(days, vwap_pullback(45, 65)(), c4=True),
                   run_market_short(days, vwap_rejection(35, 55)(), c4=True)),
        ("SWP", run_market(days, sweep_reclaim(("r", 0.5))(), c4=False),
                run_market_short(days, sweep_rejection(("r", 0.5))(), c4=False)),
        ("GAPF", run_market(days, gap_fill()(), c4=False),
                 run_market_short(days, gap_fade()(), c4=False)),
    ]
    short_all = {}
    long_all = {}
    for nm, tl, tsh in pairs:
        line(nm, "LONG", tl)
        s = line(nm, "SHORT", tsh)
        print()
        short_all[nm] = tsh
        long_all[nm] = tl

    # RSI2 short threshold/sl grid (mirror of the LONG calibration)
    print("=== RSI2-SHORT grid (overbought pop) hit%/pnl/N  [base | C4] ===")
    for th in (85, 90, 95):
        ln = f"  th>{th:<3}"
        for tpm in (0.4, 0.5, 0.6):
            t = run_market_short(days, rsi2_pop(tpm, thresh=th, sl_mult=1.0)(), False)
            t4 = run_market_short(days, rsi2_pop(tpm, thresh=th, sl_mult=1.0)(), True)
            s, s4 = stats(t), stats(t4)
            if s and s4:
                ln += f"  tp{tpm}:{s['hit']:5.1f} {s['pnl']:+6.2f} {s['n']:>3} |{s4['hit']:5.1f} {s4['pnl']:+6.2f}"
            else:
                ln += f"  tp{tpm}:    -      -   0 |    -      -"
        print(ln)
    print()

    # per-day: session return vs short-portfolio pnl (does the edge live on down days?)
    print("=== PER-DAY: session return vs SHORT-side total pnl ===")
    print(f"{'day':<12}{'sess_ret%':>10}{'short_pnl':>11}{'short_n':>9}{'long_pnl':>10}")
    short_by_day = {}
    long_by_day = {}
    for nm, ts in short_all.items():
        for t in ts:
            short_by_day.setdefault(t["day"], []).append(t["pnl"])
    for nm, ts in long_all.items():
        for t in ts:
            long_by_day.setdefault(t["day"], []).append(t["pnl"])
    down_pnl = up_pnl = 0.0
    down_n = up_n = 0
    for day in days:
        ret = day_trend(day)
        sp = sum(short_by_day.get(day.date, []))
        sn = len(short_by_day.get(day.date, []))
        lp = sum(long_by_day.get(day.date, []))
        print(f"{day.date:<12}{ret:>+10.2f}{sp:>+11.2f}{sn:>9}{lp:>+10.2f}")
        if ret < -0.3:
            down_pnl += sp; down_n += sn
        elif ret > 0.3:
            up_pnl += sp; up_n += sn
    print(f"\nSHORT on DOWN days (ret<-0.3%): pnl={down_pnl:+.2f} n={down_n}")
    print(f"SHORT on UP days   (ret>+0.3%): pnl={up_pnl:+.2f} n={up_n}")

    # aggregate short portfolio
    port = []
    for nm, ts in short_all.items():
        port.extend(ts)
    s = stats(port)
    if s:
        print(f"\nSHORT PORTFOLIO (all systems, no selector): n={s['n']} hit={s['hit']:.1f}% "
              f"pnl={s['pnl']:+.2f}/sh mean={s['mean']:+.3f}±{s['se']:.3f} PF={s['pf']:.2f} mLL={s['mll']}")
    lport = []
    for nm, ts in long_all.items():
        lport.extend(ts)
    sl = stats(lport)
    if sl:
        print(f"LONG  PORTFOLIO (same systems/period):       n={sl['n']} hit={sl['hit']:.1f}% "
              f"pnl={sl['pnl']:+.2f}/sh mean={sl['mean']:+.3f}±{sl['se']:.3f} PF={sl['pf']:.2f} mLL={sl['mll']}")


if __name__ == "__main__":
    main()
