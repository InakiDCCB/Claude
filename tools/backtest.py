"""Backtest QQQ long-only intraday systems on 1-min SIP bars (2026-06-01..06-10).
Round 2: fresh-closure factories (no state leak), exit redesign for high-hit families,
combined key levels, FVG outcome cross-tab.
Conservative fills: signal on sealed bar -> entry next bar open; SL before TP intra-bar;
forced close 15:55 ET.
"""
import json
import math
from pathlib import Path

DATA = Path(__file__).parent / "data" / "qqq_1min.json"
ENTRY_MIN, ENTRY_MAX = 30, 375   # 10:00-15:45 ET
FORCED = 385                     # 15:55 ET


def wilder_rsi(closes, n):
    rsi = [None] * len(closes)
    if len(closes) < n + 1:
        return rsi
    gains = losses = 0.0
    for k in range(1, n + 1):
        d = closes[k] - closes[k - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n
    rsi[n] = 100 - 100 / (1 + (ag / al if al else 1e9))
    for k in range(n + 1, len(closes)):
        d = closes[k] - closes[k - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        rsi[k] = 100 - 100 / (1 + (ag / al if al else 1e9))
    return rsi


def wilder_atr(h, l, c, n=14):
    m = len(c)
    atr = [None] * m
    trs = [h[0] - l[0]] + [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1]))
                           for k in range(1, m)]
    if m <= n:
        return atr
    a = sum(trs[1:n + 1]) / n
    atr[n] = a
    for k in range(n + 1, m):
        a = (a * (n - 1) + trs[k]) / n
        atr[k] = a
    return atr


def ema(closes, n):
    out = [None] * len(closes)
    if len(closes) < n:
        return out
    s = sum(closes[:n]) / n
    out[n - 1] = s
    k = 2 / (n + 1)
    for i in range(n, len(closes)):
        s = closes[i] * k + s * (1 - k)
        out[i] = s
    return out


class Day:
    def __init__(self, date, bars, prev=None):
        self.date = date
        self.o = [b["o"] for b in bars]
        self.h = [b["h"] for b in bars]
        self.l = [b["l"] for b in bars]
        self.c = [b["c"] for b in bars]
        self.v = [b["v"] for b in bars]
        n = len(bars)
        self.n = n
        sv = spv = sp2v = 0.0
        self.vwap = [None] * n
        self.sigma = [None] * n
        for i in range(n):
            tp = (self.h[i] + self.l[i] + self.c[i]) / 3
            sv += self.v[i]; spv += tp * self.v[i]; sp2v += tp * tp * self.v[i]
            m = spv / sv
            self.vwap[i] = m
            self.sigma[i] = math.sqrt(max(sp2v / sv - m * m, 0.0))
        self.ema9 = ema(self.c, 9)
        self.rsi14 = wilder_rsi(self.c, 14)
        self.atr = wilder_atr(self.h, self.l, self.c, 14)
        self.avgv20 = [None] * n
        self.avgv5 = [None] * n
        for i in range(n):
            if i >= 20:
                self.avgv20[i] = sum(self.v[i - 20:i]) / 20
            if i >= 5:
                self.avgv5[i] = sum(self.v[i - 5:i]) / 5
        self.prev_low = [None] * n
        self.prev_high = [None] * n
        lo, hi = float("inf"), float("-inf")
        for i in range(n):
            self.prev_low[i] = lo if lo != float("inf") else None
            self.prev_high[i] = hi if hi != float("-inf") else None
            lo = min(lo, self.l[i]); hi = max(hi, self.h[i])
        self.or_high = max(self.h[:30]); self.or_low = min(self.l[:30])
        f_h, f_l, f_c = [], [], []
        for k in range(0, n - 4, 5):
            f_h.append(max(self.h[k:k + 5]))
            f_l.append(min(self.l[k:k + 5]))
            f_c.append(self.c[k + 4])
        self.f_h, self.f_l, self.f_c = f_h, f_l, f_c
        self.f_rsi2 = wilder_rsi(f_c, 2)
        self.f_atr = wilder_atr(f_h, f_l, f_c, 14)
        if prev is not None:
            pv = sum((prev.h[i] + prev.l[i] + prev.c[i]) / 3 * prev.v[i] for i in range(prev.n))
            vw = pv / sum(prev.v)
            ph, pl = max(prev.h), min(prev.l)
            self.y_vpoc = vw
            self.y_vah = vw + 0.34 * (ph - pl)
            self.y_val = vw - 0.34 * (ph - pl)
            self.pdh, self.pdl, self.pdc = ph, pl, prev.c[-1]
        else:
            self.y_vpoc = self.y_vah = self.y_val = self.pdh = self.pdl = self.pdc = None
        self.slope30 = [None] * n
        for i in range(30, n):
            self.slope30[i] = self.vwap[i] - self.vwap[i - 30]


