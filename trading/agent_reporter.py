"""
Supabase agent status reporter.
Uses only stdlib (urllib) — no external dependencies.

Usage:
    from trading.agent_reporter import report
    report('Backtesting Engine', 'running')
    report('Backtesting Engine', 'idle')

For automatic cleanup on exit (including crashes):
    import atexit
    atexit.register(report, 'Backtesting Engine', 'idle')
    report('Backtesting Engine', 'running')
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_load_env()


def report(agent_name: str, status: str) -> None:
    """
    Update agent status in Supabase. Silently ignores all errors so it
    never interrupts the main script if the network is unavailable.
    """
    try:
        supabase_url = os.environ["SUPABASE_URL"]
        anon_key     = os.environ["SUPABASE_ANON_KEY"]

        payload = json.dumps({
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).encode()

        url = (
            f"{supabase_url}/rest/v1/agent_status"
            f"?name=eq.{urllib.parse.quote(agent_name)}"
        )
        req = urllib.request.Request(
            url,
            data=payload,
            method="PATCH",
            headers={
                "apikey": anon_key,
                "Authorization": f"Bearer {anon_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass
