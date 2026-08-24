# Pulse — historial de versiones del cycle_prompt

## v3.1.14 (2026-08-24) — gt_closelow_v2 PROMOVIDO a LIVE (swing, override de protocolo); lwr_v1 se queda en shadow

Usuario pidió promover "los shadows" a LIVE. En ese momento los dos shadows activos eran
`gt_closelow_v2` (clr(ayer)<0.1 → hold 3 días hábiles, arrancado 08-20) y `lwr_v1` (mecha+volumen
intradía, re-promovido a shadow v3.1.13). Antes de tocar nada se consultó `v_shadow_accumulated`:
`lwr_v1` tenía n=19 (bajo el propio criterio de muerte PF<1.2@n≥25) y pnl/sh **negativo** (−$2.14);
`gt_closelow_v2` tenía **n=0** (su hold de 3 días no había tenido tiempo de resolver ni un
episodio desde el 08-20). El propio protocolo documentado en `project_gt_closelow_v2.md` y
`project_liquidity_wick_reversal.md` exige Score≥65 con n≥30 antes de promover — ninguno lo
cumplía. Se preguntó al usuario con ambos números sobre la mesa:

- **lwr_v1 → se queda en shadow** (decisión usuario: esperar más datos, no promover con pnl/sh
  negativo). Sin cambios de mecánica ni de `strategy_registry`.
- **gt_closelow_v2 → PROMOVIDO a LIVE** (decisión usuario, override explícito del protocolo n≥30 —
  el research/backtest no cambió: PF=2.36 pool 10 años, positivo 10/11 años, hit=66.5%, pero CERO
  confirmación en vivo). `strategy_registry.gt_closelow_v2` → `status='live'`.

**Arquitectura nueva — primer sistema SWING del agente** (hold multi-día, todo lo demás es
intradía con cierre forzado a las 15:55):
- **Señal:** se mueve de `/post-close` (STATELESS, batch retrospectivo) a `/pre-market` — clr del
  daily bar de AYER ya se conoce antes de la apertura. `pre-market.md` STEP 4b calcula
  `gates.gt2_on`/`gates.gt2_clr` desde `volume_profiles` (agregadas columnas `day_high`/`day_low`
  al SELECT existente — cero fetches nuevos).
- **Entrada:** `cycle_prompt.md` STEP 6c (nuevo) — el backtest define entry=open literal (9:30 ET)
  pero el loop no corre ciclos entre 9:30-9:55 (fase PRE); se entra con MARKET order en el primer
  ciclo ACTIVE (~10:00 ET), aproximación documentada y aceptada. Sin OCO — fiel al backtest, que es
  una señal pura sin SL/TP, solo hold fijo.
- **Tracking de posición:** vía `trades` (`strategy='gt_closelow_v2'`, `exit_price IS NULL` =
  abierta), NO vía `state.positions[]` — `session_state` es una fila por fecha y se resetea cada
  día, así que una posición que debe sobrevivir 3 días no puede vivir ahí. STEP 3.0 (nuevo) la
  deriva de `trades` una vez por día. Invariante de reconciliación extendido: `Σ qty
  state.positions[] + gt2.qty (si abierta) == net qty Alpaca`.
- **Salida:** STEP 10 (reescrito) — ya NO usa `close_all_positions`/`close_position` (cerrarían
  también las shares swing en custodia). Cierra explícitamente `qty_cerrar = Σ intradía + gt2.qty
  SOLO si hoy es su día de salida` (entry + 2 sesiones hábiles, contadas vía `count(*) FROM
  session_state WHERE date > entry_date AND date <= CURRENT_DATE`).
- **Bucket propio:** sizing 8% equity, fuera del cap de 4 posiciones/70% intradía; sin C4 estándar
  (no encaja con "apagado hasta mañana" en un ciclo de 3 días) — 2 pérdidas consecutivas pausan
  nuevas entradas hasta revisión manual del usuario, no auto-reactivación.

`post-close.md`: paso 4c (batch `gt_closelow_v2_shadow.py`) RETIRADO — sus outcomes ahora van por
`trades` como cualquier LIVE, verificados en el paso 3. Clave `gtclv2` pasa a CONGELADA. Paso 1
(cierre de emergencia) ganó una excepción explícita para no cerrar shares swing no vencidas.
`strategy_registry.gt_closelow_v2` → `live`. Ver `project_gt_closelow_v2.md` para el research
original y la decisión de promoción.

