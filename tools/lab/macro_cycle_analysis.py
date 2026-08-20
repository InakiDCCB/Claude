"""Research exploratorio: ciclos macro de drawdown en QQQ (2016-2026, todo lo que tiene Alpaca)
y su relación con el calendario político US. Corre sobre tools/data/qqq_daily_full.json
(generar con tools/fetch_daily_full.py).

Hallazgos (sesión 2026-08-19, ver memoria del proyecto para el detalle completo):
- Alpaca NO tiene historia antes de 2016-01-04 (ni con feed=sip) -- límite del proveedor de datos,
  no de la cuenta. La ventana disponible es ~10.6 años, no los ~27 años desde el nacimiento de QQQ.
- Con umbral -20% (bear market real, no correcciones normales) hay solo 4 episodios en la ventana:
  2018 (midterm), 2020 (presidencial, COVID), 2022 (midterm), 2025 (post-election, tarifas).
  n=4 es insuficiente para confirmar estadísticamente un ciclo de ~4 años -- es consistente con la
  "midterm election year low" (patrón documentado independientemente en literatura financiera desde
  datos de 1930s) pero esta ventana sola NO lo prueba.
- Confirmación con noticias (get_news alrededor de cada trough) sobre la hipótesis del usuario
  ("si una noticia explica el movimiento, suele revertir rápido"): CIERTO cuando la causa es un
  shock de política/sentimiento reversible (tarifas abril-2025: "Liberation Day" tariffs -> pausa
  90 días -> +35% TQQQ el mismo día del pivote, recuperado en ~2.5 meses; shutdown/Fed-tweets
  dic-2018 -> recuperación ~4 meses, más lento porque la Fed no revirtió hasta bien entrado 2019).
  FALSO cuando la causa es un régimen macro estructural sin catalizador único reversible (2022: sin
  "la noticia del día" en el trough, fue un año entero de hikes de tasas -> recuperación ~12 meses).
  Regla práctica: la velocidad de reversión depende de si la causa noticiada es una DECISIÓN
  reversible (tarifa, comentario de un funcionario) o un REGIMEN sostenido (ciclo de hikes,
  recesión real) -- no del mero hecho de que exista una noticia explicando el movimiento.
"""
import datetime as dt
import json
from pathlib import Path

DATA = Path(__file__).parents[1] / "data" / "qqq_daily_full.json"


def d(s):
    return dt.date.fromisoformat(s)


def political_year(year, anchor_presidential=2016):
    m = (year - anchor_presidential) % 4
    return {0: "presidencial", 1: "post-election", 2: "midterm", 3: "pre-election"}[m]


def find_drawdown_episodes(closes):
    """closes: list of (date_str, close_px) sorted ascending. Returns list of episodes:
    {peak_date, peak_px, trough_date, trough_px, dd_pct, recover_date|None}."""
    peak_date, peak_px = closes[0]
    episodes, in_dd, cur = [], False, None
    for date, px in closes:
        if px >= peak_px:
            if in_dd and cur is not None:
                cur["recover_date"] = date
                episodes.append(cur)
                in_dd, cur = False, None
            peak_date, peak_px = date, px
            continue
        dd = (px / peak_px - 1) * 100
        if not in_dd:
            in_dd = True
            cur = {"peak_date": peak_date, "peak_px": peak_px,
                   "trough_date": date, "trough_px": px, "dd_pct": dd}
        elif dd < cur["dd_pct"]:
            cur["trough_date"], cur["trough_px"], cur["dd_pct"] = date, px, dd
    if in_dd and cur is not None:
        cur["recover_date"] = None
        episodes.append(cur)
    return episodes


def main():
    bars = json.loads(DATA.read_text())
    bars.sort(key=lambda b: b["t"])
    closes = [(b["t"][:10], b["c"]) for b in bars]

    episodes = find_drawdown_episodes(closes)
    major = [e for e in episodes if e["dd_pct"] <= -10]
    bear = [e for e in episodes if e["dd_pct"] <= -20]

    print(f"Data window: {closes[0][0]} .. {closes[-1][0]}  ({len(closes)} daily bars)")

    print(f"\n=== Correcciones >=10% (n={len(major)}) ===")
    print(f"{'peak':<12}{'trough':<12}{'dd%':>8}  {'días peak->trough':>18}  recovered")
    for e in major:
        days = (d(e["trough_date"]) - d(e["peak_date"])).days
        rec = e.get("recover_date") or "NO (aún bajo el pico previo)"
        print(f"{e['peak_date']:<12}{e['trough_date']:<12}{e['dd_pct']:>7.1f}%  {days:>18}  {rec}")

    print(f"\n=== Bear markets reales >=20% (n={len(bear)}) -- ciclo político por año del TROUGH ===")
    for e in bear:
        yr = int(e["trough_date"][:4])
        days = (d(e["trough_date"]) - d(e["peak_date"])).days
        rec = e.get("recover_date")
        rec_days = (d(rec) - d(e["trough_date"])).days if rec else None
        rec_str = f"{rec} (+{rec_days}d)" if rec else "NO recuperado aún"
        print(f"{e['peak_date']} -> {e['trough_date']}  {e['dd_pct']:.1f}%  "
              f"año trough={yr} ({political_year(yr)})  recovery={rec_str}")

    if len(bear) >= 2:
        gaps = [(d(bear[i + 1]["trough_date"]) - d(bear[i]["trough_date"])).days / 365.25
                for i in range(len(bear) - 1)]
        print(f"\nGaps entre troughs sucesivos: {[round(g, 2) for g in gaps]} años "
              f"(n={len(gaps)} -- MUY poca muestra para confirmar periodicidad)")


if __name__ == "__main__":
    main()