def simulate(day, entry_i, entry_px, sl, tp_spec, be_at_r=None, time_stop=None):
    risk = entry_px - sl
    tp_abs = None
    if tp_spec[0] == "r":
        tp_abs = entry_px + tp_spec[1] * risk
    elif tp_spec[0] == "abs":
        tp_abs = tp_spec[1]
    cur_sl = sl
    for j in range(entry_i, min(day.n, FORCED + 1)):
        op = entry_px if j == entry_i else day.o[j]
        if j >= FORCED:
            return j, day.o[j], "TIME"
        if day.l[j] <= cur_sl:
            return j, (op if op <= cur_sl else cur_sl), "SL"
        tp = tp_abs
        if tp_spec[0] == "vwap":
            tp = day.vwap[j] if day.vwap[j] and day.vwap[j] > entry_px else None
        if tp is not None and day.h[j] >= tp:
            return j, (op if op >= tp else tp), "TP"
        if tp_spec[0] == "fpc" and j > entry_i and day.c[j] > entry_px:
            return j, day.c[j], "TP"
        if time_stop is not None and j - entry_i >= time_stop:
            return j, day.c[j], "TIME"
        if be_at_r is not None and day.h[j] >= entry_px + be_at_r * risk:
            cur_sl = max(cur_sl, entry_px)
    j = day.n - 1
    return j, day.c[j], "TIME"


def run_market(days, signal_fn, c4=False):
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
                sl = entry - sig["sl_atr"] * a
            sl = round(sl, 2)
            if sl >= entry:
                continue
            tp = sig["tp"]
            if tp[0] == "atrx":          # entry + mult * given_atr
                tp = ("abs", round(entry + tp[1] * tp[2], 2))
            xi, xp, xt = simulate(day, e, entry, sl, tp, sig.get("be_at_r"), sig.get("time_stop"))
            pnl = xp - entry
            trades.append({"day": day.date, "ei": e, "entry": entry, "sl": sl,
                           "xi": xi, "xp": xp, "xt": xt, "pnl": pnl})
            pos_until = xi
            consec_sl = consec_sl + 1 if pnl <= 0 else 0
    return trades


def run_fvg(days, filter_fn=None, c4=False, expiry=60, collect_meta=None, max_fills=None):
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
                if day.l[i] <= pending["px"]:
                    entry = min(day.o[i], pending["px"])
                    sl = pending["sl"]
                    if sl < entry:
                        xi, xp, xt = simulate(day, i, entry, sl, ("r", 2.0))
                        pnl = xp - entry
                        tr = {"day": day.date, "ei": i, "entry": entry, "sl": sl,
                              "xi": xi, "xp": xp, "xt": xt, "pnl": pnl}
                        tr.update(pending.get("meta", {}))
                        trades.append(tr)
                        pos_until = xi
                        consec_sl = consec_sl + 1 if pnl <= 0 else 0
                        fills += 1
                    pending = None
                    continue
                if day.c[i] < pending["sl"] or i - pending["placed"] >= expiry or i > ENTRY_MAX + 10:
                    pending = None
            if c4 and consec_sl >= 2:
                continue
            if max_fills is not None and fills >= max_fills:
                continue
            if pending is None and i >= 2 and ENTRY_MIN <= i + 1 <= ENTRY_MAX:
                if day.l[i] > day.h[i - 2]:
                    if filter_fn is not None and not filter_fn(day, i):
                        continue
                    mid = round((day.l[i] + day.h[i - 2]) / 2, 2)
                    sl = round(day.l[i - 2] - 0.02, 2)
                    meta = {}
                    if collect_meta:
                        meta = {"slope_up": day.slope30[i] is not None and day.slope30[i] > 0,
                                "above_vwap": day.c[i] > day.vwap[i],
                                "risk": round(mid - sl, 2),
                                "hour_et": 9.5 + (i / 60.0)}
                    pending = {"px": mid, "sl": sl, "placed": i, "meta": meta}
    return trades


