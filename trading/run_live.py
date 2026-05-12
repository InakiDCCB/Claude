"""
trading/run_live.py — TOB-V2 TQQQ live execution entry point.

Launched daily by Windows Task Scheduler at 7:25 AM local (Mexico UTC-6).
Pipeline: market check → wait for ORB → signal evaluation → bracket order → reconcile.
"""
import atexit, logging, os, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from trading.alpaca_client    import get_bars, get_prev_close, get_clock, alpaca_request
from trading.regime_agent     import MarketRegimeAgent
from trading.exhaustion_filter import ExhaustionGapFilter
from trading.market_learner   import MarketLearner
from trading.allocation       import AllocationEngine
from trading.order_executor   import OrderExecutor
from trading.agent_reporter   import report

# ── Config ─────────────────────────────────────────────────────────────────────
SYMBOL       = "TQQQ"
QQQ          = "QQQ"
MAX_SHARES   = 10
STOP_DOLLARS = 3.00
ORB_BARS     = 3        # 3 × 5-min = first 15 min
ORB_PCT_MIN  = 0.0075   # TQQQ ORB must close ≥ 0.75% above open
QQQ_GAP_MIN  = 0.0      # QQQ must gap ≥ 0% vs prior close

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ── Logging (stdout + dated file) ─────────────────────────────────────────────
def _setup_log() -> logging.Logger:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s UTC  %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / f"tob_v2_{date}.log", encoding="utf-8"),
        ],
    )
    return logging.getLogger("tob_v2")

# ── Helpers ────────────────────────────────────────────────────────────────────
def compute_vwap(bars: list) -> float:
    """Volume-weighted average price across bars using Alpaca's per-bar vw field."""
    total_vol = sum(b["v"] for b in bars)
    if total_vol == 0:
        b = bars[-1]
        return (b["h"] + b["l"] + b["c"]) / 3
    return sum(b.get("vw", (b["h"] + b["l"] + b["c"]) / 3) * b["v"] for b in bars) / total_vol

