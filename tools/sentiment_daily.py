"""Sentimiento de mercado DETERMINISTA — dato de contexto para Market Intelligence (R1, 2026-07-03).

Bucket diario de sentimiento desde métricas observables (VIX percentil + racha + RSI2d + gap),
con reglas FIJAS — cero juicio del LLM. Se corre en /post-close 4d; el output alimenta
market_context.signature.sent + context_tags. NUNCA es gate de entrada (la familia vixcond
murió en FDR, Lote 1) — solo explica en qué régimen rinde cada sistema (patterns `sn:*`).

Uso: python sentiment_daily.py            # última sesión disponible en Yahoo
     python sentiment_daily.py --json     # salida JSON para el skill

Reglas del score (documentadas aquí = la única fuente):
  consec_up>=3 → +2 · ==2 → +1 · consec_dn>=3 → −2 · ==2 → −1
  rsi2_d>90 → +1 · <10 → −1
  vix_pct<0.20 → +1 · >0.80 → −2 · >0.60 → −1
  gap>+0.5% → +1 · <−0.5% → −1
  bucket: score>=3 euforia · >=1 optimismo · <=−3 panico · <=−1 pesimismo · resto neutral
"""
import argparse
import json
import urllib.request

UA = {"User-Agent": "Mozilla/5.0"}


def yahoo_daily(symbol, rng):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?range={rng}&interval=1d")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        d = json.loads(r.read())["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    out = []
    import datetime as dt
    for i, ts in enumerate(d["timestamp"]):
        if q["close"][i] is None:
            continue
        out.append({"date": dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat(),
                    "open": q["open"][i], "close": q["close"][i]})
    return out


def rsi2(closes):
    if len(closes) < 4:
        return None
    g = l = 0.0
    for k in (1, 2):
        d = closes[k] - closes[k - 1]
        g += max(d, 0); l += max(-d, 0)
    ag, al = g / 2, l / 2
    v = None
    for k in range(3, len(closes)):
        d = closes[k] - closes[k - 1]
        ag = (ag + max(d, 0)) / 2
        al = (al + max(-d, 0)) / 2
        v = 100 - 100 / (1 + (ag / al if al else 1e9))
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    qqq = yahoo_daily("QQQ", "6mo")
    vix = yahoo_daily("%5EVIX", "1y")
    closes = [r["close"] for r in qqq]
    today = qqq[-1]

    consec_up = consec_dn = 0
    for k in range(len(closes) - 1, 0, -1):
        if closes[k] > closes[k - 1]:
            if consec_dn: break
            consec_up += 1
        elif closes[k] < closes[k - 1]:
            if consec_up: break
            consec_dn += 1
        else:
            break
    r2 = rsi2(closes)
    gap = today["open"] / closes[-2] - 1 if len(closes) >= 2 else 0.0
    vclose = vix[-1]["close"]
    win = [r["close"] for r in vix[-253:]]
    vix_pct = sum(1 for w in win if w <= vclose) / len(win)

    score = 0
    if consec_up >= 3: score += 2
    elif consec_up == 2: score += 1
    if consec_dn >= 3: score -= 2
    elif consec_dn == 2: score -= 1
    if r2 is not None and r2 > 90: score += 1
    if r2 is not None and r2 < 10: score -= 1
    if vix_pct < 0.20: score += 1
    if vix_pct > 0.80: score -= 2
    elif vix_pct > 0.60: score -= 1
    if gap > 0.005: score += 1
    if gap < -0.005: score -= 1

    bucket = ("euforia" if score >= 3 else "optimismo" if score >= 1
              else "panico" if score <= -3 else "pesimismo" if score <= -1 else "neutral")
    out = {"date": today["date"], "sent": bucket, "score": score,
           "vix": round(vclose, 2), "vix_pct": round(vix_pct, 2),
           "consec_up": consec_up, "consec_dn": consec_dn,
           "rsi2_d": round(r2, 1) if r2 is not None else None,
           "gap_pct": round(gap * 100, 2)}
    print(json.dumps(out) if a.json else
          f"{out['date']}  sent={bucket} (score {score:+d})  VIX {out['vix']} p{out['vix_pct']}"
          f"  racha +{consec_up}/-{consec_dn}  rsi2d {out['rsi2_d']}  gap {out['gap_pct']}%")


if __name__ == "__main__":
    main()