# ---------------- system factories (fresh state per run) ----------------

def make_level_bounce(level_key, buffer_sl=0.10, tp=("vwap",), upper_frac=0.5,
                      cooldown=10, be_at_r=None):
    def factory():
        last_sig = {}

        def fn(day, i):
            levels = LEVEL_FNS[level_key](day)
            rng = day.h[i] - day.l[i]
            if not levels or rng <= 0:
                return None
            for lvv in levels:
                if lvv is None:
                    continue
                key = round(lvv, 2)
                if day.l[i] < lvv and day.c[i] > lvv and (day.c[i] - day.l[i]) / rng >= upper_frac:
                    if key in last_sig and i - last_sig[key] < cooldown:
                        continue
                    last_sig[key] = i
                    return {"sl_abs": round(min(day.l[i], lvv) - buffer_sl, 2),
                            "tp": tp, "be_at_r": be_at_r}
            return None
        return fn
    return factory


def sweep_reclaim(tp, min_depth=0.01, within=3):
    def factory():
        def fn(day, i):
            if i < 5 or day.avgv5[i] is None:
                return None
            for j in range(max(1, i - within), i):
                pl = day.prev_low[j]
                if pl is None or day.l[j] >= pl - min_depth:
                    continue
                sweep_low = min(day.l[j:i + 1])
                if day.c[i] > pl and day.v[i] >= 1.5 * day.avgv5[i] and day.c[i] > day.o[i]:
                    return {"sl_abs": round(sweep_low - 0.05, 2), "tp": tp}
            return None
        return fn
    return factory


def rsi2_dip(tp_mode, thresh=10, sl_mult=2.0, time_stop=45, require_above_pdl=False):
    def factory():
        def fn(day, i):
            if (i + 1) % 5 != 0:
                return None
            k = (i + 1) // 5 - 1
            if k < 15 or day.f_rsi2[k] is None or day.f_rsi2[k] >= thresh or day.f_atr[k] is None:
                return None
            if require_above_pdl and (day.pdl is None or day.c[i] <= day.pdl):
                return None
            a5 = day.f_atr[k]
            tp = ("fpc",) if tp_mode == "fpc" else ("atrx", tp_mode, a5)
            return {"sl_atr": sl_mult, "atr5": a5, "tp": tp, "time_stop": time_stop}
        return fn
    return factory


def ibs_5m(tp_mode, thresh=0.15, sl_mult=2.0, time_stop=45):
    def factory():
        def fn(day, i):
            if (i + 1) % 5 != 0:
                return None
            k = (i + 1) // 5 - 1
            if k < 15 or day.f_atr[k] is None:
                return None
            rng = day.f_h[k] - day.f_l[k]
            if rng <= 0 or rng < day.f_atr[k]:
                return None
            if (day.f_c[k] - day.f_l[k]) / rng >= thresh:
                return None
            a5 = day.f_atr[k]
            tp = ("fpc",) if tp_mode == "fpc" else ("atrx", tp_mode, a5)
            return {"sl_atr": sl_mult, "atr5": a5, "tp": tp, "time_stop": time_stop}
        return fn
    return factory


