# Pulse — historial de versiones del cycle_prompt

> Movido fuera de `strategies/cycle_prompt.md` en v3.1.1 (2026-07-03): el changelog se releía en
> cada ciclo del loop sin ser operativo (~2k tokens/relectura). Todas las reglas vigentes viven en
> los STEPs del cycle_prompt; este archivo es solo historia. Specs completos archivados en
> `strategies/history/cycle_prompt_v*.md`.

## v3.1.1 (2026-07-03) — dieta de contexto + modo reposo

Cero cambio de lógica de entradas (mismo espíritu que v3.0.5/v3.0.6). Motivación: preocupación del
usuario por latencia y costo de tokens con 4 sistemas LIVE (el gap por presupuesto tipo 06-22 es el
riesgo real).
- **Ventana de barras 45min → 12min** (batch de lectura): el fetch normal baja de ~45 a ~12 barras
  por ciclo → el historial de la conversación del loop engorda ~73% más lento → menos compactaciones.
  Gap-fallback escalonado: hueco > ventana → 2º fetch acotado desde `last_1min`; > 40 min →
  gap_recovery completo (13:30Z).
- **Changelog fuera del prompt** (este archivo): menos contexto base releído por ciclo.
- **Modo reposo:** wake cada 15 min (en vez de 5) SOLO cuando ninguna entrada es posible (todos los
  sistemas gated-off o C4-killed) Y sin posiciones NI limits. No sacrifica entradas por construcción.
  Al salir del reposo, catch-up de indicadores/shadow sobre el hueco (patrón O2).
- Pendiente de evaluar como experimento aparte: keep-alive de caché (wake vacío a ~sello+160s para
  mantener el prompt cache <300s → input a ~10% del precio; duplica wakeups — medir 1-2 sesiones).

## v3.1.0 (2026-07-03) — PROMOCIÓN S1 RSI2 + S4 SWP a LIVE + multi-posición

Decisión usuario 07-03; diseño `strategies/research/fase4_promotion_design.md` (decisiones 06-17:
sizing 8%, cap 70% como SUMA, máx 4 posiciones, prioridad por score del ranking, exclusión long/short).
Porteada FRESH sobre v3.0.6 (la rama `feat/fase4.1-rsi2-live` quedó obsoleta — se basaba en v3.0.3).
- **S1 RSI2 y S4 SWP colocan órdenes reales** (config oficial del playbook: S1 limit-al-close vida
  3 min + tp 0.5×ATR5m + sl 1.0×ATR5m + time-stop 15 min agent-side + abort >150s del sello;
  S4 limit-al-close vida 3 min + sl sweep_low−0.05 + tp 0.5R). S5 GAPF y S6 SWP-short SIGUEN shadow.
- **`state.positions` (LISTA) reemplaza a `state.position`**: cada estrategia ≤1 posición a la vez
  (su slot); varias estrategias coexisten (máx 4). Invariante: Σ qty trackeada == net qty Alpaca.
- **Sizing 8% equity para TODOS** (FVG/VWAPPB suben de 0.05 → 0.08). Cap exposición ≤70% como SUMA.
- **Validación**: 5 sesiones paper sin incidente de reconciliación.
- Claves shadow `rsi2`/`swp` CONGELADAS con su histórico; outcomes S1/S4 van por `trades` → ranking.

## v3.0.6 (2026-07-01) — optimización de ciclos B.1

SOLO ejecución/observabilidad, cero cambio de lógica de trading (diagnóstico
`docs/audit_cycles_2026-07-01.md`):
- **O1 — cadencia medible:** el UPDATE del STEP 9 añade SIEMPRE (también en ciclos de 1 línea) un
  timestamp a `state.cycle_log` → la cadencia real del loop queda auditable. Cero llamadas extra.
- **O2 — shadow diferido en ciclos con trabajo pesado:** si el ciclo ya hizo gap_recovery, fill/OCO
  o cómputo de gates, el STEP 6b (shadow) se DIFIERE al ciclo siguiente (`state.shadow_deferred`;
  nunca 2 seguidos; jamás difiere STEP 3 ni LIVE). Elimina la cola >300s de ciclos multi-trabajo.

## v3.0.5 (2026-06-30) — batching de I/O

SOLO ejecución, cero cambio de lógica de trading. Las lecturas (estado, clock, posiciones, barras)
en UN batch paralelo y las escrituras (log + heartbeat + estado) en UNA sola `execute_sql` →
~6 round-trips secuenciales por ciclo bajan a 2. Resuelve el "suelo" de scans p50 ~100s (que era
I/O en serie, no cómputo).

## v3.0.4 (2026-06-18) — instrumentación de latencia

SOLO observabilidad: STEP 0 captura `t0 = now()`; STEP 8 escribe `cycle_s` y `cycle_type` en
`indicators`, para diagnosticar los ciclos que superan la ventana de 5 min. También: OB shadow
batch SMC en `/post-close`.

## v3.0.3 (2026-06-16) — S6 SWP-short (shadow)

Nuevo sistema SHADOW: sweep de session HIGH + rechazo. Único short con edge en el backtest (76.9%
hit, PF 2.66, n=13 — `backtest_short_2026_06_16.md`; el espejo naïve del resto se RECHAZÓ: portfolio
short −15.01/sh PF 0.78). CERO órdenes — LONG-only sigue vigente para órdenes reales. `/post-close`
resuelve outcomes con motor espejo (`dir:"short"`).

## v3.0.2 (2026-06-15) — FVG sin tope de fills/día

Experimento aprobado por usuario. Gobernado por rvol30≥0.85 + pre-submit checks + C4 + 1-posición +
stop diario −$500. Fills SECUENCIALES. Hipótesis: las quality gates seleccionan fills #2+ con edge,
vs backtest crudo (fill#1 56%/+$18.50, fill#2 31%/+$1.19) que no aislaba pre-submit/rvol30.
`/post-close` trackea por `ordinal`.

## v3.0.1 (2026-06-12) — fixes post-mortem

Fase SOLO desde get_clock (STEP 1); check de precio fresco pre-submit FVG (STEP 6); delay de wakeup
computado al momento de la llamada (STEP 9); baseline vol30 en IEX (STEP 2-bis). Reglas de trading
sin cambios.

## v3.0 (2026-06-10) — reescritura desde el playbook

Sale del playbook validado en 32 sesiones (`strategies/research/playbook_2026_06_10.md`). Elimina:
ORB, Volume Absorption, filtro EMA, filtro VP, régimen TREND/RANGE, VP developing intradía, tick
fetches. Versión anterior: `strategies/history/cycle_prompt_v2.9.2_2026-06-10.md`.