## v3.1.13 (2026-08-20) — S4 SWP RE-PROMOVIDO a LIVE, LWR RE-PROMOVIDO a SHADOW (override de usuario)

Decisión usuario, misma sesión que v3.1.12: volver a correr S4 SWP en vivo y LWR como shadow.
**Esto NO es un nuevo hallazgo de research** — el diagnóstico de v3.1.12 sigue vigente y no fue
refutado (backtest de 10 años PF=0.93 para S4, 0/11 años positivos en el barrido SL 0.5R-1.0R con
slippage realista modelado, mismo patrón para LWR — ver `project_s4_lwr_path_analysis.md`). El
usuario decidió explícitamente correrlos de todos modos, con el mismo freno C4 (2 pérdidas
consecutivas → apagado hasta el día siguiente) que ya tenían antes del retiro.

Revertido en `cycle_prompt.md`: STEP 6 (bloque de señal S4 SWP restaurado sin cambios de
parámetros respecto a v3.1.0-v3.1.11), tabla de sistemas, prioridad multi-posición (S2>S1 →
S2>S1>S4), C4/MODO REPOSO (`c4.swp` de vuelta), STEP 7-fill (OCO + INSERT de `trades` con
`swp_v3` de vuelta), RESTRICCIONES PERMANENTES. `strategy_registry`: `swp_v3` → `live`, `lwr_v1` →
`shadow` (vuelve a correr batch en `/post-close` vía `tools/liquidity_shadow.py`). Skills
(`pre-market.md`, `post-close.md`) actualizadas igual.

## v3.1.12 (2026-08-20) — S4 SWP RETIRADO de LIVE; long-only con solo S2 FVG + S1 RSI2

Decisión usuario tras research exhaustivo de la sesión sobre por qué S4 SWP (y el shadow LWR)
pierden plata pese a hit rate ~65% (ver `project_s4_lwr_path_analysis.md`). El backtest de 10 años
(v3.1.10) ya daba PF=0.93 (negativo 10/11 años). Hoy se probaron TRES vías de rescate distintas,
todas negativas:

1. **Diagnóstico MFE/MAE:** el TP actual (0.5R) corta ganadoras muy corto (mediana de excursión
   real ~0.65-0.71R) mientras el SL (1.0R) deja correr perdedoras demasiado (99.9% ya rompió -0.5R
   antes de -1R). Un grid de SL/TP alternativo re-escaneado sobre los trades reales encontró un
   "óptimo" (SL=0.15R/TP=1.2R, PF=1.29 positivo en 11/11 años) — **pero sin modelar slippage.**
2. **Con slippage realista ($0.01-0.02, spread típico de QQQ) el óptimo se derrumba** (PF 1.29→0.83)
   porque un SL más ajustado implica un R más chico, y el mismo costo fijo en dólares se come una
   porción mayor de cada trade. Con $0.02 de slippage, LOS TRES combos probados (actual, conservador,
   óptimo) quedan bajo PF=1.0, negativos en 9-10 de 11 años.
3. **Filtro de entrada por contexto** (hora del día, rvol, pendiente VWAP, RSI14, ganancia del día,
   profundidad del sweep): ningún tercil de ningún feature cruza PF=1.0 en ambas eras — el problema
   no es un subconjunto malo diluyendo un núcleo bueno, la señal es mediocre de forma uniforme.
4. **TP=SL (R:R 1:1):** el hit rate del 65% es específico del TP ajustado a 0.5R, no una propiedad
   del setup — al subir el TP a igualar el SL, el hit rate colapsa a ~49-51% (peor que azar) y
   cancela la mejora de R:R. Mejor caso de toda la prueba (sin slippage): PF=1.04, y se derrumba a
   0.77 con fricción real.
5. **Barrido de SL entre 0.5R y 1.0R** (TP=0.5R fijo, el actual): el hit ratio máximo YA está en la
   config actual (SL=1.0R, hit 64.7-65.3%) — pero **0 de 11 años positivos en TODO el rango**, sin
   importar dónde se ponga el SL. El PF con slippage se mantiene plano (~0.74-0.76 S4, ~0.49-0.56
   LWR) en todo el barrido.

