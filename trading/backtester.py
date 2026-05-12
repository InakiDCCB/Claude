"""
trading/backtester.py — Historical strategy backtester.

Uses the local bar cache (trading/bar_cache/) for all historical data.
Applies regime + exhaustion filters identical to run_live.py.
Minimum 100 trades recommended before trusting results (enforced by strategy_explorer).

Usage:
    from trading.backtester import run_backtest
    from trading.strategy_schema import load_champion
    metrics = run_backtest(load_champion(), start_date="2025-01-01")
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from trading.bar_cache        import get_bars_cached, group_by_trading_day
from trading.regime_agent     import MarketRegimeAgent
from trading.exhaustion_filter import ExhaustionGapFilter


def _compute_vwap(bars: list) -> float:
    total_vol = sum(b["v"] for b in bars)
    if total_vol == 0:
        b = bars[-1]
        return (b["h"] + b["l"] + b["c"]) / 3
    return sum(b.get("vw", (b["h"] + b["l"] + b["c"]) / 3) * b["v"] for b in bars) / total_vol


def _simulate_trade(
    entry_price: float,
    target: float,
    stop: float,
    post_orb_bars: list,
    orb_bars_n: int,
    time_stop_bar: int,
    qty: int,
) -> tuple:
    """
    Scan post-ORB bars and return (pnl, exit_type).
    exit_type: 'TP' | 'SL' | 'TIME'
    """
    for j, bar in enumerate(post_orb_bars):
        day_bar_idx = orb_bars_n + j

        tp_hit = bar["h"] >= target
        sl_hit = bar["l"] <= stop

        if tp_hit and sl_hit:
            # Both in same bar — use candle direction as tie-breaker
            if bar["c"] >= bar["o"]:
                return round((target - entry_price) * qty, 4), "TP"
            else:
                return round((stop - entry_price) * qty, 4), "SL"
        elif tp_hit:
            return round((target - entry_price) * qty, 4), "TP"
        elif sl_hit:
            return round((stop - entry_price) * qty, 4), "SL"

        if day_bar_idx >= time_stop_bar:
            return round((bar["c"] - entry_price) * qty, 4), "TIME"

    if post_orb_bars:
        return round((post_orb_bars[-1]["c"] - entry_price) * qty, 4), "TIME"
    return 0.0, "TIME"


def _get_regime_bars(qqq_by_day: dict, days: list, i: int, orb_bars: int) -> list:
    """QQQ bars for regime: previous trading day + current day ORB."""
    result = []
    if i > 0:
        result.extend(qqq_by_day.get(days[i - 1], []))
    result.extend(qqq_by_day.get(days[i], [])[:orb_bars])
    return result


def run_backtest(config: dict, start_date: str = "2025-01-01") -> dict:
    """
    Backtest a strategy config against historical 5-min bar data.

    Returns dict with: trades, wins, win_rate, avg_pnl, total_pnl,
                       pnl_per_trade, days_traded, days_signal, config_id.
    """
    symbol = config["symbol"]
    signal = config["signal_asset"]
    entry  = config["entry"]
    exit_c = config["exit"]

    orb_bars_n  = entry["orb_bars"]
    orb_thr     = entry["orb_threshold_pct"]
    qqq_gap_min = entry["qqq_gap_min_pct"]
    use_regime  = entry.get("use_regime", True)
    use_exh     = entry.get("use_exhaustion", True)
    sl_value    = exit_c["sl_value"]
    max_shares  = config["position"]["max_shares"]

    # Parse time_stop_et → bar index from session open (9:30 ET = bar 0)
    h, m = map(int, exit_c["time_stop_et"].split(":"))
    time_stop_bar = ((h - 9) * 60 + (m - 30)) // 5  # e.g. "15:50" → 76

    # Load and group bars
    tqqq_bars = get_bars_cached(symbol, "5Min", start_date)
    qqq_bars  = get_bars_cached(signal, "5Min", start_date)

    tqqq_by_day = group_by_trading_day(tqqq_bars)
    qqq_by_day  = group_by_trading_day(qqq_bars)

    days = sorted(set(tqqq_by_day) & set(qqq_by_day))

    regime_agent = MarketRegimeAgent()
    exh_filter   = ExhaustionGapFilter()
    results      = []

    for i, day in enumerate(days):
        tqqq_day = tqqq_by_day[day]
        qqq_day  = qqq_by_day[day]

        if len(tqqq_day) < orb_bars_n + 1 or len(qqq_day) < orb_bars_n:
            continue

        tqqq_orb = tqqq_day[:orb_bars_n]
        qqq_orb  = qqq_day[:orb_bars_n]

        # Previous day's QQQ close (needed for gap filter and exhaustion)
        if i == 0:
            continue
        prev_qqq_day = qqq_by_day.get(days[i - 1], [])
        if not prev_qqq_day:
            continue
        prev_qqq_close = prev_qqq_day[-1]["c"]

        # QQQ gap filter (fraction)
        qqq_gap = (qqq_orb[0]["o"] - prev_qqq_close) / prev_qqq_close
        if qqq_gap < qqq_gap_min:
            continue

        # TQQQ ORB filter
        tqqq_open    = tqqq_orb[0]["o"]
        tqqq_orb_pct = (tqqq_orb[-1]["c"] - tqqq_open) / tqqq_open
        if tqqq_orb_pct < orb_thr:
            continue

        # Regime filter
        if use_regime:
            regime_bars = _get_regime_bars(qqq_by_day, days, i, orb_bars_n)
            if len(regime_bars) < 10:
                continue
            regime = regime_agent.classify(regime_bars)
            if regime["regime"] != "MOMENTUM":
                continue

        # Exhaustion filter
        if use_exh:
            ex = exh_filter.detect(qqq_orb, prev_qqq_close)
            if ex["is_exhaustion"]:
                continue

        # Compute trade parameters
        entry_price = _compute_vwap(tqqq_orb)
        target      = max(b["h"] for b in tqqq_orb)  # ORB high
        stop        = entry_price - sl_value

        if target <= entry_price:
            continue  # degenerate: TP at or below entry

        post_orb = tqqq_day[orb_bars_n:]
        if not post_orb:
            continue

        pnl, exit_type = _simulate_trade(
            entry_price, target, stop, post_orb,
            orb_bars_n, time_stop_bar, max_shares,
        )
        results.append({"day": day, "pnl": pnl, "exit_type": exit_type})

    if not results:
        return {
            "trades": 0, "wins": 0, "win_rate": 0.0,
            "avg_pnl": 0.0, "total_pnl": 0.0,
            "pnl_per_trade": [], "days_traded": len(days),
            "days_signal": 0, "config_id": config.get("id", "?"),
        }

    pnls  = [r["pnl"] for r in results]
    wins  = sum(1 for p in pnls if p > 0)
    n     = len(pnls)
    return {
        "trades":        n,
        "wins":          wins,
        "win_rate":      round(wins / n, 4),
        "avg_pnl":       round(sum(pnls) / n, 4),
        "total_pnl":     round(sum(pnls), 4),
        "pnl_per_trade": [round(p, 4) for p in pnls],
        "days_traded":   len(days),
        "days_signal":   n,
        "config_id":     config.get("id", "?"),
    }
