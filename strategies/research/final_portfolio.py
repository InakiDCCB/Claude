"""Final playbook portfolio over 32 sessions with definitive configs."""
import json
from pathlib import Path
from backtest import stats, rsi2_dip, vwap_pullback, sweep_reclaim, gap_fill, LEVEL_FNS
from analysis_30d import build_days, day_context, run_market_meta, run_fvg_meta2


def main():
    all_days, dates = build_days()
    days = [d for d in all_days if d.date >= "2026-04-27"]
    LEVEL_FNS.update({"VPOC": lambda day: [day.y_vpoc]})
    ctx = {d.date: day_context(d) for d in days}

    # final configs
    base_rsi2 = rsi2_dip(0.5, thresh=15, sl_mult=1.0)()

    def rsi2_final(day, i):
        if day.y_val is not None and day.o[0] < day.y_val:
            return None
        return base_rsi2(day, i)

    comp = {
        "RSI2": run_market_meta(days, rsi2_final, c4=True),
        "FVG1": run_fvg_meta2(days, None, 1, 60),
        "VWAPPB": run_market_meta(days, vwap_pullback(45, 65)(), c4=True),
        "SWP": run_market_meta(days, sweep_reclaim(("r", 0.5))(), c4=False),
        "GAPF": run_market_meta(days, gap_fill()(), c4=False),
    }
    print("COMPONENTS (final configs, 32 sessions):")
    for nm, ts in comp.items():
        s = stats(ts)
        print(f"  {nm:<7} n={s['n']:>3} hit={s['hit']:5.1f}% pnl={s['pnl']:>+7.2f} "
              f"mean={s['mean']:+.3f}±{s['se']:.3f} PF={s['pf']:4.2f} mLL={s['mll']}")

    # selector rules
    def included(nm, d):
        c = ctx[d]
        if nm == "RSI2" or nm == "FVG1" or nm == "SWP":
            return True
        if nm == "VWAPPB":
            return c["xvwap60"] >= 6
        if nm == "GAPF":
            return c.get("gap_pct", 0) < -0.3
        return False

    port = []
    for nm, ts in comp.items():
        port.extend([dict(t, sys=nm) for t in ts if included(nm, t["day"])])
    port.sort(key=lambda t: (t["day"], t["ei"]))
    s = stats(port)
    print(f"\nPORTFOLIO: n={s['n']} hit={s['hit']:.1f}% pnl={s['pnl']:+.2f}/sh "
          f"mean={s['mean']:+.3f}±{s['se']:.3f} PF={s['pf']:.2f} mLL={s['mll']}")

    daily = {}
    for t in port:
        daily.setdefault(t["day"], []).append(t)
    pos_days = sum(1 for v in daily.values() if sum(t["pnl"] for t in v) > 0)
    neg = [(d, sum(t["pnl"] for t in v)) for d, v in daily.items()]
    neg.sort(key=lambda x: x[1])
    print(f"days traded={len(daily)}/32 | days positive={pos_days} | "
          f"worst 3: {[(d, round(p, 2)) for d, p in neg[:3]]}")
    avg_tpd = s["n"] / len(daily)
    print(f"avg trades/day={avg_tpd:.1f}")

    # contribution per system inside portfolio
    print("\nPER-SYSTEM inside portfolio:")
    for nm in comp:
        ts = [t for t in port if t["sys"] == nm]
        if ts:
            s2 = stats(ts)
            print(f"  {nm:<7} n={s2['n']:>3} hit={s2['hit']:5.1f}% pnl={s2['pnl']:>+7.2f} PF={s2['pf']:4.2f}")

    # walk-forward of the full portfolio
    for label, lo, hi in (("TUNE<=05-22", "0000-00-00", "2026-05-22"),
                          ("TEST>=05-26", "2026-05-26", "9999-99-99")):
        ts = [t for t in port if lo <= t["day"] <= hi]
        s2 = stats(ts)
        dd = {}
        for t in ts:
            dd[t["day"]] = dd.get(t["day"], 0) + t["pnl"]
        print(f"{label}: n={s2['n']} hit={s2['hit']:.1f}% pnl={s2['pnl']:+.2f} PF={s2['pf']:.2f} "
              f"days+ {sum(1 for v in dd.values() if v > 0)}/{len(dd)}")

    # concurrency check (overlapping positions)
    print("\nMax concurrent positions:")
    mx = 0
    for d, v in daily.items():
        evs = []
        for t in v:
            dur = t.get("bars_held", 5)
            evs.append((t["ei"], 1))
            evs.append((t["ei"] + max(dur, 1), -1))
        evs.sort()
        cur = 0
        for _, e in evs:
            cur += e
            mx = max(mx, cur)
    print(f"  max_concurrent={mx}")


if __name__ == "__main__":
    main()
