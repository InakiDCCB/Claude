---
name: feedback-no-ema-filter
description: Eliminar EMA9/EMA21 como filtro hard de entradas — solo VWAP/VA/ORB/FVG deciden
metadata:
  type: feedback
---

**Eliminado el filtro EMA** (EMA9 <11:15 ET / EMA21 ≥11:15 ET con buffer ±$0.25) como gate de entradas. Las compras se evalúan solo contra los 4 setups:

- VWAP Pullback (6 criterios)
- Volume Absorption (5 criterios)
- ORB Breakout (3 criterios, hasta 11:00 ET)
- FVG bullish (independiente)

**Why:** Comunicado por el usuario el 2026-06-01 mid-session. Durante la sesión vimos que el rebote QQQ desde 740.01 hacia VWAP (12:19 ET) cumplió 5/6 criterios de VWAP Pullback pero fue bloqueado por el filtro EMA9 → perdió la entrada justo antes de un rally de +$5. La EMA actúa como filtro redundante cuando los setups ya incorporan price action y volume.

**How to apply:**
- En `STEP 7` del cycle ignorar el bloque "EMA filter" completo (ET <11:15 → EMA9 / ET ≥11:15 → EMA21).
- Tampoco aplicar la regla de buffer ±$0.25 ni la regla "TREND DOWN: 3 barras consecutivas arriba de EMA21" — solo mantener la regla de TREND DOWN basada en "precio ≥1.5% arriba de session_low".
- Volume Absorption: el criterio interno "EMA21 below price" SE MANTIENE (es parte del setup, no filtro externo).
- SL/TP cálculo no cambia (2×ATR / estructural).

Related: [[feedback-stick-with-pulse]] (cambios al protocolo se aplican vía memoria, no edits al spec).
