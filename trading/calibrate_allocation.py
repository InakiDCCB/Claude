"""
Calibrate AllocationEngine hyperparameters against historical backtest trades.

Design decision:
  - MEAN_REVERSION trades never reach the allocator (filtered by strategy regime).
    We enforce this with a hard gate: Y < 0.05 → A = 0.
  - Calibration focuses on sizing correctly for MOMENTUM and NEUTRAL regime wins.

Objective: maximize A(MOMENTUM wins) > A(NEUTRAL wins) > 0.05, consistently.

Output: trading/allocation_params.json
Run:    python trading/calibrate_allocation.py
"""
import atexit, json, math, os, sys, itertools
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from trading.regime_agent import MarketRegimeAgent
from trading.allocation import _normalized_time, _realized_vol, _correlation, _historical_vol
from trading.agent_reporter import report

atexit.register(report, 'Backtesting Engine', 'idle')
report('Backtesting Engine', 'running')

# ── Data loading ──────────────────────────────────────────────────────────────
_BASE = r"C:\Users\inaki\.claude\projects\C--Users-inaki-Claude\4b6a44fd-17b7-46ba-af07-660060a6e957\tool-results"
TSLA_FILES = [
    f"{_BASE}\\mcp-alpaca-get_stock_bars-1778465292120.txt",
    f"{_BASE}\\mcp-alpaca-get_stock_bars-1778465173714.txt",
    f"{_BASE}\\mcp-alpaca-get_stock_bars-1778465376423.txt",
    f"{_BASE}\\mcp-alpaca-get_stock_bars-1778464396264.txt",
]
QQQ_FILES = [
    f"{_BASE}\\mcp-alpaca-get_stock_bars-1778465292491.txt",
    f"{_BASE}\\mcp-alpaca-get_stock_bars-1778465173593.txt",
    f"{_BASE}\\mcp-alpaca-get_stock_bars-1778465377137.txt",
    f"{_BASE}\\mcp-alpaca-get_stock_bars-1778464399986.txt",
]


def _load_merge(files, sym):
    seen = {}
    for f in files:
        with open(f) as fh:
            d = json.load(fh)
        for b in d["bars"].get(sym, []):
            seen[b["t"]] = b
    return sorted(seen.values(), key=lambda x: x["t"])


def _group(bars):
    days = defaultdict(list)
    for b in bars:
        t = b["t"]; day = t[:10]; time = t[11:16]
        if "13:30" <= time <= "20:01":
            days[day].append(b)
    return {d: sorted(v, key=lambda x: x["t"]) for d, v in days.items()}


tsla_days = _group(_load_merge(TSLA_FILES, "TSLA"))
qqq_days  = _group(_load_merge(QQQ_FILES,  "QQQ"))
all_days  = sorted(set(tsla_days.keys()) & set(qqq_days.keys()))

# ── Backtest trades (best config) ─────────────────────────────────────────────
def _calc_vwap_series(day_bars):
    cum_pv = 0.0; cum_v = 0.0; result = []
    for b in day_bars:
        tp = (b["h"] + b["l"] + b["c"]) / 3
        cum_pv += tp * b["v"]; cum_v += b["v"]
        result.append((b, cum_pv / cum_v if cum_v > 0 else b["c"]))
    return result


def _extract_trades(orb_thr=0.75, qqq_gap_min=0.0, stop_size=3.0, max_wait=6, tol=1.0):
    traded = []; qqq_prev = None
    for day in all_days:
        tbars = tsla_days.get(day, [])
        qbars = qqq_days.get(day, [])
        if len(tbars) < 10 or len(qbars) < 3:
            if qbars: qqq_prev = qbars[-1]["c"]
            continue
        qqq_open = qbars[0]["o"]
        qqq_gap  = ((qqq_open - qqq_prev) / qqq_prev * 100) if qqq_prev else 0.0
        qqq_ok   = qqq_prev is None or qqq_gap >= qqq_gap_min
        orb_b = [b for b in tbars if b["t"][11:16] <= "13:44"][:3]
        if len(orb_b) < 3:
            qqq_prev = qbars[-1]["c"]; continue
        tsla_open = orb_b[0]["o"]
        orb_h = max(b["h"] for b in orb_b)
        orb_c = orb_b[-1]["c"]
        orb_p = (orb_c - tsla_open) / tsla_open * 100
        if not (qqq_ok and orb_p >= orb_thr):
            qqq_prev = qbars[-1]["c"]; continue
        vmap = {b["t"]: v for b, v in _calc_vwap_series(tbars)}
        post_orb = [(b, vmap[b["t"]]) for b in tbars if b["t"][11:16] >= "13:45"]
        entry_bar = None; entry_price = None
        for b, vwap in post_orb[:max_wait]:
            if b["l"] <= vwap + tol:
                entry_bar = b; entry_price = round(vwap, 2); break
        if entry_bar is None:
            qqq_prev = qbars[-1]["c"]; continue
        target = orb_h; stop = entry_price - stop_size
        entry_idx = next(i for i, (b, _) in enumerate(post_orb) if b["t"] == entry_bar["t"])
        outcome = "TIME"; pnl = 0.0
        for b, _ in post_orb[entry_idx:]:
            if b["h"] >= target: outcome = "WIN";  pnl = target - entry_price; break
            if b["l"] <= stop:   outcome = "LOSS"; pnl = stop - entry_price;   break
            if b["t"][11:16] >= "19:50": pnl = b["c"] - entry_price; break
        traded.append({
            "day": day, "outcome": outcome, "pnl": pnl,
            "entry_time": entry_bar["t"][11:16],
            "tbars": tbars, "qbars": qbars,
        })
        qqq_prev = qbars[-1]["c"]
    return traded


