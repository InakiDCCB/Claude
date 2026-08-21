"""Descarga historia diaria de VIX / VIX3M / VVIX desde el CDN público oficial de CBOE (pure
stdlib, sin dependencias). Fuente oficial de cada índice, gratuita, sin auth:
- VIX   (CBOE Volatility Index, "el fear index" clásico): desde 1990
- VIX3M (implícita a 3 meses -- para ratio de term structure VIX/VIX3M): desde 2009
- VVIX  (volatilidad de la volatilidad, "vol-of-vol"): desde 2006

Guarda en tools/data/vix/*.csv (gitignored, mismo patrón que tools/data/qqq_*). Reproducible sin
tocar Alpaca -- Alpaca no sirve estos símbolos (son índices CBOE, no securities).

Uso: python fetch_vix_history.py
"""
import csv
import urllib.request
from pathlib import Path

OUT_DIR = Path(__file__).parent / "data" / "vix"
SOURCES = {
    "VIX": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
    "VIX3M": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv",
    "VVIX": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VVIX_History.csv",
}


def fetch(name, url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{name}.csv"
    out_path.write_text(raw)
    rows = list(csv.DictReader(raw.splitlines()))
    print(f"{name}: {len(rows)} filas, {rows[0]['DATE']} -> {rows[-1]['DATE']} -> {out_path}")


def main():
    for name, url in SOURCES.items():
        fetch(name, url)


if __name__ == "__main__":
    main()
