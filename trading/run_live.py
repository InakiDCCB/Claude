"""
trading/run_live.py — TOB-V2 TQQQ live execution entry point.

Launched daily by Windows Task Scheduler at 7:25 AM local (Mexico UTC-6).
Pipeline: health check → market check → wait for ORB → signal evaluation
          → bracket order → event-driven monitoring → time stop.
"""
import atexit, logging, os, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from trading.alpaca_client     import get_bars, get_prev_close, get_clock, alpaca_request
from trading.connection        import check_all
from trading.regime_agent      import MarketRegimeAgent
from trading.exhaustion_filter import ExhaustionGapFilter
from trading.market_learner    import MarketLearner
from trading.allocation        import AllocationEngine
from trading.order_executor    import OrderExecutor
from trading.agent_reporter    import report
from trading.strategy_schema   import load_champion

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


def _validate_bars(bars: list, symbol: str, expected: int,
                   session_start: datetime, log: logging.Logger) -> bool:
    """Verify bar count and that first bar aligns with session open (±5 min)."""
    if len(bars) < expected:
        log.warning(f"{symbol}: only {len(bars)}/{expected} bars returned")
        return False
    first_ts = datetime.fromisoformat(bars[0]["t"].replace("Z", "+00:00"))
    drift = abs((first_ts - session_start).total_seconds())
    if drift > 300:
        log.warning(f"{symbol}: first bar {first_ts.strftime('%H:%M')} UTC, "
                    f"expected near {session_start.strftime('%H:%M')} UTC (drift={drift:.0f}s)")
        return False
    return True


