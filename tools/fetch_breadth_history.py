"""Fetch daily bars (SIP, split-adjusted) para una canasta de ~54 miembros grandes/líquidos y de
historia larga del Nasdaq-100, para construir un índice de BREADTH (amplitud de mercado) propio --
pedido explícito del usuario 2026-08-20 ("probemos con breadth de mercado") tras cerrar la línea
VIX/fear-index con resultado negativo. Mismo patrón que fetch_daily_full.py (REST directo con las
credenciales de .mcp.json, pure-stdlib, paginado).

**Limitación metodológica reconocida:** usa la composición ACTUAL del Nasdaq-100 (no reconstruye
membresía histórica) -- sesgo de supervivencia leve (una empresa que salió del índice en 2019 no
está en la canasta aunque hubiera sido parte de la "amplitud" real de ese momento). Aceptable para
research exploratorio, NO para un backtest que se vaya a operar sin más validación.

Guarda en tools/data/breadth/{symbol}.json (gitignored, mismo patrón que tools/data/qqq_*).

Uso: python fetch_breadth_history.py
"""
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

_env = json.loads((Path(__file__).parents[1] / ".mcp.json").read_text())["mcpServers"]["alpaca"]["env"]
HEADERS = {"APCA-API-KEY-ID": _env["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": _env["ALPACA_SECRET_KEY"]}
DATA_BASE = "https://data.alpaca.markets"
OUT_DIR = Path(__file__).parent / "data" / "breadth"

SYMBOLS = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "AVGO", "COST", "PEP",
    "ADBE", "CSCO", "CMCSA", "TXN", "QCOM", "AMD", "INTC", "INTU", "AMGN", "HON",
    "SBUX", "GILD", "MDLZ", "BKNG", "ADP", "VRTX", "REGN", "ISRG", "ADI", "LRCX",
    "MU", "PYPL", "CHTR", "MAR", "KLAC", "PANW", "SNPS", "CDNS", "ORLY", "MNST",
    "CTAS", "PCAR", "AEP", "ROST", "PAYX", "XEL", "FAST", "EA", "CTSH", "BIIB",
    "ILMN", "EXC", "IDXX", "VRSK",
]


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def fetch_daily(symbol, start, end):
    params = {"symbols": symbol, "timeframe": "1Day", "start": start, "end": end,
              "limit": "10000", "feed": "sip", "adjustment": "split"}
    all_bars, token = [], None
    while True:
        q = dict(params)
        if token:
            q["page_token"] = token
        url = DATA_BASE + "/v2/stocks/bars?" + urllib.parse.urlencode(q)
        resp = get(url)
        bars = resp.get("bars", {}).get(symbol, [])
        all_bars.extend(bars)
        token = resp.get("next_page_token")
        if not token:
            break
    return all_bars


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    end = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=16)).strftime("%Y-%m-%dT%H:%M:%SZ")
    start = "2016-01-01T00:00:00Z"
    ok, failed = 0, []
    for sym in SYMBOLS:
        try:
            bars = fetch_daily(sym, start, end)
            if not bars:
                failed.append(sym)
                print(f"{sym}: 0 barras (sin historia en el rango)")
                continue
            (OUT_DIR / f"{sym}.json").write_text(json.dumps(bars))
            print(f"{sym}: {len(bars)} barras, {bars[0]['t'][:10]} -> {bars[-1]['t'][:10]}")
            ok += 1
        except Exception as e:
            failed.append(sym)
            print(f"{sym}: ERROR {e}")
    print(f"\nTOTAL: {ok}/{len(SYMBOLS)} simbolos OK. Fallidos: {failed or 'ninguno'}")


if __name__ == "__main__":
    main()