**Conclusión: el edge crudo de S4 SWP (y de LWR) es insuficiente frente al costo de ejecución real
de QQQ en 1-min — no es un problema de calibración de parámetros.** Sacado de STEP 6 (bloque de
señal completo), de la tabla de sistemas, de la prioridad multi-posición (S2>S1>S4 → S2>S1), del
INSERT de `trades` (quitado `swp_v3` de la lista de strategy), de MODO REPOSO (quitado `c4.swp`),
y de RESTRICCIONES PERMANENTES. **Vuelve a long-only con solo 2 sistemas: S2 FVG + S1 RSI2.**
LWR (shadow, nunca llegó a LIVE) se archiva en `strategy_registry` por el mismo research — no tenía
camino de rescate tampoco (ver `project_liquidity_wick_reversal.md`).

Adaptadas las skills globales igual que en v3.1.11 (`pre-market.md`, `post-close.md`,
`load-memory.md`).

## v3.1.11 (2026-08-19) — S2 FVG filtra el fill ordinal #2 del día

Misma sesión que v3.1.10. Se probó primero un filtro combinado de entrada (slope_up & above_vwap &
risk 0.30-0.50, las tres condiciones que por separado se veían mejor en el cross-tab de 10 años) —
**empeoró el sistema** (PF pool 0.96 vs 1.02 sin filtro, inestable año a año: 2018/2019 con
PF=0.51). Apilar condiciones que se ven bien por separado no se sostiene juntas.

Lo que sí funcionó, mucho más simple: excluir específicamente el fill **ordinal #2** del día (sin
tocar ninguna otra condición). `tools/lab/s2_fvg_combined_filter.py`, 10 años: el fill #2 es
consistentemente el peor de los 5 ordinales (pnl agregado −46.46 vs +28/+17/+7/+30 del resto).
Excluirlo da PF pool 1.07 (+81.16 vs +34.71 del sistema sin filtrar) y PF 1.12 en 2023-2026
(+68.20 vs +53.48) — mejor en TODAS las ventanas, positivo en 9 de 11 años.

**No se puede implementar en la formación de la señal** (no se sabe de antemano si un triplete va
a fillear o expirar — el ordinal del backtest cuenta FILLS reales, no intentos formados).
Implementado en STEP 7-fill (paso 1b, nuevo): si el fill que acaba de confirmar sería el #2 real
del día (`fvg.fills_today == 1` y `NOT fvg.ordinal2_used`), se aplana INMEDIATO con market sell en
vez de sostenerlo — spread mínimo, sin exposición real. No se arma OCO, no se hace append a
`state.positions`, no se inserta en `trades` (no fue una operación real). `fvg.ordinal2_used` se
marca `true` para no volver a saltar otro fill el mismo día; `fvg.fills_today` NO se incrementa, así
que el próximo fill FVG real pasa a contar como "#2" (renumeración natural — el motor de backtest
hace lo mismo al remover la posición 2 sin renumerar el resto).

Adaptadas las skills globales (`pre-market.md`, `post-close.md`, `load-memory.md`, viven fuera del
repo en `~/.claude/commands/`) para reflejar v3.1.10/v3.1.11: `pre-market.md` ya estaba desactualizado
desde antes de hoy (rsi14/atr1m/xvwap_count/gates.gapf_on/computed_1030 seguían en el JSON de
`session_state` pese a estar podados hace tiempo o nunca haber tenido consumidor vigente) — corregido
de una vez, más el campo nuevo `fvg.ordinal2_used`. `post-close.md` todavía trataba a S6 SWP-short
como LIVE y chequeaba el gate de VWAPPB — corregido, y su sección de FVG por ordinal ahora verifica
que el filtro se aplicó (busca la línea `FVG ordinal#2 filtrado` en el output del día) en vez de
solo trackear para una decisión futura.

## v3.1.10 (2026-08-19) — S3 VWAPPB y S6 SWP-short RETIRADOS de LIVE; long-only otra vez