# ── Feature extraction ────────────────────────────────────────────────────────
_regime_agent = MarketRegimeAgent()
_all_qbars = [b for d in all_days for b in tsla_days.get(d, [])]  # QQQ history for sigma_h

_COMPAT = {"MOMENTUM": 1.0, "NEUTRAL": 0.6, "MEAN_REVERSION": 0.0}


def _extract_features(trade: dict) -> dict:
    qbars = trade["qbars"]
    # Regime and vol based on QQQ — no TSLA
    reg   = _regime_agent.classify(qbars)   # add voo_bars= when VOO data available
    compat = _COMPAT[reg["regime"]]
    Y     = reg["quality"] * compat
    T     = _normalized_time(trade["entry_time"])
    R     = _realized_vol(qbars)            # QQQ realized vol
    C     = 0.5                             # VOO pending: use neutral default
    sigma_h = _historical_vol(_all_qbars)
    return {
        "day": trade["day"], "outcome": trade["outcome"],
        "regime": reg["regime"], "Y": Y, "T": T, "R": R, "C": C, "sigma_h": sigma_h,
    }


# ── A formula (vectorized for speed) ─────────────────────────────────────────
def _A(feat: dict, p: dict) -> float:
    Y = feat["Y"]
    if Y < 0.05:          # hard gate: regime incompatible with strategy
        return 0.0
    T, R, C, sigma_h = feat["T"], feat["R"], feat["C"], feat["sigma_h"]
    alpha = math.exp(-p["l1"] * T - p["l2"] * (1.0 - Y) - p["l3"] * R)
    gamma = 1.0 + (p["g0"] * Y if Y > p["g_thr"] else 0.0)
    phi   = math.exp(-p["p0"] * R ** 2)
    # Directional tilt: clamped ≥ 0 (long-only strategy)
    direction = 1.0 if sigma_h >= p["kappa"] * abs(C) else max(0.0, 1.0 - p["kappa"])
    lam = direction * max(0.0, 1.0 - C)
    return min(1.0, alpha * gamma * phi * lam)


# ── Scoring: maximize A(MOMENTUM) > A(NEUTRAL), penalize zeroed wins ──────────
def _score(features: list, p: dict) -> tuple[float, dict]:
    by_regime: dict = defaultdict(list)
    zeroed_wins = 0
    for f in features:
        A = _A(f, p)
        if f["outcome"] == "WIN" and A < 0.05:
            zeroed_wins += 1
        by_regime[f["regime"]].append((f["outcome"], A))

    def mean_A(regime):
        vals = [A for _, A in by_regime.get(regime, [])]
        return sum(vals) / len(vals) if vals else 0.0

    mom  = mean_A("MOMENTUM")
    neut = mean_A("NEUTRAL")
    mr   = mean_A("MEAN_REVERSION")

    # Primary: high A for momentum; ordering: mom > neutral
    ordering_bonus = max(0.0, mom - neut) * 0.5
    score = mom + 0.6 * neut + ordering_bonus - 3.0 * mr - 10.0 * zeroed_wins

    return score, {"momentum": mom, "neutral": neut, "mr": mr, "zeroed_wins": zeroed_wins}


