# CLAUDE.md — Aconcagua Trader

## Migration status

`Agent_Aconcagua` es el reemplazo de `C:\Users\inaki\Code\Trading\Claude` — el mismo sistema de paper-trading de QQQ (historial de git preservado vía rename, no un repo nuevo), reordenado bajo el framework WAT y las tres máximas de abajo. Estado de la migración:

- ✅ Carpetas reorganizadas: `workflows/`, `tools/` (+ `tools/lab/`), `docs/` (aplanado), `.tmp/` ya existen y reflejan la estructura de abajo.
- 🚧 **Pendiente**: fusionar `.claude/memory/` (21 archivos) y `.claude/commands/` que quedaron en una carpeta hermana temporal `Agent_Aconcagua_new/.claude/` — el clasificador de la sesión bloquea escrituras dentro de `.claude/`, así que ese merge puntual lo hace el usuario a mano.
- 🚧 **Pendiente**: los skills globales (`~/.claude/commands/load-memory.md`, `post-close.md`) todavía apuntan a rutas de `Trading\Claude` (`strategies/research/*.py`, el path de memoria `C--Users-inaki-Code-Trading-Claude`) — hay que actualizarlos a `tools/*.py` y `C--Users-inaki-Code-Trading-Agent-Aconcagua` antes de confiar en `/pre-market` y `/post-close` para el loop en vivo.
- 🚧 **Pendiente**: consolidación/densificación del contenido de memoria (la tercera máxima, auto-aprendizaje más barato de releer).

## What This Is

Un agente de paper-trading que opera **QQQ únicamente** vía **Alpaca** (cuenta paper, MCP tools `mcp__alpaca__*`) para datos y ejecución, con todo registro/análisis en **Supabase**. Claude ES el agente — no hay un proceso Python separado orquestando; Claude llama las tools MCP directamente en cada ciclo. El proyecto viene de meses de iteración validada en `Trading\Claude` (spec actual: Pulse v3.1.5) y se reorganiza aquí bajo el framework **WAT** (`workflows/` · `Agent` · `tools/`).

## Las Tres Máximas

Toda decisión no trivial — qué estrategia promover, qué research priorizar, cómo simplificar memoria/specs — se evalúa contra estas tres, en este orden de precedencia cuando entran en conflicto:

1. **Maximizar P/L** — la métrica final. Se mide vía `trades` reconciliado con el broker (no `session_memory`), expectancy-LB por estrategia, y el PF del backtest semanal.
2. **Maximizar Hit Ratio** — win rate con Wilson lower-bound (no el crudo, que sobreestima con n bajo). Es el segundo componente del Score (`0.25 · exp_lb`) y el primer filtro de sanity antes de mirar P/L (una estrategia con buen P/L pero hit ratio bajo y varianza alta es más frágil que una consistente).
3. **Maximizar el auto-aprendizaje del modelo** — que el sistema mismo acumule y use lo que aprende, no que dependa de que el usuario se lo repita. Esto YA está parcialmente implementado (ver abajo) y es el eje que más se refina en esta migración: memoria más densa y mejor organizada = aprendizaje más barato de releer.

Estas tres ya están operacionalizadas en código, no son aspiracionales:
- **Score de estrategias** (`refresh_strategy_performance()`): `0.45·quality + 0.25·exp_lb + 0.30·robustness − drawdown` → tier `insufficient_data` / `provisional` / `established`; umbrales de acción DEPLOY≥65 / PAPER≥45 / KILLED<45.
- **Self-learning = `/post-close` leyendo lo que el loop ya escribió** (`trades`, `analysis_log`) una vez al día — no es un módulo aparte. Retroalimenta (a) niveles de mañana en `volume_profiles` → los consume `/pre-market`, y (b) el ranking de estrategias → el loop lo usa para priorizar cuando compiten señales por un slot. Nunca reescribe la spec ni promueve un shadow a LIVE por su cuenta: esa decisión es siempre del usuario.
- **Reflexión estructurada post-close** (Self-Refine): clasifica cada trade perdedor por modo de falla, audita cumplimiento de gates/sizing/OCO, y escanea movimientos perdidos — produce como máximo una "lesson" verificable por día, que solo se propone como regla tras repetirse ≥3 sesiones.