def red_run(tp, run_len=5):
    def factory():
        def fn(day, i):
            if i < run_len + 1 or day.avgv20[i] is None:
                return None
            if not (day.c[i] > day.o[i] and day.v[i] >= day.avgv20[i]):
                return None
            for k in range(i - run_len, i):
                if day.c[k] >= day.o[k]:
                    return None
            return {"sl_abs": round(min(day.l[i - run_len:i + 1]) - 0.05, 2), "tp": tp}
        return fn
    return factory


def vol_climax(tp):
    def factory():
        def fn(day, i):
            if day.avgv20[i] is None or day.atr[i] is None:
                return None
            rng = day.h[i] - day.l[i]
            if rng < day.atr[i] or day.v[i] < 4 * day.avgv20[i]:
                return None
            if min(day.o[i], day.c[i]) - day.l[i] < 0.55 * rng:
                return None
            if (day.c[i] - day.l[i]) / rng < 0.5:
                return None
            return {"sl_abs": round(day.l[i] - 0.05, 2), "tp": tp}
        return fn
    return factory


def ema9_reclaim(tp):
    def factory():
        def fn(day, i):
            if i < 31 or day.ema9[i] is None or day.ema9[i - 1] is None or day.slope30[i] is None:
                return None
            if day.slope30[i] <= 0 or day.c[i] <= day.vwap[i]:
                return None
            if day.c[i - 1] < day.ema9[i - 1] and day.c[i] > day.ema9[i] and day.atr[i]:
                return {"sl_atr": 2.0, "tp": tp}
            return None
        return fn
    return factory


def gap_fill(min_gap=-0.003):
    def factory():
        fired = set()

        def fn(day, i):
            if day.pdc is None or day.date in fired or i < ENTRY_MIN:
                return None
            if (day.o[0] - day.pdc) / day.pdc > min_gap:
                return None
            if day.ema9[i] is None or day.c[i] <= day.ema9[i] or day.c[i] >= day.pdc:
                return None
            fired.add(day.date)
            return {"sl_abs": round(min(day.l[:i + 1]) - 0.10, 2), "tp": ("abs", day.pdc)}
        return fn
    return factory


def vwap_pullback(rsi_lo, rsi_hi, tp=("r", 1.0), be_at_r=None):
    def factory():
        def fn(day, i):
            if i < 15 or day.rsi14[i] is None or day.atr[i] is None:
                return None
            if day.c[i] <= day.vwap[i] or day.l[i] > day.vwap[i] * 1.001:
                return None
            if day.c[i] <= day.o[i] or not (rsi_lo <= day.rsi14[i] <= rsi_hi):
                return None
            return {"sl_atr": 2.0, "tp": tp, "be_at_r": be_at_r}
        return fn
    return factory


def vwap_band(mult, tp):
    def factory():
        def fn(day, i):
            if i < 21 or day.sigma[i] is None or day.sigma[i] < 0.05:
                return None
            lb_prev = day.vwap[i - 1] - mult * day.sigma[i - 1]
            lb = day.vwap[i] - mult * day.sigma[i]
            if day.c[i - 1] < lb_prev and day.c[i] > lb:
                return {"sl_abs": round(min(day.l[i - 1], day.l[i]) - 0.05, 2), "tp": tp}
            return None
        return fn
    return factory


LEVEL_FNS = {}


def stats(trades):
    n = len(trades)
    if n == 0:
        return None
    wins = [t for t in trades if t["pnl"] > 0]
    pnl = sum(t["pnl"] for t in trades)
    aw = sum(t["pnl"] for t in wins) / len(wins) if wins else 0.0
    ls = [t for t in trades if t["pnl"] <= 0]
    al = sum(t["pnl"] for t in ls) / len(ls) if ls else 0.0
    gw = sum(t["pnl"] for t in wins)
    gl = -sum(t["pnl"] for t in ls)
    pf = gw / gl if gl > 0 else float("inf")
    mll = cur = 0
    for t in trades:
        cur = cur + 1 if t["pnl"] <= 0 else 0
        mll = max(mll, cur)
    mean = pnl / n
    var = sum((t["pnl"] - mean) ** 2 for t in trades) / n if n > 1 else 0.0
    se = math.sqrt(var / n) if n > 1 else 0.0
    return {"n": n, "w": len(wins), "hit": 100 * len(wins) / n, "pnl": pnl,
            "aw": aw, "al": al, "pf": pf, "mll": mll, "mean": mean, "se": se}


