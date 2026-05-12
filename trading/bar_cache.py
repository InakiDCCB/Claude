"""
trading/bar_cache.py — Incremental Alpaca 5-min bar cache.

Stores bars in trading/bar_cache/{SYMBOL}_{TIMEFRAME}.json.
Fetches only the missing range on each call, then saves back.
Cache covers up to yesterday to avoid partial-day bars.
"""
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

_CACHE_DIR = Path(__file__).parent / "bar_cache"


def _cache_path(symbol: str, timeframe: str) -> Path:
    _CACHE_DIR.mkdir(exist_ok=True)
    return _CACHE_DIR / f"{symbol}_{timeframe}.json"


def _load_cache(symbol: str, timeframe: str) -> list:
    path = _cache_path(symbol, timeframe)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def _save_cache(symbol: str, timeframe: str, bars: list):
    _cache_path(symbol, timeframe).write_text(json.dumps(bars), encoding="utf-8")


def get_bars_cached(symbol: str, timeframe: str, start_date: str) -> list:
    """
    Return bars from start_date onwards, refreshing the local cache if needed.
    Only caches complete sessions (up to and including yesterday).
    """
    from trading.alpaca_client import get_bars as _fetch

    cached = _load_cache(symbol, timeframe)

    # Cache end: yesterday 23:59 UTC (complete sessions only)
    end = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT23:59:00Z")

    if cached:
        latest_dt   = datetime.fromisoformat(cached[-1]["t"].replace("Z", "+00:00"))
        fetch_start = (latest_dt + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        fetch_start = f"{start_date}T00:00:00Z"

    if fetch_start < end:
        try:
            new_bars = _fetch(symbol, timeframe, fetch_start, end)
        except Exception:
            new_bars = []

        if new_bars:
            existing_ts = {b["t"] for b in cached}
            merged = cached + [b for b in new_bars if b["t"] not in existing_ts]
            merged.sort(key=lambda b: b["t"])
            _save_cache(symbol, timeframe, merged)
            cached = merged

    start_prefix = f"{start_date}T"
    return [b for b in cached if b["t"] >= start_prefix]


def group_by_trading_day(bars: list) -> dict:
    """
    Group bars by UTC date (YYYY-MM-DD). Each day's list is sorted by timestamp.
    Works for US regular hours (13:30–21:00 UTC) in both EDT and EST.
    """
    groups: dict = defaultdict(list)
    for bar in bars:
        groups[bar["t"][:10]].append(bar)
    return {date: sorted(day_bars, key=lambda b: b["t"]) for date, day_bars in groups.items()}
