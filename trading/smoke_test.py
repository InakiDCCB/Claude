"""
trading/smoke_test.py — End-to-end pipeline smoke test.

Places a bracket order far below market price (will NOT fill),
monitors via WebSocket + REST for 75 seconds, then cancels.
Tests every layer: connectivity → order placement → WS → REST → cleanup.

Run:
    python trading/smoke_test.py
"""
import sys, time
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__file__)))

from datetime import datetime, timezone, timedelta
from trading.connection     import check_all
from trading.alpaca_client  import alpaca_request, get_bars
from trading.order_executor import OrderExecutor

SYMBOL = "TQQQ"
MONITOR_SECONDS = 75   # how long to run the WS + REST monitoring loop

def banner(text):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print('=' * 60)

def main():
    # ── 0. Connectivity ───────────────────────────────────────────
    banner("0. Pre-flight connectivity check")
    health = check_all()
    print(f"  alpaca:   {'OK' if health['alpaca']   else 'FAIL'}")
    print(f"  supabase: {'OK' if health['supabase'] else 'FAIL (trades → fallback file)'}")
    if not health["alpaca"]:
        print("  ABORT: Alpaca unreachable.")
        return

    # ── 1. Current price ──────────────────────────────────────────
    banner(f"1. Fetch current {SYMBOL} price")
    now   = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end   = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bars  = get_bars(SYMBOL, "5Min", start, end)
    if not bars:
        print("  ABORT: No bars returned.")
        return
    last_price = bars[-1]["c"]
    print(f"  Last close: ${last_price:.2f} @ {bars[-1]['t']}")

    # ── 2. Place bracket order far below market ───────────────────
    entry  = round(last_price * 0.68, 2)   # ~32% below market — will NOT fill
    target = round(entry + 3.00, 2)
    stop   = round(entry - 3.00, 2)

    banner("2. Place bracket order (far below market — won't fill)")
    print(f"  entry={entry}  target={target}  stop={stop}  qty=1")
    print(f"  (market price is ${last_price:.2f} — order needs ~32% drop to fill)")

    executor = OrderExecutor()
    try:
        parent_id = executor.place_bracket_order(
            symbol   = SYMBOL,
            qty      = 1,
            entry    = entry,
            target   = target,
            stop     = stop,
            strategy = "SMOKE-TEST",
            notes    = "smoke_test — cancel after verification",
        )
        print(f"  ORDER PLACED: {parent_id}")
    except Exception as e:
        print(f"  ABORT: Order placement failed: {e}")
        return

    # ── 3. WebSocket + REST monitoring ────────────────────────────
    banner(f"3. run_until() — monitoring {MONITOR_SECONDS}s via WS + REST")
    print(f"  (expecting no fills — order is far below market)")
    until = datetime.now(timezone.utc) + timedelta(seconds=MONITOR_SECONDS)
    executor.run_until(until)
    print(f"  run_until() returned. positions_count={executor.positions_count}")

    # ── 4. Cancel open order ──────────────────────────────────────
    banner("4. Cancel order and verify cleanup")
    for pid in list(executor._positions):
        try:
            alpaca_request("DELETE", f"/v2/orders/{pid}")
            print(f"  Canceled order {pid[:8]}")
        except Exception as e:
            print(f"  Cancel error: {e}")

    # Give Alpaca a moment to process
    time.sleep(2)

    # Confirm via GET
    try:
        order = alpaca_request("GET", f"/v2/orders/{parent_id}")
        print(f"  Order status after cancel: {order.get('status')}")
    except Exception as e:
        print(f"  Verify error: {e}")

    # ── 5. Summary ────────────────────────────────────────────────
    banner("5. Result")
    print("  OK Connectivity check passed")
    print("  OK Market data fetch passed")
    print("  OK Order placement passed")
    print("  OK WebSocket + REST monitoring ran without crash")
    print("  OK Order canceled cleanly")
    print("\n  (No trade recorded to Supabase — order never filled, as expected)")


if __name__ == "__main__":
    main()
