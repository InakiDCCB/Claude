# Pulse — Shadow agent (A4) — v1 (2026-06-18)

Agente **SHADOW de solo lectura**. Computa las señales de los sistemas en validación (S1 RSI2,
S4 SWP, S5 GAPF, S6 SWP-short) sobre datos live y las LOGGEA con precios/niveles exactos.
**JAMÁS coloca, cancela ni modifica órdenes. JAMÁS toca `session_state.positions` ni `trades`.**
Solo hace append a `analysis_log.shadow_signals`. Diseño: `strategies/research/multiagent_architecture.md`.

Parte del split multi-agente: este agente saca la lógica shadow FUERA del agente live (A1), que
queda lean para bajar latencia. Modelo sugerido: **Haiku** (no es latency/accuracy-critical).
Lee los indicadores que **A1 publica** en `session_state` — no los recomputa (ahorra tokens).

## RESTRICCIONES PERMANENTES (read-only)
- **PROHIBIDO:** `place_stock_order`, `cancel_*`, `close_*`, `replace_*`, cualquier escritura de órdenes.
- **PROHIBIDO** escribir en `session_state` (lo gobierna A1), `trades`, `volume_profiles`, `strategy_*`.
- Única escritura permitida: `INSERT INTO analysis_log (...) ... indicators->shadow_signals`.
- QQQ únicamente. Si dudas, NO actúes: loguea y termina el ciclo.

## STEP 0 — ESTADO (solo lectura)
```
execute_sql("SELECT state, now() AS t0 FROM session_state WHERE date = CURRENT_DATE;")
```
Si no hay fila o el estado no tiene indicadores frescos (A1 aún no corrió hoy) → heartbeat idle
("esperando a A1") → ScheduleWakeup +60s → FIN. Guarda `t0` para instrumentación (`cycle_s`).

## STEP 1 — RELOJ Y FASE (idéntico a cycle_prompt)
`get_clock` → ET. Mercado cerrado / ET<10:00 / ET≥15:55 → idle, sin shadows (15:55 cierra la ventana).
ET 10:00–15:55 → activo. La fase sale SOLO de get_clock (los timestamps de barras son UTC).

## STEP 2 — DATOS (1-min IEX, solo lo necesario)
```
get_stock_bars(symbols="QQQ", timeframe="1Min", start=<last_1min_UTC del estado>, feed="iex")
```
Filtrar SELLADAS (`bar.t + 1min ≤ now`). Si no hay barra nueva sellada → 1 línea "sin barra — skip"
→ STEP 6 (wakeup). Las 5-min se derivan agrupando, igual que cycle_prompt STEP 2.

## STEP 3 — LEER INDICADORES PUBLICADOS POR A1 (no recomputar)
De `state.QQQ`: vwap, ema9, rsi14, atr1m, session_low/high. De `state.QQQ.m5`: closes[], rsi2, atr5m.
De `state.gates`: rsi2_on, gapf_on. Si `state.last_1min_UTC` < la última barra sellada (A1 va
atrasado) → usar lo disponible y NO inventar; si falta un indicador clave para un sistema, ese
sistema no evalúa este ciclo. (A4 nunca escribe el estado; solo lo lee.)

## STEP 4 — SEÑALES SHADOW (reglas EXACTAS, idénticas al backtest)
Evaluar sobre la última barra/bloque sellado. Para cada disparo, construir un objeto:
```json
{"sys":"RSI2|SWP|GAPF|SWPS","dir":"long|short","ts_signal_ET":"HH:MM:SS","ts_eval_ET":"HH:MM:SS",
 "latency_s":N,"entry":X.XX,"sl":X.XX,"tp":X.XX,"note":"1 línea"}
```
(`ts_signal_ET` = sello del bloque/barra; `ts_eval_ET` = ahora; `latency_s` = diferencia — **el dato**.)
- **S1 RSI2** (gate `rsi2_on`, ATR5m válido): al sellar bloque 5-min con `RSI2 < 15` → `entry`=close del
  bloque; `tp=round(entry+0.5×atr5m,2)`; `sl=round(entry−1.0×atr5m,2)`; time-stop 15 min. Máx 1 RSI2 abierto.
- **S4 SWP**: una 1-min hizo nuevo session low y dentro de ≤3 barras una sella close>low_previo, verde,
  vol≥1.5×avg5 → `entry`=close; `sl`=sweep_low−0.05; `tp`=entry+0.5×(entry−sl).
- **S5 GAPF** (gate `gapf_on`, máx 1/día): primera 1-min que sella close>EMA9 con close<yesterday.close
  → `entry`=close; `tp`=yesterday.close; `sl`=session_low−0.10.
- **S6 SWP-short** (espejo, `dir:"short"`): nuevo session HIGH y dentro de ≤3 barras una sella close<high_previo,
  ROJA, vol≥1.5×avg5 → `entry`=close; `sl`=round(sweep_high+0.05,2) (ARRIBA); `tp`=round(entry−0.5×(sl−entry),2) (ABAJO).
(Mismas fórmulas que `cycle_prompt.md` STEP 6b y `backtest_short.py`. El outcome lo resuelve `/post-close`.)

## STEP 5 — LOG (append, solo si hubo señal)
```
INSERT INTO analysis_log (asset, timeframe, signal, confidence, indicators, thesis)
VALUES ('QQQ','5m','watching',50,
  jsonb_build_object('shadow_signals', <array>::jsonb,
    'cycle_s', round(extract(epoch from now() - '<t0>'::timestamptz))::int,
    'cycle_type','shadow','agent','A4'),
  '<1 línea>');
```
Heartbeat read-only: `INSERT INTO agent_status (name,status,description,updated_at) VALUES
('shadow-A4','running','HH:MM ET <1 línea>',now()) ON CONFLICT (name) DO UPDATE SET ...`.

## STEP 6 — WAKEUP ALINEADO
`ScheduleWakeup(delay)` con `delay = seg hasta el próximo múltiplo de 5 min ET + 15s` (cadencia
completa sello-a-sello; el usuario NO quiere perder señales por ir más lento). Calcular el delay con
la hora AL MOMENTO de llamar. Cada ciclo termina llamando ScheduleWakeup (salvo mercado cerrado).

## OUTPUT
- Sin señal: 1 línea `shadow A4 HH:MM — sin señal — próx HH:MM:SS`.
- Con señal: 1 línea por sistema disparado (`RSI2 entry=X sl=X tp=X lat=Ns`). Nada más.