Decisión usuario tras backtestear los 5 sistemas LIVE contra los 10 años completos de 1-min QQQ
(2016-2026, `tools/data/qqq_1min/` — ver `project_macro_cycle_research.md` para cómo se armó ese
dataset y `project_systems_history.md` para el detalle completo del backtest). Con C4 activo
(igual que en producción):

| Sistema | n (10y) | hit% | PF | pnl/share | Veredicto |
|---|---|---|---|---|---|
| S1 RSI2 | 13,499 | 65.6% | 1.05 | +101.55 | Sólido, positivo casi todos los años → sigue LIVE |
| S2 FVG | 9,601 | 33.5% | 1.02 | +34.71 | Positivo (gracias a C4) → sigue LIVE |
| S3 VWAPPB | 10,079 | 49.9% | 0.99 | -11.67 | Breakeven → **RETIRADO** |
| S4 SWP | 2,336 | 64.9% | 0.93 | -29.98 | Negativo 10/11 años → sigue LIVE en revisión (ver abajo) |
| S6 SWP-short | 2,829 | 65.4% | 0.99 | -5.33 | Breakeven → **RETIRADO** |

**S3 y S6 salen de LIVE.** Con S6 fuera, el sistema vuelve a ser 100% long-only — se podó toda la
mecánica de short: exclusión de dirección long/short (STEP 6 y multi-posición), invariante de
reconciliación con signo (STEP 3, vuelve a `Σqty == net qty` simple), rama short del OCO en
STEP 7-fill, `dir:"long"|"short"` en `state.positions`, y las columnas `swp_short_v3`/`vwappb_v3`
del INSERT de `trades`. Huérfanos por la salida de S3: `rsi14` 1-min, `atr1m`, `xvwap_count`,
`gates.vwappb_on` (STEP 5, gate de las 10:30) — podados de STEP 4/STEP 8, siguiendo el mismo
criterio que la poda de `ema9`/`ema21` en v3.1.5 (cero consumidores vivos). El lookback de S1
(`atr5m`/`rsi2` 5-min) sigue intacto y es ahora el único consumidor de la lección de seed-de-dos-
fases-Wilder de v3.1.8 (generalizada en STEP 2-bis, ya no habla específicamente de RSI14/ATR1m).

**S4 SWP se recalibró y NO se encontró arreglo por parámetros.** `tools/lab/s4_swp_recalibration.py`
barrió TP∈{0.3R..1.5R} × min_depth∈{0.01,0.10,0.30} y por separado el buffer del SL∈{0.02..0.20}
con TP∈{0.5R,0.75R,1.0R} — con la muestra grande y confiable (min_depth=0.01, n=1971-2481 según la
celda), **PF se mantuvo por debajo de 1.0 en absolutamente todas las combinaciones probadas.** Las
pocas celdas con PF>1.0 aparecen solo con min_depth=0.30, que recorta la muestra a ~200 trades en
10 años (18-20/año) — año por año esas mismas celdas van de PF=0.06 a PF=1.49, ruido de muestra
chica, no una señal real. Conclusión: el problema de S4 no es la calibración de TP/SL, es que el
filtro de entrada (sweep de session low + reclaim + volumen ≥1.5×prom5) no tiene edge suficiente
por sí mismo en 10 años de datos. Sigue LIVE (con C4, que amortigua pero no arregla el problema
estructural) mientras se evalúa un rediseño del entry — no re-tocar TP/SL sin una idea nueva de
filtro, ya se demostró que no alcanza.

## v3.1.9 (2026-08-14) — STEP 4-shadow: update_indicators() en sombra (Fase 3 migración SQL)

Misma sesión que v3.1.8. Al re-validar ATR1m post-fix (contra un cold-start simulado con barras
reales del 08-13 alimentadas a `update_indicators()` desde `session_state` vacío), apareció un
SEGUNDO bug, esta vez en la función SQL misma (no en la prosa): la rama "bar 0 del día" seedeaba
`atr1m` con su propio rango H-L y lo contaba como elemento 1/14 del seed — un comentario en el
código afirmaba falsamente que esto emulaba `tools/backtest.py:wilder_atr`, que en realidad
DESCARTA ese primer TR del seed (usa `trs[1..14]`, no `trs[0..13]`). Confirmado empíricamente:
SQL daba `atr1m=0.2977` vs `0.2804` de la referencia Python para el mismo slice de 15 barras.
Corregido (migración `fix_update_indicators_atr1m_first_bar_seed`): el bar 0 ahora no aporta a
NINGÚN acumulador, simétrico con RSI14 (que ya lo hacía bien). Re-validado exacto en 2 checkpoints
(seed-boundary n=14 y steady-state 15 barras después) — Fase 2 de la migración cierra con confianza.

