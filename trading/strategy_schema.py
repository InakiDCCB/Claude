"""
trading/strategy_schema.py — Champion strategy schema and lifecycle management.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

EXCLUDED_ASSETS = frozenset({
    "BA", "LMT", "TXN", "NOC", "RTX", "GD", "HII",  # defense
    "MRNA", "PFE",                                     # excluded biotech
})

_CHAMPION_PATH = Path(__file__).parent / "active_strategy.json"
_ARCHIVE_DIR   = Path(__file__).parent / "strategy_archive"


def _tob_v2_default() -> dict:
    return {
        "version": "1.0.0",
        "id": "tob-v2-default",
        "strategy": "TOB-V2",
        "symbol": "TQQQ",
        "signal_asset": "QQQ",
        "entry": {
            "orb_bars": 3,
            "orb_threshold_pct": 0.0075,
            "qqq_gap_min_pct": 0.0,
            "use_regime": True,
            "use_exhaustion": True,
        },
        "exit": {
            "tp_method": "orb_high",
            "sl_method": "fixed_dollar",
            "sl_value": 3.0,
            "time_stop_et": "15:50",
        },
        "position": {
            "max_shares": 10,
        },
        "performance": {
            "trades": 0,
            "win_rate": None,
            "avg_pnl": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def load_champion() -> dict:
    """Load active champion strategy. Falls back to TOB-V2 default if absent."""
    if _CHAMPION_PATH.exists():
        return json.loads(_CHAMPION_PATH.read_text(encoding="utf-8"))
    return _tob_v2_default()


def save_champion(config: dict) -> None:
    _CHAMPION_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def archive_strategy(config: dict, reason: str) -> Path:
    _ARCHIVE_DIR.mkdir(exist_ok=True)
    ts  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    sid = config.get("id", "unknown")
    path = _ARCHIVE_DIR / f"{ts}_{sid}.json"
    archived = {**config, "_archived_at": datetime.now(timezone.utc).isoformat(), "_reason": reason}
    path.write_text(json.dumps(archived, indent=2), encoding="utf-8")
    return path


def make_mutation_id(base: str = "tob-v2") -> str:
    ts    = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    short = str(uuid.uuid4())[:8]
    return f"{base}-{ts}-{short}"


def sync_champion_to_supabase(config: dict) -> None:
    """
    Push current champion config to Supabase champion_strategy table.
    Silently ignores all errors — dashboard sync is best-effort.
    """
    import json as _json, os as _os, urllib.request as _ur
    try:
        url = _os.environ["SUPABASE_URL"]
        key = _os.environ["SUPABASE_ANON_KEY"]
        payload = _json.dumps([{
            "key":        "current",
            "config":     config,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }]).encode()
        req = _ur.Request(
            f"{url}/rest/v1/champion_strategy",
            data=payload,
            method="POST",
            headers={
                "apikey":        key,
                "Authorization": f"Bearer {key}",
                "Content-Type":  "application/json",
                "Prefer":        "resolution=merge-duplicates",
            },
        )
        _ur.urlopen(req, timeout=5)
    except Exception:
        pass
