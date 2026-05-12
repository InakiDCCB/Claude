"""
HistoricalPatternLibrary — Learns market condition → outcome mappings.

Records trade outcomes conditioned on regime, then computes
regime-conditional win rates that improve over time.
"""
import json
import os
from typing import Optional

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "regime_history.json")


class MarketLearner:
    """
    Stores and retrieves regime-conditioned trade outcomes.

    Each entry captures the regime context at entry and the trade result,
    building a conditional win-rate table without predicting price.
    """

    def __init__(self, path: str = _DEFAULT_PATH):
        self.path = path
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            with open(self.path) as f:
                return json.load(f)
        return {"entries": [], "win_rates": {}}

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2)

    def record_outcome(
        self,
        date: str,
        regime_result: dict,
        outcome: str,   # WIN | LOSS | TIME
        pnl: float,
        strategy: str = "TOB-V2",
    ):
        """Record a trade outcome with its regime context."""
        entry = {
            "date": date,
            "strategy": strategy,
            "regime": regime_result["regime"],
            "quality": regime_result["quality"],
            "weighted_mt": regime_result["weighted_mt"],
            "signals": regime_result["signals"],
            "outcome": outcome,
            "pnl": round(pnl, 4),
        }
        self._data["entries"].append(entry)
        self._recompute_win_rates()
        self._save()

    def _recompute_win_rates(self):
        """Recompute win rates grouped by regime and strategy."""
        from collections import defaultdict

        groups: dict = defaultdict(lambda: {"wins": 0, "total": 0, "pnl": 0.0})
        for e in self._data["entries"]:
            key = f"{e['strategy']}::{e['regime']}"
            groups[key]["total"] += 1
            groups[key]["pnl"] += e["pnl"]
            if e["outcome"] == "WIN":
                groups[key]["wins"] += 1

        rates = {}
        for key, stats in groups.items():
            rates[key] = {
                "win_rate": round(stats["wins"] / stats["total"], 4) if stats["total"] else 0.0,
                "trades": stats["total"],
                "total_pnl": round(stats["pnl"], 4),
            }
        self._data["win_rates"] = rates

    def get_win_rate(self, regime: str, strategy: str = "TOB-V2") -> Optional[float]:
        """Return historical win rate for a given regime and strategy."""
        key = f"{strategy}::{regime}"
        stats = self._data["win_rates"].get(key)
        if stats and stats["trades"] >= 3:  # min sample before trusting
            return stats["win_rate"]
        return None

    def get_entry_quality_score(
        self,
        regime_result: dict,
        strategy: str = "TOB-V2",
        strategy_regime: str = "MOMENTUM",
    ) -> float:
        """
        Regime-compatible quality score for use in the allocation formula.

        A strong signal in the WRONG direction is penalized, not rewarded:
          - regime == strategy_regime → compat = 1.0 (full signal)
          - NEUTRAL                  → compat = 0.6 (partial credit)
          - opposite regime          → compat = 0.0 (do not trade)
        """
        regime = regime_result["regime"]
        signal_quality = regime_result["quality"]

        compat = 1.0 if regime == strategy_regime else (0.6 if regime == "NEUTRAL" else 0.0)
        base_quality = signal_quality * compat

        historical_wr = self.get_win_rate(regime, strategy)
        if historical_wr is None:
            return round(base_quality, 4)

        # Once we have history, blend signal with observed win rate
        return round(0.5 * base_quality + 0.5 * historical_wr * compat, 4)

    def summary(self) -> dict:
        return {
            "total_trades": len(self._data["entries"]),
            "win_rates_by_regime": self._data["win_rates"],
        }
