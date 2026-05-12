"""
trading/connection.py — Retry decorator and pre-flight connectivity checks.

Import @with_retry to add exponential-backoff retry to any function.
Call check_all() at startup to verify external services are reachable.
"""
import functools, os, time, urllib.error, urllib.request


# ── Retry decorator ────────────────────────────────────────────────────────────

def with_retry(max_attempts=3, backoff_base=2.0,
               retryable_codes=(429, 500, 502, 503, 504)):
    """
    Retry up to max_attempts on transient network errors or retryable HTTP codes.
    Raises immediately on 401/403 (auth errors) — retrying won't fix those.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except urllib.error.HTTPError as e:
                    if e.code not in retryable_codes:
                        raise
                    last_exc = e
                except (urllib.error.URLError, TimeoutError,
                        OSError, ConnectionError) as e:
                    last_exc = e
                if attempt < max_attempts:
                    time.sleep(backoff_base ** attempt)
            raise last_exc
        return wrapper
    return decorator


# ── Pre-flight health checks ───────────────────────────────────────────────────

def verify_alpaca() -> bool:
    """True if Alpaca paper API responds within 8 s (3 attempts)."""
    from trading.alpaca_client import alpaca_request   # local import avoids circular
    for attempt in range(3):
        try:
            alpaca_request("GET", "/v2/clock", timeout=8)
            return True
        except Exception:
            if attempt < 2:
                time.sleep(2)
    return False


def verify_supabase() -> bool:
    """True if Supabase REST API responds within 8 s (3 attempts)."""
    url  = f"{os.environ['SUPABASE_URL']}/rest/v1/agent_status?limit=1"
    hdrs = {
        "apikey":        os.environ["SUPABASE_ANON_KEY"],
        "Authorization": f"Bearer {os.environ['SUPABASE_ANON_KEY']}",
    }
    for attempt in range(3):
        try:
            urllib.request.urlopen(
                urllib.request.Request(url, headers=hdrs), timeout=8
            )
            return True
        except Exception:
            if attempt < 2:
                time.sleep(2)
    return False


def check_all() -> dict:
    """
    Pre-flight connectivity check. Returns dict with bool per service.
    Call at agent startup before any trading logic.
    """
    return {
        "alpaca":   verify_alpaca(),
        "supabase": verify_supabase(),
    }