# ── Grid search ───────────────────────────────────────────────────────────────
GRID = {
    "l1":    [0.0, 0.1, 0.3, 0.5, 1.0],          # time decay
    "l2":    [0.3, 0.7, 1.0, 1.5, 2.0],          # quality penalty
    "l3":    [0.0, 0.1, 0.3, 0.5],               # vol penalty
    "g0":    [0.3, 0.5, 0.8, 1.0, 1.5],          # gamma boost
    "g_thr": [0.5, 0.6, 0.7, 0.8],               # gamma threshold
    "p0":    [0.0, 0.1, 0.3, 0.5],               # phi decay
    "kappa": [0.01, 0.05, 0.1, 0.2, 0.5],        # correlation sensitivity
}
# 5×5×4×5×4×4×5 = 40,000 combinations


if __name__ == "__main__":
    print("Extrayendo trades del backtest...")
    trades = _extract_trades()
    print(f"  {len(trades)} trades encontrados\n")

    features = [_extract_features(t) for t in trades]

    print(f"{'Date':<12} {'Regime':<16} {'T':>6} {'Y':>6} {'R':>6} {'C':>6} {'σ_h':>6} {'Outcome':>8}")
    print("-" * 70)
    for f in features:
        print(f"{f['day']:<12} {f['regime']:<16} {f['T']:>6.3f} {f['Y']:>6.3f} "
              f"{f['R']:>6.3f} {f['C']:>6.3f} {f['sigma_h']:>6.3f} {f['outcome']:>8}")

    n_combos = math.prod(len(v) for v in GRID.values())
    print(f"\nGrid search: {n_combos:,} combinaciones...")

    best_score = -999.0
    best_p = None
    best_detail = None
    best_stats = None

    keys = list(GRID.keys())
    for combo in itertools.product(*[GRID[k] for k in keys]):
        p = dict(zip(keys, combo))
        s, stats = _score(features, p)
        if s > best_score:
            best_score = s
            best_p = p
            best_stats = stats
            best_detail = [(f["day"], f["regime"], f["outcome"], _A(f, p)) for f in features]

    # ── Results ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"MEJOR CONFIGURACION  (score = {best_score:.4f})")
    print(f"{'='*60}")
    friendly = {
        "l1": "lambda1 (time decay)",
        "l2": "lambda2 (quality penalty)",
        "l3": "lambda3 (vol penalty)",
        "g0": "gamma0  (boost mult)",
        "g_thr": "gamma_thr (boost threshold Y>)",
        "p0": "phi0    (factor decay)",
        "kappa": "kappa   (corr sensitivity)",
    }
    for k, v in best_p.items():
        print(f"  {friendly[k]:<34} = {v}")

    print(f"\n  Avg A MOMENTUM:      {best_stats['momentum']:.4f}")
    print(f"  Avg A NEUTRAL:       {best_stats['neutral']:.4f}")
    print(f"  Avg A MEAN_REV:      {best_stats['mr']:.4f}  (blocked by hard gate Y<0.05)")
    print(f"  Zeroed winning days: {best_stats['zeroed_wins']}")

    print(f"\n{'Date':<12} {'Regime':<16} {'Outcome':>8} {'A':>8}  note")
    print("-" * 55)
    for day, regime, outcome, A in best_detail:
        gate  = "  [HARD GATE Y<0.05]" if A == 0.0 and outcome == "LOSS" else ""
        miss  = "  [MISSED WIN!]" if A < 0.05 and outcome == "WIN" else ""
        flag  = "  ← LOSS" if outcome == "LOSS" and A > 0.05 else ""
        print(f"{day:<12} {regime:<16} {outcome:>8} {A:>8.4f}{gate}{miss}{flag}")

    # ── Save calibrated params ────────────────────────────────────────────────
    out_path = os.path.join(os.path.dirname(__file__), "allocation_params.json")
    payload = {
        "params": {
            "lambda1": best_p["l1"],
            "lambda2": best_p["l2"],
            "lambda3": best_p["l3"],
            "gamma0":  best_p["g0"],
            "gamma_threshold": best_p["g_thr"],
            "phi0":    best_p["p0"],
            "kappa":   best_p["kappa"],
        },
        "calibration_score": round(best_score, 6),
        "calibrated_on": f"{all_days[0]} to {all_days[-1]}",
        "n_trades": len(trades),
        "avg_A_momentum": round(best_stats["momentum"], 4),
        "avg_A_neutral":  round(best_stats["neutral"], 4),
        "hard_gate_Y_threshold": 0.05,
        "note": "Re-calibrate after every 30 live trades",
    }
    with open(out_path, "w") as fp:
        json.dump(payload, fp, indent=2)
    print(f"\nGuardado en: {out_path}")
