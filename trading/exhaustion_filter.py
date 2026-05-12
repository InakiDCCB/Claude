"""
ExhaustionGapFilter — Detects market exhaustion gaps using QQQ and VOO.

An exhaustion gap occurs when the broad market (QQQ / VOO) opens with a
meaningful gap but the first ORB bars show reversal rather than continuation.
This signals that buyers/sellers are exhausted and the gap will be filled,
making momentum strategies high-risk for that session.

Detection uses data available at entry time (9:45 AM ET) only — no lookahead:
  - Gap size vs previous close
  - Gap fill ratio during the 15-min ORB (first 3 bars)
  - ORB opening candle direction (bearish reversal after gap up)
  - QQQ vs VOO agreement (divergence reduces confidence)

NOTE: This filter detects MARKET exhaustion, not individual stock exhaustion.
A stock like TSLA can exhaust independently of the broad market; that requires
stock-specific signals outside this module's scope.
"""
import math
from typing import Optional

# Minimum gap to trigger analysis (below this, no meaningful gap to exhaust)
_MIN_GAP_PCT = 0.30   # 0.30%

# ORB window: first N 5-minute bars after open (15 min = standard ORB)
_ORB_BARS = 3

# Exhaustion score threshold for classification
_EXHAUSTION_THR = 0.40


def _gap_pct(day_open: float, prev_close: float) -> float:
    if prev_close <= 0:
        return 0.0
    return (day_open - prev_close) / prev_close * 100  # in %


def _fill_ratio(day_open: float, prev_close: float, orb_close: float) -> float:
    """
    Fraction of the gap retraced by end of ORB.
      > 0 : gap filling (reversal toward prev_close)
      < 0 : gap extending (continuation away from prev_close)
      = 1 : fully filled
    """
    gap = day_open - prev_close
    if abs(gap) < 1e-6:
        return 0.0
    return (day_open - orb_close) / gap


def _orb_candle_score(bars: list, gap_up: bool) -> float:
    """
    Bearish-reversal candle score for the first ORB bar.
    Returns 0.0–1.0 where 1.0 = strong reversal candle after gap.
    """
    if not bars:
        return 0.0
    b = bars[0]
    rng = b["h"] - b["l"]
    if rng < 1e-6:
        return 0.0
    # Body direction: positive if bullish, negative if bearish
    body = (b["c"] - b["o"]) / rng
    # For gap-up: bearish candle (body < 0) signals exhaustion
    reversal_body = -body if gap_up else body
    return max(0.0, reversal_body)   # 0–1 range (body spans full range = 1)


def _mt_orb(bars: list, n: int = _ORB_BARS) -> float:
    """M_t of the first n bars — measures directional strength in the ORB."""
    tail = bars[: n + 1]
    if len(tail) < 2:
        return 0.0
    returns = [math.log(tail[i]["c"] / tail[i - 1]["c"]) for i in range(1, len(tail))]
    n_r = len(returns)
    sum_r = sum(returns)
    mean_r = sum_r / n_r
    var = sum((r - mean_r) ** 2 for r in returns) / n_r
    sigma = math.sqrt(var)
    if sigma < 1e-10:
        return sum_r * 100  # near-zero vol, use raw sum as direction
    return sum_r / (sigma * math.sqrt(n_r))


def _ticker_score(bars: list, prev_close: float) -> dict:
    """Compute exhaustion signals for a single ticker's 5-min bars."""
    if not bars or prev_close <= 0:
        return {"gap_pct": 0.0, "fill_ratio": 0.0, "candle": 0.0, "mt_orb": 0.0, "score": 0.0}

    day_open = bars[0]["o"]
    gap = _gap_pct(day_open, prev_close)
    gap_up = gap > 0

    if abs(gap) < _MIN_GAP_PCT:
        return {"gap_pct": round(gap, 4), "fill_ratio": 0.0, "candle": 0.0, "mt_orb": 0.0, "score": 0.0}

    orb_bars = bars[: _ORB_BARS + 1]
    orb_close = orb_bars[min(_ORB_BARS, len(orb_bars) - 1)]["c"]

    fill  = _fill_ratio(day_open, prev_close, orb_close)
    candle = _orb_candle_score(bars, gap_up)
    mt    = _mt_orb(bars, _ORB_BARS)

    # For gap-up: negative ORB M_t = reversal (exhaustion signal)
    mt_reversal = max(0.0, (-mt if gap_up else mt) / 2.0)

    # Fill component: only scores when gap is actually filling (fill > 0)
    fill_component = min(1.0, max(0.0, fill))

    # Weighted exhaustion score
    score = 0.50 * fill_component + 0.30 * candle + 0.20 * mt_reversal

    return {
        "gap_pct": round(gap, 4),
        "fill_ratio": round(fill, 4),
        "candle": round(candle, 4),
        "mt_orb": round(mt, 4),
        "score": round(min(1.0, score), 4),
    }


class ExhaustionGapFilter:
    """
    Detects broad-market exhaustion gaps using QQQ and optionally VOO.

    Uses only data available before the 9:45 AM entry (ORB period) — no lookahead.

    Usage:
        ef = ExhaustionGapFilter()

        # QQQ only
        result = ef.detect(qqq_bars, prev_qqq_close)

        # QQQ + VOO (recommended)
        result = ef.detect(qqq_bars, prev_qqq_close, voo_bars, prev_voo_close)

        result["is_exhaustion"]   → bool
        result["score"]           → 0.0–1.0
        result["QQQ"]             → per-ticker signals
        result["VOO"]             → per-ticker signals (or None)
        result["agreement"]       → "BOTH" | "QQQ_ONLY" | "VOO_ONLY" | "NONE"
    """

    def __init__(self, threshold: float = _EXHAUSTION_THR):
        self.threshold = threshold

    def detect(
        self,
        qqq_bars: list,
        prev_qqq_close: float,
        voo_bars: Optional[list] = None,
        prev_voo_close: Optional[float] = None,
    ) -> dict:
        qqq = _ticker_score(qqq_bars, prev_qqq_close)

        has_voo = bool(voo_bars and prev_voo_close and len(voo_bars) >= _ORB_BARS)
        if has_voo:
            voo = _ticker_score(voo_bars, prev_voo_close)
            # QQQ weighted higher (more reactive, stronger signal for momentum strategies)
            combined = 0.60 * qqq["score"] + 0.40 * voo["score"]
            qqq_ex = qqq["score"] >= self.threshold
            voo_ex = voo["score"] >= self.threshold
            agreement = (
                "BOTH"     if qqq_ex and voo_ex else
                "QQQ_ONLY" if qqq_ex else
                "VOO_ONLY" if voo_ex else
                "NONE"
            )
        else:
            voo = None
            combined = qqq["score"]
            agreement = "QQQ_ONLY" if combined >= self.threshold else "NONE"

        return {
            "is_exhaustion": combined >= self.threshold,
            "score": round(combined, 4),
            "agreement": agreement,
            "QQQ": qqq,
            "VOO": voo,
        }