Con Fase 2 cerrada, se parametrizó `update_indicators(p_date, p_new_bars, p_key default 'QQQ')`
para poder escribir a un namespace aislado (`QQQ_shadow`) sin colisionar con `state.QQQ` (prosa,
autoritativa), y se arrancó Fase 3 (shadow rollout): STEP 4-shadow corre la función en sombra cada
ciclo sobre las mismas barras que STEP 4 ya procesó (sin fetch ni round-trip nuevo), envuelta en
`DO $$ ... EXCEPTION WHEN OTHERS ...$$` para que un fallo del shadow nunca pueda tumbar el UPDATE
crítico de session_state/cycle_log/wakeup del mismo batch. Cero impacto en trading: STEP 6/6b/7
siguen leyendo EXCLUSIVAMENTE la prosa. Objetivo: 2-3 sesiones de `state.QQQ_shadow` vs `state.QQQ`
antes de evaluar Fase 4 (cutover real) — detalle completo en `project_sql_indicators_migration.md`.

## v3.1.8 (2026-08-14) — seed de dos fases para RSI14/ATR1m en cold-start

Detectado validando `update_indicators()`, una función SQL nueva (proyecto de migrar STEP 4 de
prosa a Postgres — ver `project_cycle_latency.md`): replayeando barras reales del 08-13 contra la
fórmula Wilder de referencia (`tools/backtest.py:wilder_atr`), el `atr1m` correcto daba ~0.517
mientras el loop en vivo había logueado 0.45 ese ciclo — un sesgo ~15% bajo. RSI14 y VWAP, en
cambio, coincidían casi exacto. Causa: `session_state.QQQ.atr1m` se guarda como escalar simple (a
diferencia de `rsi14`, que es `{ag,al}`), y STEP 2-bis (cold-start) solo decía "usa las fórmulas
del STEP 4" — que documentan ÚNICAMENTE la recursión de estado estable (`atr=(atr×13+tr)/14`), no
el seed de dos fases (promedio de los primeros 14 TRs, recién después recursión) que
`pre-market.md` STEP 3 sí especifica bien. Si un cold-start aplicó la recursión desde `atr1m=0`
en vez de sembrarla, el sesgo no se autocorrige (memoria larga de Wilder) — y `atr1m` fija el
TP/SL real de S3 VWAPPB. Fix: STEP 2-bis ahora especifica el seed de dos fases explícitamente,
igual que pre-market.md. No se pudo confirmar la causa raíz exacta del 08-13 (no hay historial
minuto a minuto de `session_state`) — el fix cierra el vacío del spec hacia adelante.

## v3.1.7 (2026-08-09) — S6 SWP-short LIVE persistido en el archivo

La promoción real ya venía de antes (7 trades 08-03/08-04, decisión usuario 08-07 de continuar
hasta n=100) pero había quedado solo en el contexto de una sesión del loop, nunca guardada en
`cycle_prompt.md`. Una sesión nueva releyó el archivo en SHADOW y S6 dejó de ordenar sin que nadie
lo decidiera — ver `project_short_enablement.md`. Corregido: S6 en STEP 6 (LIVE) de forma
persistente, primer sistema SHORT con órdenes reales, exclusión de dirección long/short ACTIVA.

## v3.1.6 (2026-07-29) — hard-limit gap_recovery S4 SWP

Bug detectado en sesión 07-29: el loop murió 3h16min (12:03–15:19 ET), al recuperar encontró un
sweep+reclaim de las 12:15 ET y colocó la orden SWP con la señal 3h antigua. La reclaim hypothesis
expira con el tiempo — el precio ya se movió y no hay predicción válida. Se añade en STEP 6 (S4 SWP):
si `now_ET − t_reclaim > 60 min` → log `swp_stale_abort` y skip. FVG mantiene su propio stale check
de 5 min (triplet formation). Decisión del usuario: hard-limit aprobado; FVG sigue LIVE (score=3.3
en zona KILLED pero n=22 bajo — esperar 3-5 trades más para veredicto con muestra mayor).

