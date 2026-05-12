"""
trading/ws_client.py — WebSocket listener for Alpaca trade updates (stdlib only).

Implements RFC 6455 WebSocket using ssl + socket + hashlib + base64 + struct.
No external dependencies.

Usage:
    import queue
    from trading.ws_client import AlpacaTradeStream

    q = queue.Queue()
    ws = AlpacaTradeStream(q)
    ws.start()
    if ws._connected.wait(timeout=5) and ws.is_healthy:
        event = q.get()   # {"event": "fill", "order": {...}, ...}
    ws.stop()
"""
import base64, hashlib, json, os, queue, socket, ssl, struct, threading, time


# ── RFC 6455 frame helpers ─────────────────────────────────────────────────────

_WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _ws_connect(host: str, path: str) -> ssl.SSLSocket:
    """
    Open a TCP+SSL connection and perform the HTTP Upgrade handshake.
    Returns the SSL socket ready for WebSocket framing.
    """
    raw_key  = base64.b64encode(os.urandom(16)).decode()
    expected = base64.b64encode(
        hashlib.sha1((raw_key + _WS_MAGIC).encode()).digest()
    ).decode()

    ctx  = ssl.create_default_context()
    sock = socket.create_connection((host, 443), timeout=15)
    sock = ctx.wrap_socket(sock, server_hostname=host)

    handshake = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {raw_key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    )
    sock.sendall(handshake.encode())

    # Read response headers (up to the blank line)
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Server closed connection during WS handshake")
        resp += chunk

    if b"101" not in resp:
        raise ConnectionError(f"WS upgrade rejected: {resp[:200]}")

    # Validate server's accept key (RFC 6455 §4.1)
    for line in resp.decode(errors="replace").splitlines():
        if line.lower().startswith("sec-websocket-accept:"):
            if expected not in line:
                raise ConnectionError("Sec-WebSocket-Accept key mismatch")
            break

    return sock


def _ws_send(sock: ssl.SSLSocket, message: str):
    """Send a masked text frame. Client→server frames MUST be masked (RFC 6455 §5.3)."""
    payload = message.encode()
    mask    = os.urandom(4)
    masked  = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    length  = len(payload)

    if length < 126:
        header = struct.pack("!BB", 0x81, 0x80 | length)
    elif length < 65536:
        header = struct.pack("!BBH", 0x81, 0xFE, length)
    else:
        header = struct.pack("!BBQ", 0x81, 0xFF, length)

    sock.sendall(header + mask + masked)


