# Spec C.2 + C.3 + C.4 — Integración del Conocimiento (situacional · semanal · fuente única)

**Activada:** 2026-07-01 · **Épica:** C (Sistema de Aprendizaje) · **Tipo:** diseño → implementación gated
**Principio:** el conocimiento nuevo entra por los MISMOS raíles deterministas de Fase 3/3.1
(funciones SQL + vistas + gates min-N). Nada modifica el loop ni crea reglas automáticas.

---

## C.2 — `/situational` → Sistema de Aprendizaje

**Qué conservar (estructurado, aprendible):** `bias` + `confidence` + `gap_type` + `range_structure`
del **primer snapshot QQQ del día** (el predictivo — antes de conocer el desenlace).
**Qué sintetizar:** nada extra — los niveles ya viven en la fila.
**Qué descartar del aprendizaje:** la tesis narrativa (`thesis`) — queda en la tabla para lectura humana.

**Mecánica (2 extensiones a funciones existentes):**
1. `classify_market_context()` v2 — LEFT JOIN al primer snapshot del día: añade tags
   `sit_<bias>` + `<gap_type>` y claves `situational_bias/sit_confidence/sit_range_structure`
   en `signature`. Sesión sin snapshot → sin tags (no inventa).
2. `refresh_market_patterns()` v2 — nuevo bloque `kind='precursor'`: **precisión del bias**
   medida contra el cierre real (`volume_profiles.session_close` del mismo día):
   bullish acierta si `close > t_current` del snapshot; bearish si `<`; neutral/mixed no evaluables.
   Patrón por bias con `n_support` / `effect` (= accuracy − 0.5); mismos gates min-N → la hipótesis
   "el bias X de /situational predice" emerge SOLA con evidencia, nunca por diseño.

**Fix obligatorio detectado:** `situational.md` aún referencia **TSLA/RIVN** (pre QQQ-only; el
constraint de la tabla ya rechazaría esos INSERTs) → actualizar el skill a QQQ únicamente.

### C.2 **v2** (decisión usuario 2026-07-02 — supersede la mecánica intradía de arriba)
El usuario pidió NO correr `/situational` a mano: queda **integrado en /post-close** y reorientado a
"comportamientos interdía comprobables con datos". Implementación (migración `c2v2_situational_autopostclose`):
- `situational_analysis.rule` (columna nueva) + función **`situational_snapshot(d)`**: al cierre de D
  computa estructura D-1→D (desde volume_profiles + gap_pct de market_conditions; t_open derivado) y
  **teoriza D+1** con reglas fijas: `gap_up/down_sin_llenar` (0.6) · `naked_vpoc_iman` (0.55) ·
  `hh/ll_agotamiento` (0.5) · `inside_breakout_esperado` / `expansion_reversion` (mixed, no evaluables
  direccional) · `default` neutral. Fila única idempotente `notes='auto_postclose_d1'`.
- `refresh_market_patterns` **v3**: precursor con semántica D→D+1 — precisión por **bias** (`sit:*`) y
  por **regla** (`sitr:*`) contra el cierre de la sesión siguiente. Solo evalúa filas auto; las
  manuales del skill (ad-hoc intradía) son informativas. Legacy 06-02 excluida (semántica distinta).
- post-close 4d: `situational_snapshot()` corre ANTES de `classify_market_context()` (los tags `sit_*`
  del contexto ahora significan "al cierre de D, sesgo para D+1").
- Backfill 07-02 sobre 12 sesiones: reglas pobladas; sit:bearish 3/3, gap_up_sin_llenar 2/2,
  naked_vpoc 0/1 — todo `emerging`, 0 hipótesis (gates min-N intactos).

## C.3 — Comandos semanales → `/post-close`

**Análisis de cadencia:** `fetch_data.py` + `analysis_30d.py` + `final_portfolio.py` se QUEDAN
SEMANALES (backtests pesados; la ventana 30d se mueve lento — correrlos a diario = costo sin señal).
Ninguno pasa a diario. `smc_shadow.py` sigue fetcheando su día por separado (día vs histórico —
duplicación aceptable, documentada).

**Lo que faltaba (el gap real):** los resultados semanales NO persistían — vivían en el chat y en
memoria estática que envejece. **Integración:** el paso de viernes de `/post-close` se formaliza:
tras correr los 3 scripts, INSERT de un snapshot por sistema en `strategy_performance` con
`scope='backtest'`, `time_window='30d'` (n, wins, wr, pf, expectancy, pnl_total; tier por los mismos
umbrales). Cero schema nuevo (la unique key `as_of×strategy_id×scope×time_window` ya lo soporta).
El conocimiento semanal queda versionado, consultable junto al live y comparable en el tiempo
(backtest vs shadow vs real del MISMO strategy_id).

## C.4 — Fuente única de conocimiento

**Pieza nueva:** vista **`v_shadow_accumulated`** — la reconciliación que C.1 hizo a mano, como
vista viva: por sistema, sessions / n / tp / sl / time / miss / WR / pnl desde las claves canónicas
de `session_memory.observations` (parseo regex-guard). La leen dashboard, `/load-memory` (research)
y `/post-close` (veredictos) — **una sola definición, cero recomputos manuales divergentes**.

**El mapa del conocimiento (todo vistas DB, todo alimentado por /post-close):**

| Pregunta | Fuente única |
|---|---|
| ¿Qué contexto tiene el mercado? | `v_market_context` / `v_market_intelligence` |
| ¿Qué patrones/hipótesis hay? | `v_market_patterns` / `v_market_hypotheses` |
| ¿Cómo van los shadows acumulados? | `v_shadow_accumulated` (nueva) |
| ¿Cómo rankean las estrategias (real)? | `v_strategy_ranking` |
| ¿Qué dice el backtest semanal? | `strategy_performance` scope='backtest' |
| ¿Acierta el sesgo situacional? | `v_market_patterns` kind='precursor' |

## Criterios de aceptación
1. Migración aplicada; re-run de classify+patterns sobre el histórico NO genera hipótesis espurias
   (gates aguantan — el precursor arranca con n=1 evaluable como mucho).
2. `v_shadow_accumulated` devuelve exactamente los acumulados reconciliados en C.1 (S6 n=17 64.7%,
   OB n=22 36%, RSI2 n=51).
3. `situational.md` QQQ-only; `post-close.md` con paso viernes formalizado.
4. Docs/memoria actualizados (mapa del conocimiento en `reference_market_intelligence.md`).

## Fuera de alcance
Automatizar la corrida de `/situational` (sigue siendo manual/opcional del usuario); cambiar el loop;
que las recomendaciones actúen solas (Épica G).
