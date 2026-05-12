"""
trading/alpaca_client.py — Shared Alpaca REST API and Supabase HTTP client.

Loads credentials from .env at the project root on first import.
Both order_executor and run_live import from this module — single source of truth for
all HTTP logic and credentials.
"""
import json, os, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trading.connection import with_retry


def _load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

ALPACA_BASE = "https://paper-api.alpaca.markets"
ALPACA_DATA = "https://data.alpaca.markets"
_FALLBACK   = Path(__file__).parent / "fallback_trades.jsonl"


def _alpaca_headers() -> dict:
    return {
        "APCA-API-KEY-ID":     os.environ["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"],
        "Content-Type":        "application/json",
    }


def _supabase_headers() -> dict:
    key = os.environ["SUPABASE_ANON_KEY"]
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=ignore-duplicates",
    }


def _raw_request(method: str, url: str, headers: dict, data=None, timeout: int = 15):
    body = json.dumps(data).encode() if data else None
    req  = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


@with_retry()
def alpaca_request(method: str, path: str, data=None, timeout: int = 15):
    """Authenticated request to the Alpaca broker REST API."""
    return _raw_request(method, f"{ALPACA_BASE}{path}", _alpaca_headers(), data, timeout)


@with_retry()
def supabase_upsert(table: str, rows: list):
    """Upsert rows into a Supabase table. Raises on network errors."""
    url = f"{os.environ['SUPABASE_URL']}/rest/v1/{table}"
    _raw_request("POST", url, _supabase_headers(), rows)


def _supabase_select_exists(table: str, order_id: str) -> bool:
    """Returns True if a row with this order_id exists in the table."""
    url = (
        f"{os.environ['SUPABASE_URL']}/rest/v1/{table}"
        f"?order_id=eq.{urllib.parse.quote(order_id)}&limit=1"
    )
    hdrs = {
        "apikey":        os.environ["SUPABASE_ANON_KEY"],
        "Authorization": f"Bearer {os.environ['SUPABASE_ANON_KEY']}",
        "Accept":        "application/json",
    }
    result = _raw_request("GET", url, hdrs)
    return bool(result)


def supabase_upsert_verified(table: str, rows: list):
    """
    Upsert + SELECT verification. On persistent failure, appends to local fallback file.
    Never loses a trade record.
    """
    order_id = rows[0].get("order_id") if rows else None
    for attempt in range(3):
        try:
            supabase_upsert(table, rows)
            if not order_id or _supabase_select_exists(table, order_id):
                return
        except Exception:
            pass
        if attempt < 2:
            time.sleep(2 ** (attempt + 1))

    with open(_FALLBACK, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def get_clock() -> dict:
    """Alpaca market clock — is_open, next_open, next_close timestamps."""
    return alpaca_request("GET", "/v2/clock")


def sync_fallback_to_supabase() -> int:
    """Replay locally-saved fallback trades to Supabase. Returns count synced."""
    if not _FALLBACK.exists():
        return 0
    lines = [l.strip() for l in _FALLBACK.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return 0
    synced, remaining = 0, []
    for line in lines:
        try:
            supabase_upsert("trades", [json.loads(line)])
            synced += 1
        except Exception:
            remaining.append(line)
    if remaining:
        _FALLBACK.write_text("\n".join(remaining) + "\n", encoding="utf-8")
    else:
        _FALLBACK.unlink(missing_ok=True)
    return synced


@with_retry()
def get_bars(symbol: str, timeframe: str, start_iso: str, end_iso: str) -> list:
    """Fetch stock bars from Alpaca data API with auto-pagination."""
    bars, params = [], {
        "timeframe":  timeframe,
        "start":      start_iso,
        "end":        end_iso,
        "limit":      "1000",
        "adjustment": "raw",
        "feed":       "iex",
    }
    hdrs = {
        "APCA-API-KEY-ID":     os.environ["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"],
    }
    while True:
        url = f"{ALPACA_DATA}/v2/stocks/{symbol}/bars?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        bars.extend(data.get("bars") or [])
        token = data.get("next_page_token")
        if not token:
            break
        params["page_token"] = token
    return bars


def get_prev_close(symbol: str, before_dt: datetime) -> float:
    """Most recent daily closing price before before_dt."""
    start = (before_dt - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end   = before_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    bars  = get_bars(symbol, "1Day", start, end)
    if not bars:
        raise RuntimeError(f"No daily bars for {symbol} before {end}")
    return bars[-1]["c"]
