"""
trading/strategy_explorer.py — Level A parameter space exploration.

Level A: vary entry/exit parameters of the current strategy template.
         8 × 4 × 5 × 7 = 1,120 possible combinations.

Higher levels (B, C) will add new indicators and new strategy templates.
"""
import random
from copy import deepcopy
from datetime import datetime, timezone

from trading.strategy_schema import make_mutation_id

# Level A search space — all dimensions are independent
LEVEL_A_SPACE = {
    "orb_threshold_pct": [0.005, 0.0075, 0.01, 0.0125, 0.015, 0.0175, 0.02, 0.025],
    "orb_bars":          [2, 3, 4, 5],
    "qqq_gap_min_pct":   [-0.002, -0.001, 0.0, 0.001, 0.002],
    "sl_value":          [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0],
}


def generate_random_level_a(base_config: dict) -> dict:
    """Return a deep copy of base_config with randomly mutated Level A parameters."""
    cfg = deepcopy(base_config)
    cfg["id"] = make_mutation_id(base_config.get("strategy", "strategy").lower())
    cfg["entry"]["orb_threshold_pct"] = random.choice(LEVEL_A_SPACE["orb_threshold_pct"])
    cfg["entry"]["orb_bars"]          = random.choice(LEVEL_A_SPACE["orb_bars"])
    cfg["entry"]["qqq_gap_min_pct"]   = random.choice(LEVEL_A_SPACE["qqq_gap_min_pct"])
    cfg["exit"]["sl_value"]           = random.choice(LEVEL_A_SPACE["sl_value"])
    cfg["performance"] = {
        "trades": 0, "win_rate": None, "avg_pnl": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return cfg


def is_better_than_champion(
    candidate: dict,
    champion:  dict,
    min_trades:          int   = 100,
    min_pnl_improvement: float = 0.15,
    max_winrate_drop:    float = 0.05,
) -> bool:
    """
    True if candidate backtests justify replacing the champion.

    Criteria (all must hold):
      1. candidate.trades >= min_trades         (sufficient sample)
      2. candidate.avg_pnl >= champion.avg_pnl + min_pnl_improvement
      3. candidate.win_rate >= champion.win_rate - max_winrate_drop
    """
    if (candidate.get("trades") or 0) < min_trades:
        return False

    cand_pnl  = candidate.get("avg_pnl")  or 0.0
    champ_pnl = champion.get("avg_pnl")   or 0.0
    cand_wr   = candidate.get("win_rate") or 0.0
    champ_wr  = champion.get("win_rate")  or 0.0

    if cand_pnl < champ_pnl + min_pnl_improvement:
        return False
    if cand_wr < champ_wr - max_winrate_drop:
        return False
    return True