## WAT Architecture Applied Here

**Layer 1 — Workflows** (`workflows/`): la spec del loop en vivo (`cycle_prompt.md`, única fuente de verdad operacional — sistemas, gates, fórmulas, wakeups) + tres comandos globales invocados manualmente por el usuario cada sesión: `/load-memory`, `/pre-market`, `/post-close`. Estos tres viven en `C:\Users\inaki\.claude\commands\` como repo git local-only sin remote — **decisión explícita del usuario, no relitigar** (ver memoria `ref_skills_repo`).

**Layer 2 — Agent**: Claude Code mismo. Lee la workflow correspondiente a la fase del día, ejecuta las tools en el orden correcto, maneja fallos, y pregunta cuando hace falta (`AskUserQuestion` con 2-4 opciones y una recomendada, para decisiones no triviales). No hay agente Python separado — la separación WAT entre razonamiento probabilístico y ejecución determinista se logra con: Claude decide QUÉ hacer, los scripts en `tools/` y las funciones SQL en Supabase hacen el cálculo pesado (barato, determinista, sin riesgo de error del LLM).

**Layer 3 — Tools** (`tools/`): scripts Python puro-stdlib (motor de backtest, fetchers de datos, simuladores de shadow strategies, pipelines de minería de hipótesis) + funciones SQL en Supabase (`upsert_market_condition`, `refresh_strategy_performance`, `refresh_market_patterns`, etc.) para toda la matemática de aprendizaje continuo.

**Por qué importa la separación:** si cada paso del agente es 90% preciso, cinco pasos seguidos bajan a 59% de éxito. Delegar la ejecución a scripts/SQL deterministas mantiene a Claude enfocado en orquestación y decisión, donde es fuerte.

## Folder Structure

```
Agent_Aconcagua/
├── CLAUDE.md
├── .env / .mcp.json / .gitignore
├── workflows/
│   ├── cycle_prompt.md        # spec operacional del loop en vivo
│   ├── shadow_prompt.md       # agente shadow read-only
│   └── history/               # CHANGELOG + specs superseded
├── tools/
│   ├── *.py                   # scripts de producción invocados por los skills (fetch_data, td_shadow, sentiment_daily, analysis_30d, final_portfolio, backtest*)
│   └── lab/                   # research exploratorio/one-off (gt_factory*, gt_intraday*, smc_*, horizon_lab, calibrate_rsi2)
├── docs/                       # audits + specs de diseño, un solo nivel
├── supabase/schema.sql
├── dashboard/                  # Next.js/Vercel — sin cambios estructurales
└── .tmp/                       # datos cacheados / regenerables (antes strategies/research/data/)
```

## Trading System Summary — Pulse v3.1.5

`workflows/cycle_prompt.md` es la **única fuente de verdad operacional**. Este resumen es orientativo.

**Fases de sesión:**

| Phase          | ET window   | Action                                                       |
| -------------- | ----------- | ------------------------------------------------------------ |
| Pre-market     | 9:30–9:55   | `/pre-market`: seeds incrementales + niveles ayer + gates conocibles |
| Gates 10:00/10:30 | 10:00/10:30 | rvol30, gap_pct, open_loc, xvwap60 → fijan gates on/off  |
| Active trading | 10:00–15:30 | Ciclos alineados a velas 5-min; agente programa sus propios `ScheduleWakeup` |
| Passive        | 15:30–15:55 | Solo gestión de posición; sin entries nuevos                  |
| Close          | 15:55       | Cierre forzado total (`exit_type=TIME`)                       |
| Post-close     | ≥16:00      | `/post-close`: niveles de mañana + resolución de shadows + aprendizaje |

**Sistemas LIVE**: S2 FVG (limit al midpoint, gate rvol30), S3 VWAPPB (pullback VWAP, días choppy), S1 RSI2-dip (RSI2(5m)<15, tp/sl por ATR5m, time-stop 15m), S4 Sweep&Reclaim (sweep session-low + reclaim). Multi-posición: `state.positions[]`, máx 4, cap 70% suma, sizing 8%, prioridad por score. **C4 global**: 2 pérdidas consecutivas de un sistema → apagado hasta el día siguiente.

**Sistemas SHADOW (cero órdenes)**: S5 GapFill, S6 SWP-short, OB/OBNB, Golden Ticket (4 señales diarias), TD Sequential (TD9S). Se resuelven en `/post-close` como validación antes de una eventual promoción a LIVE — la promoción siempre la decide el usuario.

**Ejecución crítica**: única fuente de datos 1-min IEX (5-min derivadas por resampleo), indicadores incrementales en `session_state`, exits SIEMPRE broker-side vía OCO (4 params obligatorios; `order_class="bracket"` prohibido), safety-net de posición desprotegida como primera acción de cada ciclo. Modelo: **Sonnet para todo** (pre-market, loop, post-close, research — Haiku no sostiene la latencia <30s que exige el playbook).

## Dashboard

Next.js 14 en Vercel, capa de solo-lectura sobre Supabase (sin lógica de trading). Layout por prioridad de lectura: sesión de hoy → cuenta → performance → trades → validación/aprendizaje (ranking + shadows) → market intelligence → infraestructura. Detalle completo de componentes y rutas API: ver `docs/` tras la migración (hoy: `project_dashboard.md` en la memoria de `Trading\Claude`).

## Supabase Schema

Tablas clave: `trades`, `analysis_log`, `session_state`, `session_memory`, `volume_profiles`, `agent_status`, `champion_strategy`, `alpaca_state`, `strategy_registry`, `market_conditions`, `strategy_performance` (+ vista `v_strategy_ranking`). QQQ-only forzado por constraint en las tablas relevantes. Definición completa en `supabase/schema.sql`.

## User Skills (`/comandos` manuales)

| Skill | Cuándo | Qué hace |
|---|---|---|
| `/load-memory` | Al iniciar sesión | Carga memoria: default = modo trading lean; `full` = research |
| `/pre-market` | 9:30–9:55 ET | Seeds incrementales + niveles de ayer + gates conocibles → `session_state`. CERO órdenes |
| `/post-close` | ≥16:00 ET | Niveles de mañana + resolución de shadows + aprendizaje continuo + reflexión estructurada + `session_memory` |

Arranque diario (manual, sin cambios): `/load-memory` → `/pre-market` → lanzar el loop con `@workflows/cycle_prompt.md`. El agente programa sus propios wakeups dentro de esa sesión; un turno que termina sin `ScheduleWakeup` mata el loop (excepciones: STEP final del día completado, o mercado cerrado).

## Hard Constraints (permanentes)

- **Universo: QQQ únicamente** — sin excepciones.
- Long-only en LIVE; shorts solo como shadow.
- Exclusión ética: defensa (BA, LMT, TXN, NOC, RTX, GD, HII), farma (MRNA, PFE).
- Exits siempre broker-side vía OCO; cierre forzado 15:55 ET.
- Cambios estructurales a la spec requieren ≥3 sesiones de evidencia (no improvisar setups).
- Modelo Sonnet para todo el trabajo de trading.

## How to Operate

1. **Buscar tools existentes primero** en `tools/` antes de escribir un script nuevo.
2. **Aprender de cada fallo**: leer el error completo, arreglar el script, verificar, y documentar lo aprendido en la workflow correspondiente (rate limits, timing, comportamiento inesperado) — no lo dejes solo en el chat.
3. **Mantener las workflows al día**: no crear ni sobreescribir `cycle_prompt.md`/`shadow_prompt.md` sin preguntar, salvo instrucción explícita — son la fuente de verdad y deben preservarse con cuidado, no descartarse tras un solo uso.

**Bucle de auto-mejora**: identificar qué falló → arreglar la tool → verificar → actualizar la workflow con el nuevo approach → seguir con un sistema más robusto. Así es como el framework mejora con el tiempo — es la maquinaria concreta detrás de la tercera máxima (auto-aprendizaje).