def _force_close(executor: OrderExecutor, symbol: str, log: logging.Logger):
    """Cancel open orders and close position with exponential-backoff retry."""
    for pid in list(executor._positions):
        for attempt in range(3):
            try:
                alpaca_request("DELETE", f"/v2/orders/{pid}")
                log.info(f"Canceled order {pid[:8]}")
                break
            except Exception as e:
                log.warning(f"Cancel {pid[:8]} attempt {attempt + 1}: {e}")
                time.sleep(2 ** attempt)

    for attempt in range(3):
        try:
            alpaca_request("DELETE", f"/v2/positions/{symbol}")
            log.info(f"Closed {symbol} position.")
            break
        except Exception as e:
            log.warning(f"Close position attempt {attempt + 1}: {e}")
            time.sleep(2 ** attempt)

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    log = _setup_log()
    atexit.register(report, "TOB-V2 Opening Monitor", "idle")
    report("TOB-V2 Opening Monitor", "running")
    log.info("=== TOB-V2 Opening Monitor started ===")

    # ── Load strategy config ───────────────────────────────────────────────────
    cfg          = load_champion()
    SYMBOL       = cfg["symbol"]
    QQQ          = cfg["signal_asset"]
    MAX_SHARES   = cfg["position"]["max_shares"]
    ORB_BARS     = cfg["entry"]["orb_bars"]
    ORB_PCT_MIN  = cfg["entry"]["orb_threshold_pct"]
    QQQ_GAP_MIN  = cfg["entry"]["qqq_gap_min_pct"]
    STOP_DOLLARS = cfg["exit"]["sl_value"]
    log.info(
        f"Config: {cfg['id']} | "
        f"orb={ORB_PCT_MIN:.3f} bars={ORB_BARS} "
        f"gap={QQQ_GAP_MIN:+.3f} sl=${STOP_DOLLARS:.2f}"
    )

    # ── 0. Pre-flight health check ─────────────────────────────────────────────
    health = check_all()
    if not health["alpaca"]:
        log.error("Alpaca API unreachable — aborting.")
        return
    if not health["supabase"]:
        log.warning("Supabase unreachable — trade records will go to fallback file.")

    # ── 1. Market clock ────────────────────────────────────────────────────────
    try:
        clock = get_clock()
    except Exception as e:
        log.error(f"Could not fetch market clock: {e}")
        return

    now_utc = datetime.now(timezone.utc)

    if clock["is_open"]:
        next_close = datetime.fromisoformat(clock["next_close"]).astimezone(timezone.utc)
        today_open = next_close - timedelta(hours=6, minutes=30)
    else:
        next_open = datetime.fromisoformat(clock["next_open"]).astimezone(timezone.utc)
        if next_open.date() != now_utc.date():
            log.info("No market session today — exiting.")
            return
        today_open = next_open

    orb_end    = today_open + timedelta(minutes=14, seconds=59)
    entry_time = today_open + timedelta(minutes=15)           # 9:45 ET
    time_stop  = today_open + timedelta(hours=6, minutes=20)  # 3:50 PM ET

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
    orb_start    = today_open.strftime("%Y-%m-%dT%H:%M:%SZ")
    after_orb    = entry_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    regime_start = (today_open - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        tqqq_orb_bars   = get_bars(SYMBOL, "5Min", orb_start, after_orb)
        qqq_regime_bars = get_bars(QQQ,    "5Min", regime_start, after_orb)
    except Exception as e:
        log.error(f"Failed to fetch bars: {e}")
        return

    qqq_orb_bars = [b for b in qqq_regime_bars if b["t"] >= orb_start][:ORB_BARS]
    orb_tqqq     = tqqq_orb_bars[:ORB_BARS]

    log.info(f"Bars — TQQQ ORB: {len(orb_tqqq)}, QQQ total: {len(qqq_regime_bars)}, QQQ ORB: {len(qqq_orb_bars)}")

    if not _validate_bars(orb_tqqq, SYMBOL, ORB_BARS, today_open, log):
        log.info("TQQQ bar validation failed — exiting.")
        return
    if not _validate_bars(qqq_orb_bars, QQQ, ORB_BARS, today_open, log):
        log.info("QQQ bar validation failed — exiting.")
        return

    # ── 4. Signal filters ──────────────────────────────────────────────────────
    try:
        prev_qqq_close = get_prev_close(QQQ, today_open)
    except Exception as e:
        log.error(f"Failed to fetch QQQ prev close: {e}")
        return

    qqq_gap_pct = (qqq_orb_bars[0]["o"] - prev_qqq_close) / prev_qqq_close
    log.info(f"QQQ gap: {qqq_gap_pct * 100:.2f}%  (need ≥ 0.0%)")
    if qqq_gap_pct < QQQ_GAP_MIN:
        log.info("QQQ gap FAILED — no trade.")
        return

    tqqq_open_price = orb_tqqq[0]["o"]
    tqqq_orb_high   = max(b["h"] for b in orb_tqqq)
    tqqq_orb_pct    = (orb_tqqq[-1]["c"] - tqqq_open_price) / tqqq_open_price
    log.info(f"TQQQ ORB: {tqqq_orb_pct * 100:.2f}%  (need ≥ 0.75%)")
    if tqqq_orb_pct < ORB_PCT_MIN:
        log.info("TQQQ ORB FAILED — no trade.")
        return

    regime_result = MarketRegimeAgent().classify(qqq_regime_bars)
    log.info(
        f"Regime: {regime_result['regime']} | "
        f"quality={regime_result['quality']:.2f} | "
        f"M_t={regime_result['weighted_mt']:.2f}"
    )
    if regime_result["regime"] != "MOMENTUM":
        log.info("Regime not MOMENTUM — no trade.")
        return

    ex = ExhaustionGapFilter().detect(qqq_orb_bars, prev_qqq_close)
    log.info(f"Exhaustion: score={ex['score']:.2f} | is_exhaustion={ex['is_exhaustion']}")
    if ex["is_exhaustion"]:
        log.info("Exhaustion gap detected — no trade.")
        return

    learner = MarketLearner()
    quality = learner.get_entry_quality_score(regime_result)
    alloc   = AllocationEngine().compute(
        tsla_bars      = tqqq_orb_bars,
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

    # ── 5. Compute order parameters and place order ────────────────────────────
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

    wait_until(entry_time, log)

    executor   = OrderExecutor()
    placed     = False
    parent_id  = None
    for attempt in range(3):
        try:
            parent_id = executor.place_bracket_order(
                symbol=SYMBOL, qty=qty,
                entry=entry_price, target=target, stop=stop,
                strategy="TOB-V2", notes=notes,
            )
            placed = True
            break
        except Exception as e:
            log.warning(f"Order placement attempt {attempt + 1}/3: {e}")
            time.sleep(2 ** attempt)

    if not placed:
        log.error("Order placement failed after 3 attempts — exiting.")
        return

    if parent_id:
        executor.set_trade_context(parent_id, regime_result)

    # ── 6. Event-driven monitoring until time stop ─────────────────────────────
    log.info(f"Monitoring until {time_stop.strftime('%H:%M UTC')} ...")
    executor.run_until(time_stop)

    if executor.positions_count == 0:
        log.info("All positions closed — done.")
        return

    # ── 7. Time stop — force close ─────────────────────────────────────────────
    log.info("Time stop reached — canceling orders and closing position.")
    _force_close(executor, SYMBOL, log)
    log.info("=== TOB-V2 Opening Monitor complete ===")


if __name__ == "__main__":
    main()