## v3.1.5 (2026-07-20) — poda de contexto muerto (auditoría señal/ruido)

Auditoría a demanda del usuario (calidad de contexto > cantidad): mapeo productor→consumidor de los
8 indicadores por ciclo. **`ema9` y `ema21` se computaban e escribían a `session_state` cada ciclo
(~64/día) con CERO consumidores vivos** — sus únicos usuarios (E9RC-reclaim y S5 GAPF) están muertos
(GAPF descartada 07-10). Eliminados de STEP 4 (cómputo), STEP 8 (indicators JSONB) y del seed de
/pre-market. Cero cambio de lógica de trading — misma poda de contexto-que-estorba que v3.0 hizo con
ORB/VolAbs/filtro-EMA/régimen-TREND-RANGE/tick-fetches. `rsi14`/`atr1m` quedan marcados "SOLO S3
VWAPPB" (soporte vital — mueren con VWAPPB si el ranking lo mata). Nota: `gapf_on` sigue en el seed
de /pre-market como vestigio (gate muerto 07-10) — pendiente de poda menor.

## v3.1.4 (2026-07-16) — fase computada en SQL + prohibido saltar sellos (auditoría de timing)

Auditoría a demanda del usuario ("las confusiones de horario y el PASSIVE prematuro son
inaceptables y continúan"): el 07-14 el agente entró en PASSIVE a las 11:30 AM **pese al blindaje
de deltas de v3.1.2** (la prohibición en prosa no detiene el razonamiento de hora de pared del LLM),
y con el loop VIVO se perdieron **52 velas en 5 sesiones (~10/día, ~16%)** por la regla
"si el sello queda a <45s → salta al siguiente".
- **`fase_sql`:** el STEP 0 ahora trae la fase COMPUTADA por Postgres (zona IANA, DST-proof):
  PRE/ACTIVE/PASSIVE/CLOSE. El agente tiene PROHIBIDO derivar fase de cualquier otra fuente;
  get_clock solo aporta is_open y el override de early-close (deltas, solo puede adelantar).
  Actuar PASSIVE/CLOSE con fase_sql='ACTIVE' = bug_mecanico reportado por 4f; transición sin
  evidencia impresa (`fase_sql=X et_now=HH:MM:SS`) es inválida.
- **Sello inmediato SIEMPRE:** wakes (ciclo y KA) apuntan al próximo sello+10 aunque falten <60s
  (mínimo 60 → llega ~sello+65, tarde pero la vela SE EVALÚA). La regla vieja regalaba la vela entera.
- **4f nuevos checks fijos:** `premature_passive` · `abort_violation` (lat_s>150 colocada: 07-09
  216s, 07-16 184s) · métrica diaria `velas_perdidas_vivo` (target ≤2; baseline ~10).
 — S5 GAPF descartada + fixes de la primera semana LIVE

Revisión de resultados 07-06→07-09 (usuario: "analizar, corregir/ajustar; promover/descartar"):
- **S5 GAPF DESCARTADA** (triple confirmación): backtest fresco 57 sesiones n=14 PF 0.63 −$10.79/sh
  · shadow vivo n=3 33% −$2.25/sh · primo diario mr_gapdn muerto en FDR L1. Registry → archived;
  gate gapf_on eliminado; clave `gapf` congelada con su histórico.
- **Resolución shadow SECUENCIAL en /post-close** (hallazgo mayor): el shadow no-secuencial de SWPS
  contaba clusters de señales solapadas (56.5%) mientras el backtest secuencial de la MISMA ventana
  da 88.9% a 0.5R — medíamos otro sistema. Desde 07-10: señal que entra con trade simulado abierto
  del mismo sistema → `skip_overlap`. Nueva lectura del edge de SWPS: vive en días ALCISTAS
  (85.7% hit; en bajistas casi no genera señales — no hay nuevos highs).
- **KA: ScheduleWakeup obligatorio y verificado antes de cerrar el turno** (07-07: loop muerto 5h
  desde 10:50, causa más probable un turno que terminó sin programar wake).
- **Abort S1 >150s INCONDICIONAL** (07-09: señal con lat 216s colocada igual — ganó, pero fuera de
  spec) + **PRELOAD de tools alpaca en el primer ciclo** (la carga vía ToolSearch a mitad de ciclo
  causó esa latencia).
- **Coherencia de notes OCO** en STEP 7 (07-06: outage corrompió un notes con sl>entry).
- fetch_data.py: `end` dinámico (estaba hardcodeado a 06-26 — la caché semanal envejecía en silencio).

## v3.1.2 (2026-07-06) — keep-alive de caché + fase por deltas (blindaje anti-cierre prematuro)

Respuesta al primer día de v3.1.1 con 4 LIVE: dos gaps por tokens (10:36→11:17 y 12:50→14:28,
~2h20m total; S1 perdió 5-7 señales por abort de latencia post-outage) + alerta del usuario sobre
cierres/pasivo a medio día.
- **Keep-alive (EXPERIMENTO, OK usuario 07-06):** wake KA a mitad de intervalo (anclado al
  boundary: `max(60, delay_aligned−150)` — un +150 fijo saltaría velas cuando el ciclo termina
  tarde) → ambas relecturas de contexto quedan <300s → input a precio de caché (~10%). El turno KA
  solo hace get_clock + ScheduleWakeup; PROHIBIDO decidir fase, tocar posiciones o escribir DB.
  Revertir si en 1-2 sesiones se pierden wakes o la cadencia degrada vs baseline 5m05s.
- **STEP 1 por DELTAS de get_clock:** fase desde `mins_to_close = next_close − timestamp` (mismo
  response, mismo huso — inmune al bug UTC/ET del 06-12). PROHIBIDO PASSIVE/STEP 10 con
  mins_to_close > 30; tras outage la duda se resuelve hacia ACTIVO. Cubre gratis los cierres
  tempranos (13:00).


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

## Pre-v3.0 (Pulse v2.x, 2026-06-01 → 06-18) — primeras sesiones, journal condensado

Retirado de memoria 2026-08-09 (archivo `project_history_recaps.md`, journal narrativo — casi todas
las lecciones ya son reglas activas en `feedback_*.md`, referenciadas abajo). Capital: ~$100k inicial
→ $100,213 (fin semana 1) → $100,287 (06-02) → $100,267 (06-08) → $100,078 (06-09, drawdown ~$245).

- **Semana 1 (06-01→06-05):** −$59.05, 3/8 WR. Salieron: EMA filter dropped, OCO obligatorio, filter
  sealed bars, slippage protection FVG, QQQ-only (tras SL combinado −$24.27 en TSLA/RIVN), FVG
  limit-on-formation, no-time-gates.
- **06-02:** −$5.41. Bugs: barras no selladas contaminando indicadores, sin OCO broker-side.
- **06-08:** +$51.19, 9 trades FVG 67% WR. Validó FVG limit-on-formation + OCO re-arm. Gap de 87min
  por tokens → semilla de la disciplina de ahorro de tokens.
- **06-09 (catastrófica):** −$186.44, 0/5 WR. 3 FVGs stacked sin OCO armado + `order_class="bracket"`
  con SL leg `held` sin activar → prohibido `bracket`, exigido `oco` desde entonces.
- **06-11 (primera sesión v3.0):** +$14.50. Corriendo en Haiku: terminó turnos sin `ScheduleWakeup`
  → decisión usuario: todo el trading en Sonnet desde entonces.
- **06-12 (bug forense más caro):** emergency SL −$4.62. Bug UTC/ET: barras UTC leídas como hora ET
  → loop muerto 72 min en pleno selloff (2 señales que habrían disparado C4 nunca evaluadas). Semilla
  directa de la regla "fase solo desde get_clock".
- **06-18:** FVG +$6.49, RSI2 shadow 67% hit, S6 shadow 80% hit. Gap recovery de 2h reconstruyó 21
  bloques 5-min sin corromper la cadena RSI2 — validó que el gap-recovery funciona. Nació la
  observación de "ciclos lentos".
