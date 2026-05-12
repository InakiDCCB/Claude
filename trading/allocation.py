"""
AllocationEngine — Dynamic position sizing via the A formula.

A = e^(-λ1·T - λ2·(1-Y) - λ3·R) · (1 + γ0·Y · 1_{Y>γ_thr}) · e^(-φ0·R²) · Λ(C, σ_h)

Hard gate: Y < 0.05 (regime incompatible with strategy) → A = 0, do not trade.

Hyperparameters are loaded from allocation_params.json if present (run
calibrate_allocation.py to generate). Falls back to factory defaults otherwise.
"""
import json
import math
import os
from typing import Optional


def _load_calibrated_params() -> dict:
    """Load calibrated params from allocation_params.json if available."""
    path = os.path.join(os.path.dirname(__file__), "allocation_params.json")
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        return data.get("params", {})
    return {}

# Defaults — overridden by allocation_params.json when present
_FACTORY_DEFAULTS = {
    "lambda1": 0.5,
    "lambda2": 0.3,
    "lambda3": 0.4,
    "gamma0":  0.8,
    "gamma_threshold": 0.7,
    "phi0":    0.5,
    "kappa":   0.3,
}
_DEFAULTS = {**_FACTORY_DEFAULTS, **_load_calibrated_params()}


def _normalized_time(bar_time_str: str) -> float:
    """
    Convert bar timestamp (HH:MM UTC) to T in [0, 1] for US session.
    Session: 13:30–20:00 UTC (9:30–16:00 ET) → T=0 at open, T=1 at close.
    """
    h, m = int(bar_time_str[:2]), int(bar_time_str[3:5])
    minutes_from_open = (h * 60 + m) - (13 * 60 + 30)
    session_length = 6 * 60 + 30  # 390 minutes
    return max(0.0, min(1.0, minutes_from_open / session_length))


def _realized_vol(bars: list, n: int = 15) -> float:
    """Normalized realized volatility in [0, 1] from recent bar returns."""
    if len(bars) < n + 1:
        return 0.5
    tail = bars[-(n + 1):]
    returns = [math.log(tail[i]["c"] / tail[i - 1]["c"]) for i in range(1, len(tail))]
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / len(returns)
    sigma = math.sqrt(var)
    # Annualized vol proxy, cap at 2x daily typical
    annual_vol = sigma * math.sqrt(252 * 78)  # 78 bars/day for 5m
    return min(annual_vol / 2.0, 1.0)


def _correlation(bars_a: list, bars_b: list, n: int = 15) -> float:
    """Pearson correlation of returns between two bar series over last n bars."""
    if len(bars_a) < n + 1 or len(bars_b) < n + 1:
        return 0.5
    ra = [math.log(bars_a[-(n + 1) + i]["c"] / bars_a[-(n + 1) + i - 1]["c"]) for i in range(1, n + 1)]
    rb = [math.log(bars_b[-(n + 1) + i]["c"] / bars_b[-(n + 1) + i - 1]["c"]) for i in range(1, n + 1)]
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n)) / n
    sa = math.sqrt(sum((r - ma) ** 2 for r in ra) / n)
    sb = math.sqrt(sum((r - mb) ** 2 for r in rb) / n)
    if sa < 1e-10 or sb < 1e-10:
        return 0.5
    return max(-1.0, min(1.0, cov / (sa * sb)))


def _historical_vol(bars_history: list, n: int = 60) -> float:
    """Long-run realized vol estimate from historical bars."""
    return _realized_vol(bars_history, n=min(n, len(bars_history) - 1))


class AllocationEngine:
    """
    Computes dynamic position fraction A in [0, 1].

    Args (compute):
      tsla_bars      : recent 5-min TSLA bars (current day)
      qqq_bars       : recent 5-min QQQ bars (current day) for correlation
      entry_time_utc : "HH:MM" of intended entry bar
      quality        : regime quality score from MarketLearner (0-1)
      tsla_history   : multi-day TSLA bars for historical vol baseline
      params         : override default hyperparameters (optional)
    """

    def compute(
        self,
        tsla_bars: list,
        qqq_bars: list,
        entry_time_utc: str,
        quality: float,
        tsla_history: Optional[list] = None,
        params: Optional[dict] = None,
    ) -> dict:
        p = {**_DEFAULTS, **(params or {})}

        T = _normalized_time(entry_time_utc)
        Y = max(0.0, min(1.0, quality))

        # Hard gate: regime incompatible with strategy — do not allocate
        if Y < 0.05:
            return {
                "A": 0.0, "should_trade": False,
                "components": {"T": round(T, 4), "Y": 0.0, "gate": "Y<0.05"},
            }

        R = _realized_vol(tsla_bars)
        C = _correlation(tsla_bars, qqq_bars)
        hist = tsla_history if tsla_history else tsla_bars
        sigma_h = _historical_vol(hist)

        g_thr = p.get("gamma_threshold", 0.7)

        # α: position scalar
        alpha = math.exp(-p["lambda1"] * T - p["lambda2"] * (1.0 - Y) - p["lambda3"] * R)

        # Γ: gamma hedge boost when quality exceeds threshold
        gamma = 1.0 + (p["gamma0"] * Y if Y > g_thr else 0.0)

        # Φ: factor decay — penalizes high realized volatility
        phi = math.exp(-p["phi0"] * R ** 2)

        # Λ: directional tilt — long-only, clamped ≥ 0
        direction = 1.0 if sigma_h >= p["kappa"] * abs(C) else max(0.0, 1.0 - p["kappa"])
        lam = direction * max(0.0, 1.0 - C)

        A = min(1.0, max(0.0, alpha * gamma * phi * lam))

        return {
            "A": round(A, 4),
            "should_trade": A > 0.05,
            "components": {
                "T": round(T, 4),
                "Y": round(Y, 4),
                "R": round(R, 4),
                "C": round(C, 4),
                "sigma_h": round(sigma_h, 4),
                "alpha": round(alpha, 4),
                "gamma": round(gamma, 4),
                "phi": round(phi, 4),
                "lambda_tilt": round(lam, 4),
            },
        }
