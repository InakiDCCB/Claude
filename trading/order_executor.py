"""
trading/order_executor.py — Live order placement and fill reconciliation.

Architecture:
  - Bracket orders: limit entry + take-profit (limit) + stop-loss (stop)
  - run_until(): WebSocket primary trigger + REST fallback/audit
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
import atexit, json, os, queue, sys, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from trading.agent_reporter import report
from trading.alpaca_client  import alpaca_request, supabase_upsert_verified
from trading.market_learner import MarketLearner
from trading.ws_client      import AlpacaTradeStream

# ── Config ────────────────────────────────────────────────────────────────────

POLL_INTERVAL = 30
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

    Primary monitoring: AlpacaTradeStream WebSocket fires reconcile() on fill events.
    Fallback: REST reconcile every 60 s (WS healthy) or 10 s (WS failed).
    """

    def __init__(self):
        self._positions: dict = _load_state()
        self._log(f"OrderExecutor ready — tracking {len(self._positions)} open position(s).")

    def _log(self, msg: str):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[{ts}] {msg}", flush=True)

    @property
    def positions_count(self) -> int:
        return len(self._positions)

    def set_trade_context(self, parent_id: str, regime_result: dict) -> None:
        """Store regime context so _record_trade can call MarketLearner.record_outcome."""
        if parent_id in self._positions:
            self._positions[parent_id]["regime_result"] = regime_result
            _save_state(self._positions)

    # ── Order placement ───────────────────────────────────────────────────────

    def place_bracket_order(
        self,
        symbol:   str,
        qty:      float,
        entry:    float,
        target:   float,
        stop:     float,
        strategy: str,
        notes:    str = "",
    ) -> str:
        """Submit a bracket order (entry + TP + SL) to Alpaca. Returns parent order ID."""
        ts_tag  = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
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

        try:
            order = alpaca_request("POST", "/v2/orders", payload)
        except Exception as e:
            self._log(f"ORDER PLACEMENT FAILED: {e}")
            raise

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
            f"target={target:.2f}  stop={stop:.2f}  [{parent_id[:8]}]"
        )
        return parent_id

    # ── Reconciliation ────────────────────────────────────────────────────────

    def reconcile(self):
        """Check all open positions against Alpaca and process any new fills."""
        if not self._positions:
            return

        to_close = []
        for pid, pos in list(self._positions.items()):
            try:
                done = self._reconcile_one(pid, pos)
                if done:
                    to_close.append(pid)
            except Exception as e:
                self._log(f"WARN reconcile {pid[:8]}: {e}")

        for pid in to_close:
            del self._positions[pid]
        if to_close:
            _save_state(self._positions)

    def _reconcile_one(self, parent_id: str, pos: dict) -> bool:
        """Returns True when position is fully resolved and can be removed."""
        order  = alpaca_request("GET", f"/v2/orders/{parent_id}")
        status = order.get("status", "")

        if status in ("canceled", "expired", "rejected"):
            self._log(f"ORDER {status.upper()} — {pos['symbol']} [{parent_id[:8]}]")
            return True

        if status not in ("filled", "partially_filled"):
            return False

        if status == "partially_filled":
            return False

        entry_fill = float(order.get("filled_avg_price") or pos["entry"])
        filled_qty = float(order.get("filled_qty")       or pos["qty"])
        filled_at  = order.get("filled_at") or datetime.now(timezone.utc).isoformat()

        if pos.get("status") != "in_trade":
            self._log(f"ENTRY   {pos['symbol']} x{filled_qty} @ {entry_fill:.2f} [{parent_id[:8]}]")
            pos["status"]     = "in_trade"
            pos["entry_fill"] = entry_fill
            _save_state(self._positions)

        legs = order.get("legs") or []
        for leg in legs:
            if leg.get("status") == "filled":
                exit_price = float(leg.get("filled_avg_price") or 0)
                leg_type   = leg.get("type", "")
                exit_type  = "TP" if leg_type == "limit" else "SL"
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
        outcome = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "SCRATCH")
        notes   = " | ".join(filter(None, [
            pos.get("notes", ""),
            f"exit={exit_type}",
            f"outcome={outcome}",
        ]))

        row = {
            "created_at": pos.get("placed_at"),
            "filled_at":  filled_at,
            "asset":      pos["symbol"],
            "side":       "buy",
            "quantity":   filled_qty,
            "price":      entry_fill,
            "exit_price": exit_price,
            "exit_type":  exit_type,
            "order_id":   parent_id,
            "status":     "filled",
            "strategy":   pos["strategy"],
            "pnl":        pnl,
            "notes":      notes,
        }

        supabase_upsert_verified("trades", [row])
        self._log(
            f"RECORDED {pos['symbol']} x{filled_qty}  "
            f"entry={entry_fill:.2f}  exit={exit_price:.2f}  "
            f"pnl={pnl:+.2f}  [{outcome}]  [{parent_id[:8]}]"
        )

        regime_result = pos.get("regime_result")
        if regime_result:
            ml_outcome = "WIN" if pnl > 0 else "LOSS"
            date_str   = filled_at[:10] if filled_at else datetime.now(timezone.utc).strftime("%Y-%m-%d")
            try:
                MarketLearner().record_outcome(
                    date         = date_str,
                    regime_result = regime_result,
                    outcome      = ml_outcome,
                    pnl          = pnl,
                    strategy     = pos.get("strategy", "TOB-V2"),
                )
            except Exception as e:
                self._log(f"MarketLearner.record_outcome failed: {e}")

    # ── WebSocket + REST monitoring ───────────────────────────────────────────

    def _process_ws_event(self, event: dict):
        """On any fill event from WS, immediately reconcile all positions via REST."""
        order = event.get("order", {})
        self._log(
            f"WS {event.get('event', '?')}  "
            f"order={order.get('id', '?')[:8]}  "
            f"price={event.get('price', '?')}"
        )
        self.reconcile()

    def run_until(self, until: datetime):
        """
        Monitor open positions until `until` (UTC datetime) or all positions are closed.
        WebSocket events are the primary trigger; REST reconcile is the fallback/audit.
        """
        event_q = queue.Queue()
        ws = AlpacaTradeStream(event_q)
        ws.start()

        if ws._connected.wait(timeout=5):
            self._log("WebSocket connected — event-driven mode.")
        else:
            self._log("WebSocket unavailable — REST fallback mode.")

        last_rest = datetime.now(timezone.utc)

        try:
            while datetime.now(timezone.utc) < until and self._positions:
                while not event_q.empty():
                    try:
                        self._process_ws_event(event_q.get_nowait())
                    except Exception as e:
                        self._log(f"WS event error: {e}")

                now = datetime.now(timezone.utc)
                if ws.has_failed:
                    self.reconcile()
                elif (now - last_rest).total_seconds() >= 60:
                    self.reconcile()
                    last_rest = now

                time.sleep(10)
        finally:
            ws.stop()

    # ── Standalone REST loop ──────────────────────────────────────────────────

    def run(self, interval: int = POLL_INTERVAL):
        """Blocking REST-only reconciliation loop (standalone / legacy use)."""
        self._log(f"REST reconciliation loop — polling every {interval}s.")
        try:
            while True:
                self.reconcile()
                time.sleep(interval)
        except KeyboardInterrupt:
            self._log("Stopped.")


if __name__ == "__main__":
    OrderExecutor().run()