def wait_until(target: datetime, log: logging.Logger):
    secs = (target - datetime.now(timezone.utc)).total_seconds()
    if secs > 2:
        log.info(f"Waiting {secs / 60:.1f} min → {target.strftime('%H:%M UTC')} ...")
        time.sleep(max(0.0, secs - 0.5))

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    log = _setup_log()
    atexit.register(report, "TOB-V2 Opening Monitor", "idle")
    report("TOB-V2 Opening Monitor", "running")
    log.info("=== TOB-V2 Opening Monitor started ===")

    # ── 1. Market clock ────────────────────────────────────────────────────────
    clock   = get_clock()
    now_utc = datetime.now(timezone.utc)

    if clock["is_open"]:
        # Arrived after open — infer open from next_close (6h30m standard session)
        next_close = datetime.fromisoformat(clock["next_close"]).astimezone(timezone.utc)
        today_open = next_close - timedelta(hours=6, minutes=30)
    else:
        next_open = datetime.fromisoformat(clock["next_open"]).astimezone(timezone.utc)
        if next_open.date() != now_utc.date():
            log.info("No market session today — exiting.")
            return
        today_open = next_open

    orb_end    = today_open + timedelta(minutes=14, seconds=59)
    entry_time = today_open + timedelta(minutes=15)            # 9:45 ET
    time_stop  = today_open + timedelta(hours=6, minutes=20)   # 3:50 PM ET

    log.info(
        f"Session: open={today_open.strftime('%H:%M')} "
        f"entry={entry_time.strftime('%H:%M')} "
        f"stop={time_stop.strftime('%H:%M')} (UTC)"
    )

    if now_utc >= entry_time:
        log.info("ORB window already passed — exiting.")
        return

    # ── 2. Wait for ORB to close ───────────────────────────────────────────────
    wait_until(orb_end + timedelta(seconds=30), log)

    # ── 3. Fetch bars ──────────────────────────────────────────────────────────
    orb_start = today_open.strftime("%Y-%m-%dT%H:%M:%SZ")
    after_orb = entry_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    # 24-hour lookback gives enough data for all regime resolutions (5m, 15m, 1h)
    regime_start = (today_open - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")

    tqqq_orb_bars   = get_bars(SYMBOL, "5Min", orb_start, after_orb)
    qqq_regime_bars = get_bars(QQQ,    "5Min", regime_start, after_orb)
    qqq_orb_bars    = [b for b in qqq_regime_bars if b["t"] >= orb_start][:ORB_BARS]

    orb_tqqq = tqqq_orb_bars[:ORB_BARS]
    log.info(f"Bars — TQQQ ORB: {len(orb_tqqq)}, QQQ total: {len(qqq_regime_bars)}, QQQ ORB: {len(qqq_orb_bars)}")

    if len(orb_tqqq) < ORB_BARS or len(qqq_orb_bars) < ORB_BARS:
        log.info("Insufficient ORB bars — exiting.")
        return

    # ── 4. Signal filters ──────────────────────────────────────────────────────
    prev_qqq_close = get_prev_close(QQQ, today_open)

    # QQQ gap filter
    qqq_gap_pct = (qqq_orb_bars[0]["o"] - prev_qqq_close) / prev_qqq_close
    log.info(f"QQQ gap: {qqq_gap_pct * 100:.2f}%  (need ≥ 0.0%)")
    if qqq_gap_pct < QQQ_GAP_MIN:
        log.info("QQQ gap FAILED — no trade.")
        return

    # TQQQ ORB filter
    tqqq_open_price = orb_tqqq[0]["o"]
    tqqq_orb_high   = max(b["h"] for b in orb_tqqq)
    tqqq_orb_pct    = (orb_tqqq[-1]["c"] - tqqq_open_price) / tqqq_open_price
    log.info(f"TQQQ ORB: {tqqq_orb_pct * 100:.2f}%  (need ≥ 0.75%)")
    if tqqq_orb_pct < ORB_PCT_MIN:
        log.info("TQQQ ORB FAILED — no trade.")
        return

    # Regime (uses full 24h QQQ bars for signal strength)
    regime_result = MarketRegimeAgent().classify(qqq_regime_bars)
    log.info(
        f"Regime: {regime_result['regime']} | "
        f"quality={regime_result['quality']:.2f} | "
        f"M_t={regime_result['weighted_mt']:.2f}"
    )
    if regime_result["regime"] != "MOMENTUM":
        log.info("Regime not MOMENTUM — no trade.")
        return

    # Exhaustion gap filter
    ex = ExhaustionGapFilter().detect(qqq_orb_bars, prev_qqq_close)
    log.info(f"Exhaustion: score={ex['score']:.2f} | is_exhaustion={ex['is_exhaustion']}")
    if ex["is_exhaustion"]:
        log.info("Exhaustion gap detected — no trade.")
        return

    # Allocation gate
    learner = MarketLearner()
    quality = learner.get_entry_quality_score(regime_result)
    alloc   = AllocationEngine().compute(
        tsla_bars      = tqqq_orb_bars,       # TQQQ in the execution-asset slot
        qqq_bars       = qqq_regime_bars,
        entry_time_utc = entry_time.strftime("%H:%M"),
        quality        = quality,
    )
    log.info(
        f"Allocation: quality={quality:.2f} | A={alloc['A']:.2f} | "
        f"should_trade={alloc['should_trade']}"
    )
    if not alloc["should_trade"]:
        log.info("Allocation gate closed (Y < 0.05 or A ≤ 0.05) — no trade.")
        return

    # ── 5. Compute order parameters ────────────────────────────────────────────
    entry_price = round(compute_vwap(orb_tqqq), 2)
    target      = round(tqqq_orb_high, 2)
    stop        = round(entry_price - STOP_DOLLARS, 2)
    qty         = max(1, round(alloc["A"] * MAX_SHARES))
    notes       = (
        f"ORB {tqqq_orb_pct * 100:.1f}% | "
        f"QQQ gap {qqq_gap_pct * 100:.1f}% | "
        f"A={alloc['A']:.2f}"
    )

    log.info(f"SIGNAL → {SYMBOL} x{qty}  entry={entry_price}  target={target}  stop={stop}")

    # Wait for 9:45 ET before placing
    wait_until(entry_time, log)

    executor = OrderExecutor()
    executor.place_bracket_order(
        symbol=SYMBOL, qty=qty,
        entry=entry_price, target=target, stop=stop,
        strategy="TOB-V2", notes=notes,
    )

    # ── 6. Reconciliation loop until time stop ─────────────────────────────────
    log.info(f"Reconciliation loop until {time_stop.strftime('%H:%M UTC')} ...")
    while datetime.now(timezone.utc) < time_stop:
        executor.reconcile()
        if not executor._positions:
            log.info("All positions closed — done.")
            return
        time.sleep(30)

    # ── 7. Time stop — force close ─────────────────────────────────────────────
    log.info("Time stop reached — canceling orders and closing position.")
    for pid in list(executor._positions):
        try:
            alpaca_request("DELETE", f"/v2/orders/{pid}")
            log.info(f"Canceled order {pid}")
        except Exception as e:
            log.warning(f"Cancel {pid}: {e}")

    try:
        alpaca_request("DELETE", f"/v2/positions/{SYMBOL}")
        log.info(f"Closed {SYMBOL} position.")
    except Exception as e:
        log.warning(f"Close position: {e}")

    log.info("=== TOB-V2 Opening Monitor complete ===")


if __name__ == "__main__":
    main()
