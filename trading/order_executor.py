"""
order_executor.py — Live order placement and fill reconciliation.

Architecture:
  - Bracket orders: limit entry + take-profit (limit) + stop-loss (stop)
  - Reconciles fills every POLL_INTERVAL seconds via REST polling (no WebSocket)
  - Idempotent writes: Supabase upsert on order_id — no duplicate records
  - Only FULLY FILLED trades are written to the trades table
  - State persisted to trading/open_positions.json — survives restarts/crashes

Run as standalone reconciler:
    python trading/order_executor.py

Place an order from another script:
    from trading.order_executor import OrderExecutor
    ex = OrderExecutor()
    ex.place_bracket_order('TQQQ', qty=10, entry=70.40, target=72.85, stop=67.40,
                           strategy='TOB-V2', notes='ORB +1.2%')
"""
import atexit, json, os, sys, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from trading.agent_reporter import report
from trading.alpaca_client import alpaca_request, supabase_upsert

# ── Config ────────────────────────────────────────────────────────────────────

POLL_INTERVAL = 30  # seconds between reconciliation runs
STATE_FILE    = os.path.join(os.path.dirname(__file__), "open_positions.json")

# ── State ─────────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def _save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ── Executor ──────────────────────────────────────────────────────────────────

class OrderExecutor:
    """
    Places bracket orders on Alpaca paper trading and reconciles fills to Supabase.

    Each open position is tracked in open_positions.json. The reconciler polls
    Alpaca every POLL_INTERVAL seconds to detect fills, bypassing any WebSocket
    unreliability. Only fully-filled round-trip trades are written to Supabase.
    """

    def __init__(self):
        self._positions: dict = _load_state()
        self._log("OrderExecutor ready — tracking "
                  f"{len(self._positions)} open position(s).")

    def _log(self, msg: str):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[{ts}] {msg}", flush=True)

    # ── Order placement ───────────────────────────────────────────────────────

    def place_bracket_order(
        self,
        symbol:   str,
        qty:      float,
        entry:    float,  # limit buy price
        target:   float,  # take-profit limit price
        stop:     float,  # stop-loss stop price
        strategy: str,
        notes:    str = "",
    ) -> str:
        """
        Submit a bracket order (entry + TP + SL) to Alpaca.
        Returns the parent order ID.
        """
        ts_tag = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        payload = {
            "symbol":          symbol,
            "qty":             str(qty),
            "side":            "buy",
            "type":            "limit",
            "time_in_force":   "day",
            "limit_price":     f"{entry:.2f}",
            "order_class":     "bracket",
            "take_profit":     {"limit_price": f"{target:.2f}"},
            "stop_loss":       {"stop_price":  f"{stop:.2f}"},
            "client_order_id": f"{strategy}-{symbol}-{ts_tag}",
        }

        order     = alpaca_request("POST", "/v2/orders", payload)
        parent_id = order["id"]

        self._positions[parent_id] = {
            "symbol":    symbol,
            "qty":       qty,
            "entry":     entry,
            "target":    target,
            "stop":      stop,
            "strategy":  strategy,
            "notes":     notes,
            "placed_at": datetime.now(timezone.utc).isoformat(),
            "status":    "pending_entry",
        }
        _save_state(self._positions)

        self._log(
            f"PLACED  {symbol} x{qty}  entry={entry:.2f}  "
            f"target={target:.2f}  stop={stop:.2f}  [{parent_id}]"
        )
        return parent_id

    # ── Reconciliation ────────────────────────────────────────────────────────

    def reconcile(self):
        """
        Check all open positions against Alpaca and process any new fills.
        Safe to call as often as needed — all writes are idempotent.
        """
        if not self._positions:
            return

        to_close = []
        for pid, pos in list(self._positions.items()):
            try:
                done = self._reconcile_one(pid, pos)
                if done:
                    to_close.append(pid)
            except Exception as e:
                self._log(f"WARN reconcile {pid}: {e}")

        for pid in to_close:
            del self._positions[pid]
        if to_close:
            _save_state(self._positions)

    def _reconcile_one(self, parent_id: str, pos: dict) -> bool:
        """Returns True when the position is fully resolved and can be removed."""
        order  = alpaca_request("GET", f"/v2/orders/{parent_id}")
        status = order.get("status", "")

        # Terminal states with no fill
        if status in ("canceled", "expired", "rejected"):
            self._log(f"ORDER {status.upper()} — {pos['symbol']} [{parent_id}]")
            return True

        # Not filled yet
        if status not in ("filled", "partially_filled"):
            return False

        # Partial: wait for full fill before recording
        if status == "partially_filled":
            return False

        # Entry fully filled
        entry_fill = float(order.get("filled_avg_price") or pos["entry"])
        filled_qty = float(order.get("filled_qty")       or pos["qty"])
        filled_at  = order.get("filled_at") or datetime.now(timezone.utc).isoformat()

        if pos.get("status") != "in_trade":
            self._log(f"ENTRY   {pos['symbol']} x{filled_qty} @ {entry_fill:.2f} [{parent_id}]")
            pos["status"]     = "in_trade"
            pos["entry_fill"] = entry_fill
            _save_state(self._positions)

        # Check exit legs (TP or SL)
        legs = order.get("legs") or []
        for leg in legs:
            if leg.get("status") == "filled":
                exit_price = float(leg.get("filled_avg_price") or 0)
                exit_type  = leg.get("type", "unknown")  # limit=TP, stop=SL
                pnl        = round((exit_price - entry_fill) * filled_qty, 4)

                self._record_trade(
                    pos        = pos,
                    parent_id  = parent_id,
                    entry_fill = entry_fill,
                    exit_price = exit_price,
                    exit_type  = exit_type,
                    filled_qty = filled_qty,
                    filled_at  = filled_at,
                    pnl        = pnl,
                )
                return True

        # Entry filled but no exit yet — position is open, keep polling
        return False

    def _record_trade(
        self,
        pos:        dict,
        parent_id:  str,
        entry_fill: float,
        exit_price: float,
        exit_type:  str,
        filled_qty: float,
        filled_at:  str,
        pnl:        float,
    ):
        outcome = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "TIME")
        leg_tag = "TP" if exit_type == "limit" else "SL"
        notes   = " | ".join(filter(None, [
            pos.get("notes", ""),
            f"exit={leg_tag}",
            f"outcome={outcome}",
        ]))

        row = {
            "created_at":  pos.get("placed_at"),
            "filled_at":   filled_at,
            "asset":       pos["symbol"],
            "side":        "buy",
            "quantity":    filled_qty,
            "price":       entry_fill,
            "exit_price":  exit_price,
            "order_id":    parent_id,
            "status":      "filled",
            "strategy":    pos["strategy"],
            "pnl":         pnl,
            "notes":       notes,
        }

        supabase_upsert("trades", [row])
        self._log(
            f"RECORDED {pos['symbol']} x{filled_qty}  "
            f"entry={entry_fill:.2f}  exit={exit_price:.2f}  "
            f"pnl={pnl:+.2f}  [{outcome}]  [{parent_id}]"
        )

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self, interval: int = POLL_INTERVAL):
        """
        Blocking reconciliation loop. Intended to run as a background service
        during market hours. Automatically reports status to the dashboard.
        """
        atexit.register(report, "Order Execution", "idle")
        report("Order Execution", "running")
        self._log(f"Reconciliation loop started — polling every {interval}s. Ctrl+C to stop.")
        try:
            while True:
                self.reconcile()
                time.sleep(interval)
        except KeyboardInterrupt:
            self._log("Stopped.")


if __name__ == "__main__":
    OrderExecutor().run()