def _read_exact(sock: ssl.SSLSocket, n: int) -> bytes:
    """Read exactly n bytes from the socket."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed mid-read")
        buf += chunk
    return buf


def _ws_recv(sock: ssl.SSLSocket, timeout: float = 35.0) -> tuple:
    """
    Read one complete WebSocket frame.
    Returns (opcode, payload_bytes).
    Raises TimeoutError if nothing arrives within `timeout` seconds.
    """
    sock.settimeout(timeout)

    header  = _read_exact(sock, 2)
    opcode  = header[0] & 0x0F
    has_mask = bool(header[1] & 0x80)
    length  = header[1] & 0x7F

    if length == 126:
        length = struct.unpack("!H", _read_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _read_exact(sock, 8))[0]

    mask_key = _read_exact(sock, 4) if has_mask else b""
    payload  = _read_exact(sock, length)

    if has_mask:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

    return opcode, payload


def _ws_ping(sock: ssl.SSLSocket):
    """Send a ping frame (FIN + opcode 0x9, masked, empty payload)."""
    sock.sendall(b"\x89\x80" + os.urandom(4))


def _ws_pong(sock: ssl.SSLSocket, payload: bytes = b""):
    """Send a pong frame in reply to a ping."""
    if not payload:
        sock.sendall(b"\x8A\x80" + os.urandom(4))
    else:
        mask   = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        sock.sendall(struct.pack("!BB", 0x8A, 0x80 | len(payload)) + mask + masked)


# ── Alpaca trade stream thread ─────────────────────────────────────────────────

class AlpacaTradeStream(threading.Thread):
    """
    Background thread: connects to Alpaca paper-trading WebSocket stream,
    authenticates, subscribes to trade_updates, and enqueues fill events.

    Auto-reconnects up to MAX_RETRIES times on drop.
    After MAX_RETRIES failures sets has_failed = True — caller should fall
    back to REST polling.
    """
    HOST        = "paper-api.alpaca.markets"
    PATH        = "/stream"
    MAX_RETRIES = 3
    HB_INTERVAL = 25   # seconds between heartbeat pings

    def __init__(self, event_queue: queue.Queue):
        super().__init__(daemon=True, name="AlpacaWS")
        self._q         = event_queue
        self._stop      = threading.Event()
        self._connected = threading.Event()
        self._sock      = None
        self.has_failed = False

    @property
    def is_healthy(self) -> bool:
        return self._connected.is_set() and not self.has_failed

    # ── Thread entry ──────────────────────────────────────────────────────────

    def run(self):
        retries = 0
        while not self._stop.is_set() and retries < self.MAX_RETRIES:
            try:
                self._connected.clear()
                self._run_session()
                retries = 0            # clean session → reset counter
            except Exception:
                retries += 1
                self._connected.clear()
                if not self._stop.is_set():
                    time.sleep(2 ** retries)

        if not self._stop.is_set():
            self.has_failed = True

    # ── Single WebSocket session ───────────────────────────────────────────────

    def _run_session(self):
        sock = _ws_connect(self.HOST, self.PATH)
        self._sock = sock

        # Authenticate — Alpaca accepts both auth format variants
        _ws_send(sock, json.dumps({
            "action": "auth",
            "key":    os.environ["ALPACA_API_KEY"],
            "secret": os.environ["ALPACA_SECRET_KEY"],
        }))

        # Wait for auth confirmation (try up to 3 frames)
        authenticated = False
        for _ in range(3):
            opcode, payload = _ws_recv(sock, timeout=10)
            if opcode == 0x8:
                raise ConnectionError("Server closed during auth")
            if opcode not in (0x1, 0x2):
                continue
            msg = json.loads(payload)
            if self._is_auth_ok(msg):
                authenticated = True
                break

        if not authenticated:
            raise ConnectionError("Authentication failed or timed out")

        # Subscribe to trade_updates
        _ws_send(sock, json.dumps({
            "action": "listen",
            "data":   {"streams": ["trade_updates"]},
        }))

        self._connected.set()
        last_ping = time.monotonic()

        # ── Receive loop ──────────────────────────────────────────────────────
        while not self._stop.is_set():
            # Heartbeat
            if time.monotonic() - last_ping >= self.HB_INTERVAL:
                _ws_ping(sock)
                last_ping = time.monotonic()

            try:
                opcode, payload = _ws_recv(sock, timeout=self.HB_INTERVAL + 10)
            except TimeoutError:
                _ws_ping(sock)
                last_ping = time.monotonic()
                continue

            if opcode == 0x8:          # Close frame
                self._connected.clear()
                return

            if opcode == 0x9:          # Ping from server → pong
                _ws_pong(sock, payload)
                continue

            if opcode in (0x1, 0x2):   # Text or binary
                try:
                    self._handle(json.loads(payload))
                except json.JSONDecodeError:
                    pass

    # ── Message parsing ───────────────────────────────────────────────────────

    def _is_auth_ok(self, msg) -> bool:
        """Accept either Alpaca auth response format."""
        if isinstance(msg, list):
            return any(
                m.get("T") == "success" and "authenticated" in m.get("msg", "")
                for m in msg
            )
        if isinstance(msg, dict):
            data = msg.get("data", {})
            return data.get("status") == "authorized"
        return False

    def _handle(self, msg):
        """Route incoming message to event enqueue."""
        if isinstance(msg, list):
            for item in msg:
                stream = item.get("stream") or item.get("T", "")
                if "trade_update" in stream:
                    self._enqueue(item.get("data", item))
        elif isinstance(msg, dict):
            if "trade_update" in msg.get("stream", ""):
                self._enqueue(msg.get("data", {}))

    def _enqueue(self, data: dict):
        """Only forward fill events — ignore order-new, pending, etc."""
        event = data.get("event", "")
        if event in ("fill", "partial_fill"):
            self._q.put({
                "event": event,
                "order": data.get("order", {}),
                "price": data.get("price"),
                "qty":   data.get("qty"),
                "ts":    data.get("timestamp"),
            })

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def stop(self):
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
