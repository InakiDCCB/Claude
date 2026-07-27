# Short-side mirror backtest — 2026-06-16

Motivación: usuario retira LONG-only (decisión 06-16) para no dejar dinero en días bajistas.
Antes de tocar `cycle_prompt`, medir si el edge v3.0 es **simétrico** en short.

Método: `backtest_short.py` — espejo exacto del motor LONG (reutiliza `Day`; SL arriba, TP abajo,
pnl = entry − exit). Cada sistema espejado a su gemelo bajista. Muestra: 12 sesiones 06-01..06-16
(incluye 4 días bajistas recientes). Fills conservadores idénticos al LONG (SL antes que TP intrabar).

## Resultado por sistema (LONG real vs SHORT espejo)

| Sistema | LONG hit / pnl | SHORT hit / pnl | ¿simétrico? |
|---|---|---|---|
| RSI2 (th 15 / espejo th 85) | 75.3% / +15.55 | 63.9% / −1.06 | **NO** |
| FVG f2 | 50.0% / +14.68 | 33.3% / −0.19 | **NO** |
| VWAPPB (45-65 / espejo 35-55) | 62.9% / +9.17 | 33.3% / −10.84 | **NO (peor)** |
| SWP | 69.2% / +2.48 | 76.9% / +1.46 | **SÍ** (PF 2.66) |
| GAPF | 66.7% / +6.64 | 25.0% / −4.37 | **NO** (n chico) |

**Portfolio SHORT (sin selector): n=98, 50.0% hit, −15.01/sh, PF 0.78, mLL=6.**
Portfolio LONG (mismo periodo): n=148, 67.6% hit, +48.52/sh, PF 1.69, mLL=3.

## Hallazgos

1. **La simetría NO se sostiene.** El espejo naïve pierde dinero (PF 0.78). Confirmado
   empíricamente: el mercado QQQ no es simétrico alza/baja — los pullbacks alcistas a VWAP
   revierten, los rallies bajistas a VWAP NO (VWAPPB-short −10.84 es el peor).

2. **El short solo es rentable en días bajistas (problema de régimen):**
   - SHORT en días con ret < −0.3%: **+19.66 (n=27)**
   - SHORT en días con ret > +0.3%: **−23.77 (n=61)**
   - El día de hoy 06-16 (−1.68%): short habría dado **+5.84 (n=5)** → la intuición del usuario
     es correcta PARA ese tipo de día. El problema: no sabes el régimen a las 10:00.

3. **Piezas salvables (pero NO validadas aún):**
   - **SWP-short** (sweep de máximo + rechazo): 76.9% hit, PF 2.66 — robusto a ambos lados,
     pero n=13 (~1/día). El más prometedor.
   - **RSI2-short th>90** (no th>85): +10.29, 75% hit, n=52. PERO th>85=−0.77 y th>95=−0.43:
     pico aislado en 90 con vecinos negativos = **probable overfit** con n=12 sesiones. No fiable.

## Veredicto

**NO promover shorts a LIVE con el espejo actual.** El edge direccional v3.0 es intrínsecamente
LONG. Caminos posibles (decisión usuario):
- (a) Aislar SWP-short como sistema shadow independiente (validar 5+ sesiones, juntar muestra).
- (b) Diseñar un **gate de régimen bajista** fiable a las 10:00/10:30 (¿open<VAL? ¿gap down?
  ¿xvwap+slope?) y activar shorts SOLO bajo ese gate — es el cuello de botella real.
- (c) Aceptar que en días como 06-16 el sistema se queda en cash (coste de oportunidad acotado:
  el LONG portfolio fue −1.11 ese día, no es que el LONG sangrara).

Re-correr: `python fetch_data.py && python backtest_short.py`. Para más muestra, extender el
START de fetch_data.py hacia atrás (más sesiones bajistas mejoran la potencia estadística).
