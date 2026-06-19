# Estudio Smart Money Concepts (ICT + TRD Angel Casapia) — QQQ intradía

**Estado: RESEARCH (offline). No toca el loop.** Alimenta el pipeline backtest → shadow → ranking → Fase 4.
Parte de la directiva STANDING de nuevos sistemas. Fecha: 2026-06-18.

## 1. Hallazgo: ICT y TRD Casapia son la MISMA familia (SMC)
- **ICT** (Inner Circle Trader): order blocks, FVG, liquidity, market structure (BOS/CHoCH),
  displacement, OTE, killzones.
- **TRD Angel Casapia** (marca **ACATRADING**, @iamacatrading; canal YouTube "TRD Angel Casapia"):
  price action / **order flow / SMC** — order blocks, liquidez, estructura de mercado, "leer el gráfico
  sin indicadores". Sus reglas CONCRETAS están en cursos de pago (Hotmart) → **no públicas** en forma de reglas.
- → **Convergen.** Se unifican en UN stream SMC para no duplicar el trabajo de backtest. Casapia aporta
  un *framing* (order flow, sin indicadores) sobre el mismo set conceptual de ICT.

## 2. Ya implementado (¡SMC ya está dentro del sistema!)
- **S2 FVG** = Fair Value Gap (ICT). **LIVE**.
- **S4 SWP** (Sweep & Reclaim) = liquidity sweep / stop-hunt (ICT). **Shadow**.
→ El estudio EXTIENDE lo que ya hay; no parte de cero.

## 3. Inventario de conceptos SMC y su formalización para QQQ 1-min

| Concepto | Definición operacional (determinista) | Backtesteable | Estado |
|---|---|---|---|
| Fair Value Gap | gap de 3 velas (imbalance): `low[i] > high[i-2]` | sí | ✅ S2 |
| Liquidity sweep | barrido de high/low previo + reversión con volumen | sí | ✅ S4 |
| **Order Block (OB)** | última vela opuesta antes de un impulso que rompe estructura | sí (con regla de impulso ≥ k·ATR) | a formalizar |
| **Market Structure Shift (BOS/CHoCH)** | ruptura de swing high/low previo | sí (swings por fractales de N barras) | a formalizar |
| Breaker Block | OB fallido que se reconvierte tras BOS | sí (deriva de OB + BOS) | a formalizar |
| Displacement | vela(s) de impulso con rango ≫ ATR | sí (`rango ≥ k·ATR`) | a formalizar |
| OTE (Optimal Trade Entry) | retroceso a fib 0.62–0.79 del impulso | sí (fib sobre swing) | a formalizar |
| Killzones | ventanas horarias (NY open…) | ⚠️ choca con no-time-gates | **decisión usuario** |

## 4. ⚠️ Tensión killzones vs `no-time-gates`
ICT/SMC dan mucho peso a ventanas horarias (killzones). El proyecto tiene [[feedback-no-time-gates]]
(el usuario rechazó filtros por reloj). **Opciones:**
- (a) Reformular killzone como criterio de DATOS (p.ej. "primera hora con rvol30 alto" en vez de
  "9:30–10:30 fijo") — compatible con la regla.
- (b) Aprobar killzones como excepción (argumento: es mecánica del setup, no risk-mgmt por reloj).
→ **Decisión del usuario antes de codificarlas.**

## 5. El reto real: discrecional → determinista
SMC es **discrecional** (el trader "ve" el order block, el sweep, la estructura). Para backtestear hay
que fijar reglas DETERMINISTAS: cómo se define un swing (fractal de N barras), qué cuenta como "impulso"
(rango ≥ k·ATR), qué OB es válido (mitigado/no mitigado). **Cada definición es un parámetro a calibrar
→ riesgo de sobreajuste** si se prueban demasiadas variantes. Mitigación: walk-forward + el tier de
muestra mínima del ranking (n<20 = insufficient).

## 6. Plan (offline, gated por evidencia)
1. **Formalizar primero Order Block + Market Structure (BOS/CHoCH)** como factories en `backtest.py` /
   consultables vía `horizon_lab` — son el mayor valor incremental sobre FVG/SWP ya existentes.
2. Backtest sobre `qqq_1min` + walk-forward → Horizon Score.
3. **(Casapia)** si el usuario aporta material de sus cursos/videos con setups concretos, refinar las
   reglas con su framing; si no, usar la definición SMC estándar y tratarlo como "SMC genérico".
4. Los que pasen el backtest → shadow 5 sesiones → ranking → Fase 4 (nuevos sistemas S7+).

## 7. Decisiones que necesito del usuario
- **Killzones:** ¿reformular como dato (a) o aprobar excepción (b)?
- **Casapia:** ¿tienes acceso a sus reglas concretas (cursos) para formalizarlas fielmente, o uso la
  definición SMC estándar y lo tratamos como "SMC genérico"?
- **Prioridad:** ¿empiezo formalizando Order Block + BOS, o prefieres otro concepto primero?

## 8. Resultados — Backtest #1 (Bullish Order Block, SMC estándar, 06-18)
`smc_backtest.py` sobre 32 sesiones (05-01→06-16), grid n∈{1,2,3} × tp∈{1.5,2,3} × C4: **NO hay edge.**
PF agrupa en 0.81–1.07 (mayoría < 1.0), hit 22–44%, pnl mayormente negativo. Las 2 variantes apenas
positivas (n2 tp3.0 +2.15/PF1.07; n1 tp2.0+C4 +1.44/PF1.06) están dentro del ruido e inconsistentes con
sus vecinas → artefacto de grid-search. **Anti-hallazgo: NO re-probar OB naïve.** El framework cazó la
falta de edge antes de cualquier shadow/live.

## 9. Decisión 06-18: validar por SHADOW (no por backtest)
El usuario prefiere validación sobre **datos reales** (la divergencia backtest↔real le ha dado problemas).
→ Los mecanismos SMC (incl. OB) se shadowean. **Implementación: en `/post-close`** sobre las barras del
día (`smc_shadow.py`, detección causal = mismas señales que en vivo), **NO en cada ciclo** → cero coste
de latencia (clave porque hay un problema abierto de ciclos lentos, ver [[cycle-latency-overrun]]).
Shadow = guarda entry/SL/TP/outcome, SIN órdenes. Sobre N sesiones decidimos si OB tiene edge real
(el backtest dice que no; el forward-test real lo confirma o no). **Regla `no-time-gates` RELAJADA**
(killzones SMC permitidas, justificadas por evidencia).

## Fuentes (investigación 2026-06-18)
- Canal YouTube "TRD Angel Casapia" (@ACATRADING); Instagram @iamacatrading; cursos Hotmart
  ("SALA Trader Angel Casapia", "Traders Estoicos", "Aprende Viéndome Operar"). Método = price action /
  order flow / SMC, sin indicadores. Reglas detalladas: solo en cursos de pago.
