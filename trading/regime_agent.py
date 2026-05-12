"""
MarketRegimeAgent — Multi-resolution momentum classifier.

Uses QQQ and VOO as primary market condition indicators (not the traded stock).
QQQ captures tech/growth momentum; VOO captures broad market direction.
Together they describe the market environment in which any strategy operates.

Computes M_t = sum(r_{t-i}) / (sigma_t * sqrt(N)) at multiple timeframes
and classifies market regime as MOMENTUM, MEAN_REVERSION, or NEUTRAL.
"""
import math
from typing import Literal, Optional

Regime = Literal["MOMENTUM", "MEAN_REVERSION", "NEUTRAL"]

_MOMENTUM_THR = 0.5
_MR_THR = -0.5

_RESOLUTION_SIZES = {"5m": 1, "15m": 3, "1h": 12}
_LOOKBACK         = {"5m": 15, "15m": 8, "1h": 4}
_RES_WEIGHTS      = {"5m": 0.3, "15m": 0.4, "1h": 0.3}

# Ticker blending weights: QQQ is more reactive, VOO more stable
_QQQ_W = 0.6
_VOO_W = 0.4


def _aggregate_bars(bars: list, size: int) -> list:
    out = []
    for i in range(0, len(bars) - size + 1, size):
        chunk = bars[i : i + size]
        out.append({
            "o": chunk[0]["o"],
            "h": max(b["h"] for b in chunk),
            "l": min(b["l"] for b in chunk),
            "c": chunk[-1]["c"],
            "v": sum(b["v"] for b in chunk),
            "t": chunk[-1]["t"],
        })
    return out


def _compute_mt(bars: list, n: int) -> float:
    """
    M_t = sum(r_{t-i}, i=1..N) / (sigma_t * sqrt(N))
    Returns 0 if insufficient data or zero volatility.
    """
    if len(bars) < n + 1:
        return 0.0
    tail = bars[-(n + 1):]
    returns = [math.log(tail[i]["c"] / tail[i - 1]["c"]) for i in range(1, len(tail))]
    sum_r = sum(returns)
    n_r = len(returns)
    mean_r = sum_r / n_r
    variance = sum((r - mean_r) ** 2 for r in returns) / n_r
    sigma = math.sqrt(variance)
    if sigma < 1e-10:
        return 0.0
    return sum_r / (sigma * math.sqrt(n_r))


def _mt_per_resolution(bars_5m: list) -> dict:
    """Compute M_t at each resolution for a single ticker."""
    out = {}
    for res, size in _RESOLUTION_SIZES.items():
        agg = _aggregate_bars(bars_5m, size) if size > 1 else bars_5m
        out[res] = round(_compute_mt(agg, _LOOKBACK[res]), 4)
    return out


def _classify_mt(mt: float) -> Regime:
    if mt > _MOMENTUM_THR:
        return "MOMENTUM"
    if mt < _MR_THR:
        return "MEAN_REVERSION"
    return "NEUTRAL"


class MarketRegimeAgent:
    """
    Classifies broad market regime using QQQ and VOO bars.

    QQQ and VOO represent the market environment, not the traded instrument.
    The regime tells strategies whether the market is trending (MOMENTUM),
    reverting (MEAN_REVERSION), or directionless (NEUTRAL).

    Usage:
        agent = MarketRegimeAgent()
        result = agent.classify(qqq_bars, voo_bars)   # preferred
        result = agent.classify(qqq_bars)              # VOO optional

        regime = result["regime"]       # MOMENTUM | MEAN_REVERSION | NEUTRAL
        quality = result["quality"]     # 0.0–1.0 confidence score
        signals = result["signals"]     # combined M_t per resolution
        per_ticker = result["per_ticker"]  # {"QQQ": {...}, "VOO": {...}}
    """

    def classify(self, qqq_bars: list, voo_bars: Optional[list] = None) -> dict:
        """
        Classify market regime from QQQ (required) and VOO (optional) 5-min bars.
        When VOO is provided, signals are blended 60% QQQ / 40% VOO.
        """
        qqq_mt = _mt_per_resolution(qqq_bars)

        if voo_bars and len(voo_bars) >= _LOOKBACK["5m"] + 1:
            voo_mt = _mt_per_resolution(voo_bars)
            signals = {
                res: round(_QQQ_W * qqq_mt[res] + _VOO_W * voo_mt[res], 4)
                for res in _RESOLUTION_SIZES
            }
            per_ticker = {"QQQ": qqq_mt, "VOO": voo_mt}
        else:
            signals = qqq_mt
            per_ticker = {"QQQ": qqq_mt, "VOO": None}

        weighted_mt = sum(_RES_WEIGHTS[r] * signals[r] for r in signals)

        if weighted_mt > _MOMENTUM_THR:
            combined = "MOMENTUM"
        elif weighted_mt < _MR_THR:
            combined = "MEAN_REVERSION"
        else:
            combined = "NEUTRAL"

        return {
            "regime": combined,
            "quality": round(self._compute_quality(signals, combined), 4),
            "weighted_mt": round(weighted_mt, 4),
            "signals": signals,
            "per_resolution": {res: _classify_mt(signals[res]) for res in signals},
            "per_ticker": per_ticker,
        }

    def _compute_quality(self, signals: dict, regime: Regime) -> float:
        if regime == "NEUTRAL":
            return 0.3
        sign = 1 if regime == "MOMENTUM" else -1
        aligned = [sign * signals[r] for r in signals]
        agreement = sum(1 for v in aligned if v > 0) / len(aligned)
        avg_strength = sum(max(v, 0) for v in aligned) / len(aligned)
        raw = 0.6 * agreement + 0.4 * min(avg_strength / 2.0, 1.0)
        return min(max(raw, 0.0), 1.0)