def main():
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
    # prior-3-day vwaps as naked-POC proxies
    for idx, d in enumerate(dates):
        day = days_all[d]
        vws = []
        for pd_ in dates[max(0, idx - 3):idx]:
            p = days_all[pd_]
            vws.append(sum((p.h[i] + p.l[i] + p.c[i]) / 3 * p.v[i] for i in range(p.n)) / sum(p.v))
        day.prior3_vw = vws
    days = [days_all[d] for d in dates if d >= "2026-06-01"]

    def sup_levels(day):
        raw = [day.y_val, day.y_vpoc, day.pdl, day.pdc] + list(day.prior3_vw)
        raw = sorted(x for x in raw if x is not None)
        out = []
        for x in raw:
            if not out or x - out[-1] > 0.30:
                out.append(x)
        return out

    LEVEL_FNS.update({
        "VAL": lambda day: [day.y_val],
        "VPOC": lambda day: [day.y_vpoc],
        "PDL": lambda day: [day.pdl],
        "PDC": lambda day: [day.pdc],
        "KEY": lambda day: [day.y_val, day.y_vpoc, day.pdl, day.pdc],
        "Y3VW": lambda day: day.prior3_vw,
        "SUP": sup_levels,
    })

    def fvg_risk_filter(day, i):
        mid = (day.l[i] + day.h[i - 2]) / 2
        return 0.50 <= mid - (day.l[i - 2] - 0.02) <= 1.00

    systems = [
        ("FVG_v29_base", lambda c4: run_fvg(days, None, c4, collect_meta=True)),
        ("FVG_C1_trend", lambda c4: run_fvg(
            days, lambda day, i: day.slope30[i] is not None and day.slope30[i] > 0
            and day.c[i] > day.vwap[i], c4)),
        ("FVG_first1", lambda c4: run_fvg(days, None, c4, max_fills=1)),
        ("FVG_first2", lambda c4: run_fvg(days, None, c4, max_fills=2)),
        ("FVG_first3", lambda c4: run_fvg(days, None, c4, max_fills=3)),
        ("FVG_r0510", lambda c4: run_fvg(days, fvg_risk_filter, c4)),
        ("FVG_f2_r0510", lambda c4: run_fvg(days, fvg_risk_filter, c4, max_fills=2)),
    ]
    factories = [
        ("VWAPPB_45_65", vwap_pullback(45, 65)),
        ("VWAPPB_be05", vwap_pullback(45, 65, tp=("r", 1.0), be_at_r=0.5)),
        ("VWAPPB_075R", vwap_pullback(45, 65, tp=("r", 0.75))),
        ("VPOC_b_1R", make_level_bounce("VPOC", tp=("r", 1.0))),
        ("VPOC_b_05R", make_level_bounce("VPOC", tp=("r", 0.5))),
        ("VPOC_b_15R", make_level_bounce("VPOC", tp=("r", 1.5))),
        ("VPOC_b_be05", make_level_bounce("VPOC", tp=("r", 1.0), be_at_r=0.5)),
        ("KEY_b_1R", make_level_bounce("KEY", tp=("r", 1.0))),
        ("KEY_b_05R", make_level_bounce("KEY", tp=("r", 0.5))),
        ("KEY_b_be05", make_level_bounce("KEY", tp=("r", 1.0), be_at_r=0.5)),
        ("Y3VW_b_1R", make_level_bounce("Y3VW", tp=("r", 1.0))),
        ("VAL_b_1R", make_level_bounce("VAL", tp=("r", 1.0))),
        ("PDL_b_1R", make_level_bounce("PDL", tp=("r", 1.0))),
        ("PDC_b_1R", make_level_bounce("PDC", tp=("r", 1.0))),
        ("SWP_fpc", sweep_reclaim(("fpc",))),
        ("SWP_fpc_d30", sweep_reclaim(("fpc",), min_depth=0.30)),
        ("SWP_05R", sweep_reclaim(("r", 0.5))),
        ("SWP_05R_d30", sweep_reclaim(("r", 0.5), min_depth=0.30)),
        ("SWP_1R_d30", sweep_reclaim(("r", 1.0), min_depth=0.30)),
        ("RSI2_fpc", rsi2_dip("fpc")),
        ("RSI2_fpc_pdl", rsi2_dip("fpc", require_above_pdl=True)),
        ("RSI2_fpc_s10", rsi2_dip("fpc", sl_mult=1.0)),
        ("RSI2_fpc_s15", rsi2_dip("fpc", sl_mult=1.5)),
        ("RSI2_t025_s10", rsi2_dip(0.25, sl_mult=1.0)),
        ("RSI2_t05_s10", rsi2_dip(0.5, sl_mult=1.0)),
        ("RSI2_t05_s15", rsi2_dip(0.5, sl_mult=1.5)),
        ("RSI2_t05_s20", rsi2_dip(0.5, sl_mult=2.0)),
        ("RSI2_t10_s20", rsi2_dip(1.0, sl_mult=2.0)),
        ("RSI2_th5_t05", rsi2_dip(0.5, thresh=5, sl_mult=1.5)),
        ("RSI2_th15_t05", rsi2_dip(0.5, thresh=15, sl_mult=1.5)),
        ("RSI2_pdl_t05", rsi2_dip(0.5, sl_mult=1.5, require_above_pdl=True)),
        ("RSI2_fpc_ts15", rsi2_dip("fpc", sl_mult=1.5, time_stop=15)),
        ("IBS_fpc", ibs_5m("fpc")),
        ("IBS_t05_s15", ibs_5m(0.5, sl_mult=1.5)),
        ("IBS_t025_s10", ibs_5m(0.25, sl_mult=1.0)),
        ("RED5_fpc", red_run(("fpc",))),
        ("RED5_05R", red_run(("r", 0.5))),
        ("VCW_vwap", vol_climax(("vwap",))),
        ("E9RC_1R", ema9_reclaim(("r", 1.0))),
        ("E9RC_05R", ema9_reclaim(("r", 0.5))),
        ("GAPFILL", gap_fill()),
        ("VB20_1R", vwap_band(2.0, ("r", 1.0))),
        ("VB20_05R", vwap_band(2.0, ("r", 0.5))),
    ]
    for name, fac in factories:
        systems.append((name, lambda c4, f=fac: run_market(days, f(), c4)))

    rows = []
    detail = {}
    for name, runner in systems:
        t0 = runner(False)
        t4 = runner(True)
        s0, s4 = stats(t0), stats(t4)
        if s0 is None:
            continue
        rows.append((name, s0, s4))
        detail[name] = t0

    rows.sort(key=lambda r: (-r[1]["hit"], -r[1]["n"]))
    print(f"{'SYSTEM':<15}{'N':>4}{'HIT%':>7}{'PnL/sh':>8}{'mean':>7}{'se':>6}{'avgW':>7}"
          f"{'avgL':>7}{'PF':>6}{'mLL':>4} | {'C4:N':>4}{'HIT%':>7}{'PnL':>8}")
    for name, s0, s4 in rows:
        pf_s = f"{s0['pf']:5.2f}" if s0["pf"] != float("inf") else "  inf"
        c4s = f"{s4['n']:>4}{s4['hit']:>7.1f}{s4['pnl']:>8.2f}" if s4 else "   -      -       -"
        print(f"{name:<15}{s0['n']:>4}{s0['hit']:>7.1f}{s0['pnl']:>8.2f}{s0['mean']:>7.3f}"
              f"{s0['se']:>6.3f}{s0['aw']:>7.2f}{s0['al']:>7.2f}{pf_s}{s0['mll']:>4} | {c4s}")

    # FVG cross-tab
    fvg = detail["FVG_v29_base"]
    print("\nFVG cross-tab (N=%d):" % len(fvg))
    def sub(label, pred):
        ts = [t for t in fvg if pred(t)]
        if not ts:
            print(f"  {label:<28} n=0")
            return
        w = sum(1 for t in ts if t["pnl"] > 0)
        p = sum(t["pnl"] for t in ts)
        print(f"  {label:<28} n={len(ts):>3} hit={100*w/len(ts):>5.1f}% pnl={p:>+7.2f}")
    sub("slope_up & above_vwap", lambda t: t.get("slope_up") and t.get("above_vwap"))
    sub("slope_up & below_vwap", lambda t: t.get("slope_up") and not t.get("above_vwap"))
    sub("slope_dn & above_vwap", lambda t: not t.get("slope_up") and t.get("above_vwap"))
    sub("slope_dn & below_vwap", lambda t: not t.get("slope_up") and not t.get("above_vwap"))
    sub("risk < 0.50", lambda t: t.get("risk", 9) < 0.50)
    sub("risk 0.50-1.00", lambda t: 0.50 <= t.get("risk", 9) < 1.00)
    sub("risk >= 1.00", lambda t: t.get("risk", 0) >= 1.00)
    sub("hour < 11", lambda t: t.get("hour_et", 99) < 11)
    sub("hour 11-14", lambda t: 11 <= t.get("hour_et", 99) < 14)
    sub("hour >= 14", lambda t: t.get("hour_et", 0) >= 14)
    sub("risk>=0.5 & slope_up", lambda t: t.get("risk", 0) >= 0.5 and t.get("slope_up"))
    sub("hour<11 & risk 0.5-1", lambda t: t.get("hour_et", 99) < 11 and 0.5 <= t.get("risk", 9) < 1.0)

    # robustness grids
    print("\nLevel-bounce grid (tp=1R) hit%/pnl/N:")
    print(f"{'':>14}" + "".join(f"{'frac=' + str(fr):>20}" for fr in (0.4, 0.5, 0.6)))
    for lvl in ("Y3VW", "SUP"):
        for buf in (0.05, 0.10, 0.15):
            cells = []
            for fr in (0.4, 0.5, 0.6):
                t = run_market(days, make_level_bounce(lvl, buffer_sl=buf, tp=("r", 1.0),
                                                       upper_frac=fr)(), False)
                s = stats(t)
                cells.append(f"{s['hit']:5.1f} {s['pnl']:+6.2f} {s['n']:>3}" if s else "    -      -   0")
            print(f"{lvl:>6} buf={buf:.2f}" + "".join(f"{c:>20}" for c in cells))

    print("\nRSI2 grid (sl=1.0xATR5) hit%/pnl/N  [base | C4]:")
    for th in (5, 10, 15):
        line = f"  th<{th:<3}"
        for tpm in (0.4, 0.5, 0.6):
            t = run_market(days, rsi2_dip(tpm, thresh=th, sl_mult=1.0)(), False)
            t4 = run_market(days, rsi2_dip(tpm, thresh=th, sl_mult=1.0)(), True)
            s, s4 = stats(t), stats(t4)
            line += (f"  tp{tpm}: {s['hit']:4.1f} {s['pnl']:+6.2f} {s['n']:>3}"
                     f" |{s4['hit']:4.1f} {s4['pnl']:+6.2f}")
        print(line)

    # split-sample for shortlist
    short = ["Y3VW_b_1R", "VPOC_b_1R", "KEY_b_1R", "RSI2_t05_s10", "E9RC_05R",
             "IBS_t025_s10", "VWAPPB_45_65", "FVG_first2", "FVG_f2_r0510", "GAPFILL"]
    print("\nSplit-sample (W1=06-01..05 | W2=06-08..10):")
    for nm in short:
        ts = detail.get(nm)
        if not ts:
            continue
        w1 = [t for t in ts if t["day"] <= "2026-06-05"]
        w2 = [t for t in ts if t["day"] >= "2026-06-08"]
        s1, s2 = stats(w1), stats(w2)
        f1 = f"n={s1['n']:>3} hit={s1['hit']:5.1f}% pnl={s1['pnl']:+7.2f}" if s1 else "n=  0"
        f2 = f"n={s2['n']:>3} hit={s2['hit']:5.1f}% pnl={s2['pnl']:+7.2f}" if s2 else "n=  0"
        print(f"  {nm:<14} W1: {f1}   W2: {f2}")

    # per-day for top hit with N>=10 and pnl>0
    sel = [r[0] for r in rows if r[1]["n"] >= 10 and r[1]["pnl"] > 0][:6]
    print("\nPer-day PnL/sh (hit-sorted, N>=10, PnL>0):")
    print("DAY        " + "".join(f"{s[:11]:>13}" for s in sel))
    for d in [dd.date for dd in days]:
        line = f"{d} "
        for s in sel:
            p = sum(t["pnl"] for t in detail[s] if t["day"] == d)
            nn = sum(1 for t in detail[s] if t["day"] == d)
            line += f"{p:>9.2f}({nn:>2})"
        print(line)

    # FVG risk-band sensitivity x max_fills
    print("\nFVG band sensitivity (hit%/pnl/N):")
    for lo, hi in ((0.40, 0.90), (0.40, 1.00), (0.50, 1.00), (0.50, 1.20), (0.60, 1.00)):
        line = f"  band {lo:.2f}-{hi:.2f}"
        for mf in (2, 3):
            def filt(day, i, lo=lo, hi=hi):
                mid = (day.l[i] + day.h[i - 2]) / 2
                return lo <= mid - (day.l[i - 2] - 0.02) <= hi
            s = stats(run_fvg(days, filt, False, max_fills=mf))
            line += (f"   f{mf}: {s['hit']:5.1f} {s['pnl']:+7.2f} {s['n']:>3}" if s
                     else f"   f{mf}:     -       -   0")
        print(line)

    # Y3VW bounce gated by open-inside-yesterday-VA
    def y3vw_gated_factory():
        inner = make_level_bounce("Y3VW", tp=("r", 1.0))()

        def fn(day, i):
            if day.y_val is None or not (day.y_val <= day.o[0] <= day.y_vah):
                return None
            return inner(day, i)
        return fn
    tg = run_market(days, y3vw_gated_factory(), False)
    w1 = [t for t in tg if t["day"] <= "2026-06-05"]
    w2 = [t for t in tg if t["day"] >= "2026-06-08"]
    s_, s1, s2 = stats(tg), stats(w1), stats(w2)
    print("\nY3VW gated (open inside y-VA):")
    if s_:
        print(f"  all: n={s_['n']} hit={s_['hit']:.1f}% pnl={s_['pnl']:+.2f} | "
              f"W1: {('n=%d hit=%.1f%% pnl=%+.2f' % (s1['n'], s1['hit'], s1['pnl'])) if s1 else 'n=0'} | "
              f"W2: {('n=%d hit=%.1f%% pnl=%+.2f' % (s2['n'], s2['hit'], s2['pnl'])) if s2 else 'n=0'}")

    # which days does FVG_f2_r0510 trade / win
    print("\nFVG_f2_r0510 trades:")
    for t in detail["FVG_f2_r0510"]:
        print(f"  {t['day']} ei={t['ei']:>3} entry={t['entry']:.2f} sl={t['sl']:.2f} "
              f"exit={t['xp']:.2f} {t['xt']} pnl={t['pnl']:+.2f}")

    (Path(__file__).parent / "data" / "trades_dump.json").write_text(
        json.dumps(detail, default=str))


if __name__ == "__main__":
    main()
