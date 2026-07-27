# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A paper trading research system for studying market behavior and developing strategies. Execution and market data go through **Alpaca** (paper account, configured in `.mcp.json`). All trade records and analysis are stored in **Supabase**. Strategy specs live in `strategies/` (current: `cycle_prompt.md` v3.1.5; older specs + CHANGELOG in `strategies/history/`).

## Key Principle

Claude uses the `mcp__alpaca__*` MCP tools directly for market data and order execution. No separate Python agent scripts — Claude IS the agent.

## Trading Loop (Pulse v3.1.5 — 2026-07-20)

**`strategies/cycle_prompt.md` es la ÚNICA fuente de verdad operacional** (sistemas, gates, fórmulas, wakeups). Este resumen es orientativo; si difieren, manda el cycle_prompt. v3.0 sale del playbook validado en 32 sesiones (`strategies/research/playbook_2026_06_10.md`); v3.0.1 (2026-06-12) añade fixes de ejecución post-mortem: fase solo desde get_clock, pre-submit check FVG con precio fresco, delay de wakeup computado al momento de la llamada, baseline vol30 en IEX. v3.0.2 (2026-06-15) elimina el tope de 1 fill/día del FVG (experimento de usuario): ahora francotirador secuencial gobernado por rvol30 + pre-submit + C4 + 1-posición; `/post-close` trackea performance por ordinal. v3.0.3 (2026-06-16) añade el shadow **S6 SWP-short** (sweep de session high + rechazo; único short que sobrevivió al backtest espejo — `strategies/research/backtest_short.py`); órdenes reales siguen LONG-only, S6 es shadow (cero órdenes) en validación 5 sesiones. v3.0.4 (2026-06-18) instrumenta latencia (`cycle_s`/`cycle_type`) + OB shadow batch en `/post-close`. v3.0.5 (2026-06-30) batching de I/O (lecturas en 1 batch paralelo + escrituras en 1 `execute_sql`). v3.0.6 (2026-07-01, diagnóstico B.1 `docs/audit_cycles_2026-07-01.md`) añade `state.cycle_log` (cadencia real medible, 1 timestamp/ciclo) + diferimiento del shadow en ciclos con trabajo pesado (`state.shadow_deferred`) — todo sin cambio de lógica de trading. **v3.1.0 (2026-07-03, decisión usuario): PROMOCIÓN S1 RSI2 + S4 SWP a LIVE + multi-posición** — `state.positions` (lista, ≤1 por estrategia, máx 4, cap 70% como suma, prioridad por score, exclusión long/short), sizing 8% para todos, S1 con time-stop 15 min agent-side y abort >150s del sello; S5 GAPF y S6 SWP-short siguen shadow. Validación: 5 sesiones paper sin incidente de reconciliación. **v3.1.1 (2026-07-03): dieta de contexto + modo reposo** (mitigación tokens/latencia, cero cambio de lógica de entradas) — ventana de barras 45→12min con gap-fallback escalonado, changelog movido a `strategies/history/CHANGELOG.md`, y wake 15min SOLO cuando ninguna entrada es posible (gates off / C4) y no hay posiciones ni limits. **v3.1.2 (2026-07-06): keep-alive de caché (experimento) + fase por deltas** — wake KA a mitad de intervalo (input cacheado ~10%; el turno KA solo hace get_clock+ScheduleWakeup, PROHIBIDO decidir fase) y STEP 1 desde `mins_to_close = next_close − timestamp` de get_clock (inmune a errores UTC/ET; PROHIBIDO PASSIVE/STEP 10 con >30 min al cierre; cubre cierres tempranos). Historial completo de versiones: `strategies/history/CHANGELOG.md`.

Session phases:

| Phase          | ET window   | Action                                                       |
| -------------- | ----------- | ------------------------------------------------------------ |
| Pre-market     | 9:30–9:55   | `/pre-market`: seeds incrementales + niveles ayer + gates conocibles |
| Gates 10:00    | 10:00       | rvol30, gap_pct, open_loc → fija fvg_on / rsi2_on / gapf_on  |
| Gates 10:30    | 10:30       | xvwap60 (cruces close-VWAP 1ª hora) → fija vwappb_on         |
| Active trading | 10:00–15:30 | Ciclos ALINEADOS a velas 5-min (wake = sello + 10s)          |
| Passive        | 15:30–15:55 | Solo gestión de posición; sin entries nuevos                  |
| Close          | 15:55       | Cierre forzado total (exit_type=TIME)                         |
| Post-close     | ≥16:00      | `/post-close`: niveles de mañana + resolución de shadows + **aprendizaje** (clasifica condición + recalcula ranking) |

Sistemas v3.1: **LIVE** = S2 FVG (limit al midpoint on-formation; gate rvol30 ≥ 0.85; fills secuenciales dentro de su slot), S3 VWAPPB (pullback a VWAP; solo días choppy con xvwap60 ≥ 6), **S1 RSI2-dip** (RSI2(5m)<15 → limit al close, tp 0.5×ATR5m / sl 1.0×ATR5m / ts15; gate open≥VAL; promovida 07-03) y **S4 Sweep&Reclaim** (sweep session low + reclaim con volumen → tp 0.5R; promovida 07-03). **SHADOW** (CERO órdenes) = S5 GapFill, S6 SWP-short (in-cycle) + OB/OBNB (batch post-close) + GT diarias (pre-market). **C4 global**: 2 pérdidas consecutivas de un sistema → ese sistema apagado hasta mañana. **ELIMINADOS en v3.0** (no evaluar): ORB, Volume Absorption, filtro EMA, filtro VP, régimen TREND/RANGE, VP developing intradía, tick fetches.

**"Self-learning" = el análisis periódico de `/post-close` sobre las estrategias de `cycle_prompt.md`** — no es un módulo, agente ni proceso aparte: es el mismo skill de post-cierre leyendo lo que el loop ya produjo (`trades`, `analysis_log`) una vez al día. `/pre-market` siembra `session_state` para el loop, el loop (`cycle_prompt.md`) ejecuta las estrategias todo el día, y `/post-close` analiza esa ejecución y retroalimenta dos cosas: (a) niveles de mañana en `volume_profiles` → los consume el `/pre-market` siguiente; (b) score/ranking por estrategia → el loop lo usa (STEP 6) para priorizar cuando varias señales compiten por un slot. Nunca reescribe `cycle_prompt.md` ni promueve un shadow a LIVE por su cuenta — eso es siempre decisión del usuario.

**Aprendizaje continuo (Fase 3, aplicado 2026-06-17 — capa de datos LIVE):** cada `/post-close` clasifica la sesión en `market_conditions` (liquidez = rvol30 ≷ 0.85, volatilidad = rango vs mediana, régimen = xvwap60) y recalcula el ranking (`refresh_strategy_performance()` → vista `v_strategy_ranking`): por `strategy_id` canónico, métricas n / WR (Wilson LB) / PF / expectancy-LB / drawdown → **Score** (0.45 calidad + 0.25 exp_lb + 0.30 robustez − drawdown) + **tier** (n<20 `insufficient_data` / <50 `provisional` / ≥50 `established`). Sólo informa y prioriza — NO crea reglas ni promueve a real (decisión del usuario). Taxonomía en `strategy_registry`; `trades.strategy_id` se auto-asigna por trigger. El dashboard expone ranking + condiciones (sección "Aprendizaje continuo"). Detalle: `strategies/research/learning_system_design.md`.

**Fase 4.1+4.2 (multi-posición + S1 RSI2 + S4 SWP LIVE) — ADOPTADA 2026-07-03 (v3.1.0):** porteada FRESH sobre v3.0.6 (la rama vieja `feat/fase4.1-rsi2-live` quedó obsoleta — se basaba en v3.0.3 y perdería el batching/cycle_log). Cambios: `state.positions[]` (lista), varias posiciones long concurrentes (máx 4, cap 70% como suma, prioridad por score), exclusión long/short, sizing 8%. En validación 5 sesiones paper. Diseño: `strategies/research/fase4_promotion_design.md`.

Claves de ejecución: una sola fuente de datos (1-min IEX; las 5-min se derivan por resampleo — sin SIP ni su lag de 15min), indicadores incrementales persistidos en `session_state`, exits SIEMPRE broker-side vía OCO (4 params obligatorios; `order_class="bracket"` PROHIBIDO), safety-net de posición desprotegida como primera acción de cada ciclo, wakeup alineado al próximo múltiplo de 5 min ET (~290-310s; 60s tras placear un limit o con precio cerca de TP/SL). Timing crítico: las señales RSI2 pierden el edge si la orden llega >1 min tarde del sello (playbook §7b).

Arranque diario desde sesión local: `/load-memory` → `/pre-market` → lanzar el primer ciclo con `@strategies/cycle_prompt.md`. **El agente programa sus propios wakeups llamando ScheduleWakeup en cada ciclo (STEP 9) — el usuario NO usa `/loop` ni re-invoca; un turno que termina sin ScheduleWakeup mata el loop** (excepciones: STEP 10 completado, mercado cerrado). **Modelo: Sonnet 4.6 para TODO** (pre-market, loop, post-close, research — decisión usuario 2026-06-11: Haiku no puede ejecutar `/pre-market` y sus ciclos de 2-3.5 min rompían la latencia <30s del playbook §7b). **Todas las escrituras del agente (trades, analysis_log, heartbeat, session_memory) van por SQL directo vía Supabase MCP** — los endpoints HTTP `/api/db/*` no se usan desde local (AGENT_SECRET solo existe en Vercel). Direct `mcp__alpaca__*` tool calls are blocked in cloud/remote environments; Alpaca data is available in Vercel via the `alpaca_state` sync table.

## Dashboard (`dashboard/`)

Next.js 14 app deployed to Vercel. Server components fetch all data from Supabase in parallel and pass it to client components as props.

```bash
cd dashboard && npm run dev      # dev server (port 3000)
cd dashboard && npm run build    # production build
cd dashboard && npm run start    # run production build locally
cd dashboard && npx tsc --noEmit # type-check without building
```

**Data flow:** `app/page.tsx` (server) fetches all Supabase data → passes as props to `TradingPanel` (client root) → distributed to child components.

**Dashboard layout (rediseño 2026-07-03, orden por prioridad de lectura):**
1. Sesión de hoy → `LiveSessionPanel` (posición como ladder SL/entry/TP + precio, gates del día, chip Golden Ticket, pulso del loop desde `state.cycle_log` v3.0.6, trades de la sesión)
2. Cuenta → `AccountSummary` (portfolio, hit ratio, P&L por sistema, posiciones live)
3. Performance → `PerformanceCard` (equity por sesión, KPIs inception/MTD/maxDD/PF — deriva de `trades` reconciliada con broker, NO de `session_memory`)
4. Trades → `DataTabs` (tabla expandible con notas del agente, columna Salida TP/SL/TIME/MANUAL, filtro por estrategia, P&L, pestaña Horario por franja 30-min ET, analysis log)
5. Validación & aprendizaje → `ShadowPanel` (outcomes reales desde `v_shadow_accumulated`: WR, TP/SL/TIME, P&L sombra) + `StrategyRankingCard` + `MarketConditionsCard`
6. Market Intelligence → `MarketIntelligencePanel` (contexto, patrones, hipótesis — advisory)
7. Infraestructura → `AgentGrid` + `ChampionCard` + `MarketCalendarCard`

**Key files:**
- `app/page.tsx` — server component; parallel-fetches trades, analysis_log, agent_status, champion_strategy, alpaca_state filtered by date range (`from`/`to` search params)
- `app/actions.ts` — reserved for server actions (currently empty)
- `app/api/account/route.ts` — proxies Alpaca `/v2/account` + `/v2/positions`; used by `AccountSummary`'s PortfolioCard
- `app/api/db/*.ts` — only `sync-alpaca` and `reconcile-trades` remain (the two that need Alpaca keys from Vercel); both require `?secret=AGENT_SECRET`. The agent write endpoints (heartbeat/log/trade/trade-exit/read/memory) were removed 2026-06-11 — the agent writes via direct Supabase SQL (MCP)
- `app/api/cron/sync/route.ts` — sync endpoint called by external cron (cron-job.org) every minute; requires `Authorization: Bearer CRON_SECRET`
- `app/api/ping/route.ts` — health check
- `lib/supabase.ts` — `createSupabase()` factory + all TypeScript types
- `lib/alpaca-sync.ts` — `syncAlpacaState()` fetches Alpaca account + positions, upserts to `alpaca_state`
- `lib/auth.ts` — `checkSecret()` validates `AGENT_SECRET` for all `/api/db/` routes

**Components:**

| Component | Role |
|---|---|
| `TradingPanel.tsx` | Root client component; owns trade-event toast notifications; Supabase realtime subscription; section ordering |
| `LiveSessionPanel.tsx` | Today's session: position ladder (SL/entry/TP + live price + R), daily gates, Golden Ticket chip (`state.gt`), loop pulse from `state.cycle_log` (cadence bars + last-cycle age), session trades strip |
| `AccountSummary.tsx` | Reads live Alpaca data from `alpaca_state` table; equity, cash, buying power, day P&L, P&L by system |
| `PerformanceCard.tsx` | Equity curve per session + KPIs (inception/MTD/maxDD/PF); derived from reconciled `trades` |
| `DataTabs.tsx` | Tabbed trades & analysis: expandable rows with agent notes, exit-type column, strategy filter + summary chips, hourly P&L tab (30-min ET buckets), CSV export |
| `ShadowPanel.tsx` | Shadow strategies from `strategy_registry` (status=shadow) + real outcomes from `v_shadow_accumulated` (WR, TP/SL/TIME bar, shadow P&L $/sh); `ID_TO_SYS` maps strategy_id → sys code (incl. GTR2D/GT3D) |
| `StrategyRankingCard.tsx` | `v_strategy_ranking` — score/tier per canonical strategy |
| `MarketConditionsCard.tsx` | `market_conditions` per session (liquidez/volatilidad/régimen) |
| `MarketIntelligencePanel.tsx` | Fase 3.1: context badges, patterns, hypotheses, emerging labels (advisory) |
| `MarketStatus.tsx` | ET clock + market open/closed indicator; pings `/api/ping` every 30s for latency |
| `ChampionCard.tsx` | Displays active strategy config from `champion_strategy` table |
| `AgentGrid.tsx` | Lists agents from `agent_status`; renders status pill (running/idle/error/disconnected) + optional progress bar from `metadata.progress` |
| `MarketCalendarCard.tsx` | NYSE calendar + early-close indicator; sidebar widget |

**Env vars required:**

| Variable | Used by |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase client (all data fetching) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase client (all data fetching) |
| `ALPACA_API_KEY` | `lib/alpaca-sync.ts` (Alpaca account/positions sync) |
| `ALPACA_SECRET_KEY` | `lib/alpaca-sync.ts` (Alpaca account/positions sync) |
| `AGENT_SECRET` | All `/api/db/*` routes (agent authentication) |
| `CRON_SECRET` | `/api/cron/sync` route (Vercel cron authentication) |
| `SUPABASE_SERVICE_ROLE_KEY` | `createSupabaseAdmin()` in all `/api/db/*` write routes |

## Alpaca MCP

Configured in `.mcp.json` (gitignored — contains Alpaca paper keys). Use `mcp__alpaca__*` tools for all market data and order execution. Must run from local machine — Alpaca endpoints are blocked in cloud/web environments.

## Supabase Schema

Defined in `supabase/schema.sql`. Tables: `trades`, `analysis_log`, `agent_status`, `champion_strategy`, `session_memory`, `alpaca_state`, `session_state`, `volume_profiles`, `situational_analysis`, y (Fase 3) `strategy_registry`, `market_conditions`, `strategy_performance` + vista `v_strategy_ranking`. All have RLS enabled with `anon` SELECT policies; writes go through `service_role` in `/api/db/*` routes or direct service_role SQL. QQQ-only forzado por constraint `NOT VALID` en `trades`/`analysis_log`/`volume_profiles`/`market_conditions` (históricos no-QQQ grandfathered).

Full table reference:

| Table | Purpose | Key details |
|---|---|---|
| `trades` | Paper trade ledger | `exit_type` ∈ {TP, SL, TIME, MANUAL}; `status` ∈ {pending, filled, cancelled, rejected}; quantity column is `quantity` (not `qty`); `total_value` is generated |
| `analysis_log` | Signals + indicator readings | `indicators` is JSONB; `signal` ∈ {bullish, bearish, neutral, watching} |
| `agent_status` | Agent heartbeats | `status` ∈ {running, idle, error}; `metadata` is JSONB |
| `champion_strategy` | Active strategy config | Single row keyed `"current"`; full config stored as JSONB in `config` column |
| `alpaca_state` | Live Alpaca account snapshot | Single row keyed `"current"`; synced by `/api/db/sync-alpaca` (manual) and `/api/cron/sync` (external cron-job.org every minute) |
| `session_memory` | Post-close analysis storage | `session_date` (not `date`); session learnings written after each trading day |
| `session_state` | Intraday loop state | Per-date row; state JSONB v3.0: VWAP num/den, EMAs, RSI14, ATR1m, buffer 5-min (closes/RSI2/ATR5m), gates diarios, c4 counters, fvg fills, position |
| `volume_profiles` | Daily VP snapshots | Per-date×symbol row; VPOC/VAH/VAL + day_high/low + session_close + bin_size. Written by post-close. |
| `situational_analysis` | D-1 → D bias snapshots | Per-date×symbol×timestamp row; written by `/situational` skill (informational only — does not affect loop) |
| `strategy_registry` | Catálogo canónico de estrategias (Fase 3A) | `strategy_id` PK (versiones granulares); `status` ∈ {live, shadow, archived, research}; `aliases[]` (variantes de formato); trigger auto-mapea `trades.strategy` → `trades.strategy_id` |
| `market_conditions` | Clasificación por sesión (Fase 3B) | Per-date; liquidez/volatilidad/régimen/cuadrante desde gates. Escrita por post-close (`upsert_market_condition`) |
| `strategy_performance` | Snapshots de ranking (Fase 3C) | Per (as_of, strategy_id, scope, time_window); n/WR/PF/exp_lb/score/tier. Recalculada por post-close (`refresh_strategy_performance`); vista pública `v_strategy_ranking` |

TypeScript types for all tables live in `lib/supabase.ts` (`Trade`, `AnalysisEntry`, `AgentStatus`, `ChampionConfig`, `AlpacaState`, `AlpacaPosition`).

## User Skills (manual `/commands`)

Skills live in `~/.claude/commands/` (local git-only repo, no remote). Invoke with `/<name>`:

| Skill | Purpose | Affects loop? |
|---|---|---|
| `/load-memory` | Carga memoria: default = modo trading lean (7 reglas); `full` = research | No — contexto |
| `/pre-market` | 9:30–9:55 ET: seeds incrementales + niveles ayer + vol30_baseline + gates conocibles → `session_state`; paso 4b (desde 07-03): señales Golden Ticket GTR2D/GT3D desde closes diarios | Yes — seeds state |
| `/post-close` | ≥16:00 ET: niveles mañana (`volume_profiles`) + resolución shadows (7 claves canónicas, incl. GT o2c) + **aprendizaje** (condición + ranking) + **Market Intelligence + situacional v2 automático** (paso 4d) + snapshots backtest viernes (4e) + `session_memory` | Yes — gates de mañana + ranking |
| ~~`/situational`~~ | **ELIMINADO 07-06** — integrado a /post-close 4d desde 07-02 (`situational_snapshot()` automático + predicción D+1 evaluada por el engine). El análisis ad-hoc se pide directo si hace falta | — |

## Documentation Index (every `.md` in the repo)

Reference index only — each doc's full content lives in its own file; don't duplicate it here. Grouped by folder, roughly current → historical within each group.

### `docs/` — active planning & audits

- `docs/backlog.md` — Backlog maestro por épicas (A-H), **fuente de verdad del programa de mejora**; estado 07-26: E.1 SMC cerrado (OB/OBNB rechazadas), H Golden Ticket con 6 shadows activos, D.2 (S1/S4) adoptada a LIVE 07-03.
- `docs/execution_plan.md` — Runbook secuencial complementario al backlog; cola accionable-sin-gate vacía tras 07-02, resto espera evidencia/re-medición/acción usuario (Vercel).
- `docs/gt_batch1_2026-07-03.md` — Golden Ticket lote 1 (GT-0/1/2): 51 hipótesis diarias → gt_rsi2d y gt_3down sobreviven OOS (PF 2.67/1.53); propuestos como shadow.
- `docs/gt_batch2_2026-07-03.md` — GT lotes 2/2b/2c/1b/1c (121 hipótesis): intradía naive anti-hallazgo; gt_washout, gt_closelow y ob_nobos_v1 activados como shadow.
- `docs/audit_cycles_2026-07-01.md` — Diagnóstico B.1 de latencia de ciclos (65 ciclos): outliers por multi-trabajo, no por acumulación de contexto; O1+O2 aprobados y aplicados en v3.0.6.
- `docs/audit_integrity_2026-07-01.md` — Auditoría A.3 de integridad cruzada dashboard/Supabase/engine/memorias: SINCRONIZADO, match exacto trades vs session_memory, drift equity despreciable ($1.14).
- `docs/audit_shadow_2026-07-01.md` — Auditoría C.1 de todas las estrategias shadow (S1/S4/S5/S6/OB): S6 SWPS mejor potencial, ninguna promovida ese día; fixes de claves canónicas aplicados mismo día.
- `docs/audit_smc_structure_2026-07-02.md` — Backtest E.1 de BOS/CHoCH: sin edge standalone (PF ≤1.13); confluencia OB×carácter tampoco rescata (PF ≤1.21) — stream SMC cerrado, solo OB shadow en curso.
- `docs/audit_supabase_2026-07-01.md` — Auditoría A.1 de esquema/seguridad/rendimiento Supabase: hallazgos RLS/security-definer/search_path; migración P0+P1 aplicada mismo día, advisors a 0.

### `docs/specs/` — design specs per épica

- `docs/specs/B1_cycle_optimization.md` — Spec épica B.1: diagnóstico read-only de causas de ciclos >5min, prerrequisito del gate Fase 4.1; sin cambios al loop en esa fase.
- `docs/specs/C1_shadow_audit.md` — Spec épica C.1: auditoría read-only de sistemas shadow con clasificación por potencial, sin promociones (gate D.2 aparte).
- `docs/specs/C2_C3_C4_knowledge_integration.md` — Spec C.2+C.3+C.4: integra `/situational` (auto en post-close v2), snapshots semanales (viernes) y vista única `v_shadow_accumulated`; implementada.
- `docs/specs/E1_smc_bos_choch.md` — Spec de investigación E.1: define BOS/CHoCH determinista y killzone-como-dato para backtest offline; resultado en `audit_smc_structure` (sin edge).
- `docs/specs/R1_reflexion_sentiment.md` — Spec R1: sentimiento determinista como contexto (no señal) + reflexión estructurada post-close con taxonomía fija, máx 1 lesson/día verificable.
- `docs/specs/golden_ticket_research.md` — Spec fundacional Épica H (Golden Ticket): ingeniería inversa de principios Renaissance/Medallion, arquitectura GT-0 a GT-5; research completo, implementación en lotes posteriores (`gt_batch*`).

### `strategies/` — the live spec

- `strategies/cycle_prompt.md` — **Spec operacional actual**, Pulse v3.1.5 (2026-07-20): única fuente de verdad del loop en vivo; 4 sistemas LIVE + 2 shadow, multi-posición.
- `strategies/shadow_prompt.md` — Agente shadow read-only (A4) v1: calcula señales S1/S4/S5/S6 para validación; nunca coloca órdenes, solo escribe en `analysis_log`.

### `strategies/history/` — superseded specs & changelog

- `strategies/history/CHANGELOG.md` — Historial de versiones de `cycle_prompt.md` (v3.0 → v3.1.5), no operacional; sacado del prompt en vivo en v3.1.1 para ahorrar tokens.
- `strategies/history/cycle_prompt_v3.0.6_2026-07-01.md` — Spec completa superseded, v3.0.6 (2026-07-01); batching I/O + cycle_log + shadow diferido, S1/S4/S5 aún shadow pre-promoción.
- `strategies/history/cycle_prompt_v2.9.2_2026-06-10.md` — Spec completa superseded, última pre-v3.0; era multi-símbolo con filtros VP/EMA/régimen, ORB, Volume Absorption — todo eliminado en v3.0.
- `strategies/history/pulse_v2.md` — Spec superseded, Pulse v2.8 (2026-05-28); detección de régimen TREND/RANGE, filtro duro de Volume Profile, ORB/Absorption — arquitectura reemplazada por v3.0.
- `strategies/history/pulse_v2_session_archive.md` — Log histórico de sesiones (pre-2026-06-04, universo multi-símbolo QQQ/TSLA/RIVN) que informó las revisiones v2.0→v2.8; solo archivo.

### `strategies/research/` — backtests & design docs

- `strategies/research/playbook_2026_06_10.md` — Playbook standing de 32 sesiones: portfolio de 5 sistemas (69.1% hit, PF 1.90, +$74.82/sh) con configs exactas, gates y anti-hallazgos; base de v3.0, re-correr semanalmente.
- `strategies/research/backtest_2026_06_10.md` — Backtest multi-sistema (8 sesiones): FVG f2 risk-band + RSI2-dip "C5" promovidos a validación shadow; invalidó el filtro FVG slope-C1; sembró los sistemas de v3.0.
- `strategies/research/backtest_short_2026_06_16.md` — Backtest espejo del lado short (12 sesiones): simetría short naïve rechazada (PF 0.78); solo SWP-short simétrico sobrevive (76.9%, PF 2.66) — aislado como shadow (S6).
- `strategies/research/fase4_promotion_design.md` — Diseño (2026-06-17) para promover shadows S1/S4/S5/S6 a órdenes reales con tracking multi-posición; adoptado luego como v3.1.0.
- `strategies/research/learning_system_design.md` — Diseño (2026-06-17) del esquema de aprendizaje continuo (`strategy_registry`, `market_conditions`, `strategy_performance`, fórmula de ranking); implementado como la capa "Fase 3" de self-learning.
- `strategies/research/multiagent_architecture.md` — Diseño (2026-06-18) de split en 5 agentes para bajar latencia / habilitar shadow SMC; tradeoffs de coste de tokens analizados; NO implementado — superseded por batching en un solo agente.
- `strategies/research/smc_study.md` — Estudio de conceptos SMC/ICT; el backtest de Order Block NO mostró edge (PF 0.81-1.07, anti-hallazgo); pivotó a validación shadow-only vía `/post-close`, stream ahora cerrado.
- `strategies/research/HORIZON_LAB.md` — Tool offline NL→backtest (`horizon_lab.py`); puntúa hipótesis DEPLOY/PAPER/KILLED contra la config del playbook; acelerador standing, no toca el loop en vivo.

### `.claude/memory/` — persistent project memory (repo-local, distinct from the global auto-memory system)

⚠️ Nota: `.claude/memory/MEMORY.md` referencia "Pulse v2.8 + FVG v1" como estrategia activa — está desactualizado frente al spec real (`strategies/cycle_prompt.md` v3.1.5). No tratar ese dato como vigente.

- `.claude/memory/MEMORY.md` — Índice raíz de esta memoria local; enlaza todos los archivos de abajo por categoría (nota de versión desactualizada, ver ⚠️ arriba).
- `.claude/memory/user_inaki_profile.md` — Perfil de usuario: paper trader QQQ-only hispanohablante, conocimiento técnico avanzado (Volume Profile, ICT/FVG, order flow), pragmático con tradeoffs coste/precisión.
- `.claude/memory/feedback_decision_style.md` — Para decisiones no triviales usar `AskUserQuestion` con 2-4 opciones y una recomendada; si el cambio es claro/bajo riesgo, proponer y ejecutar sin preguntar.
- `.claude/memory/feedback_direct_cycles.md` — El loop corre como ciclos directos en la sesión CLI local (no subprocess); Alpaca/Supabase bloqueados en cloud/CCR; reiniciar CLI si el MCP se desconecta.
- `.claude/memory/feedback_eod_close_sgov.md` — Cierre escalonado por ganancia (+0.7% a las 15:00, +0.4% a las 15:30) y aparcar ~95% del cash en SGOV overnight; vender SGOV al inicio del pre-análisis siguiente.
- `.claude/memory/feedback_forced_close.md` — Cierre forzado obligatorio a las 15:55 ET (`exit_type='TIME'`); brackets DAY expiran a las 16:00, usar GTC solo si overnight está autorizado explícitamente.
- `.claude/memory/feedback_language.md` — Conversación siempre en español; el contenido de archivos (código, specs, SQL) respeta el idioma original de cada archivo destino.
- `.claude/memory/feedback_local_first.md` — Preferir soluciones locales sin instalar software o crear servicios remotos; ofrecer alternativas remote/CLI de terceros solo como opt-in secundario.
- `.claude/memory/feedback_loop_terse.md` — Durante el loop de trading, respuestas de una sola línea por ciclo; expandir solo ante señales, fills, errores o cambios de régimen.
- `.claude/memory/feedback_no_ema_filter.md` — Filtro EMA9/EMA21 eliminado como gate de entradas (2026-06-01); solo VWAP/VA/ORB/FVG deciden, tras bloquear una entrada ganadora.
- `.claude/memory/feedback_pending_observations.md` — Dos reglas candidatas sin formalizar (OBS-1 skip si entry >1×ATR tarde; OBS-2 TP2 por lower-high) pendientes de validar con ≥3 sesiones.
- `.claude/memory/feedback_session_schedule.md` — Horario legado de fases de sesión: pre-análisis 9:50, loop 10:00, passive 15:45, forced close 15:55, SGOV 15:56-15:59.
- `.claude/memory/feedback_stick_with_pulse.md` — No añadir setups de momentum/chase improvisados; cambios estructurales requieren ≥3 sesiones de evidencia (lección: setup improvisado perdió −$16.52).
- `.claude/memory/feedback_trade_consolidation.md` — 1 trade = 1 compra (no por venta); exit_price = promedio ponderado FIFO de ventas; no insertar en `trades` hasta que el lote cierre 100%.
- `.claude/memory/feedback_trading_philosophy.md` — El aprendizaje del comportamiento del mercado es lo permanente; las estrategias específicas son reemplazables y no se debe forzar actividad en días sin setups.
- `.claude/memory/project_dashboard.md` — Referencia del dashboard Next.js/Vercel: layout de 6 niveles, componentes clave, rutas API, sync Alpaca→Supabase vía cron-job.org cada minuto.
- `.claude/memory/project_pulse_overview.md` — Overview de Pulse v2.8: 4 setups (VWAP Pullback, Volume Absorption, ORB, FVG); FVG es explícitamente independiente (sizing propio, sin filtros del árbol principal) — histórico, ver ⚠️ arriba.
- `.claude/memory/project_situational_analysis.md` — Skill `/situational` (D-1→D) es puramente informativo, no afecta el loop ni `session_state`; persiste snapshots en tabla `situational_analysis`.
- `.claude/memory/project_universe_constraints.md` — Universo permanente QQQ-only, long-only, y lista de exclusión ética (defensa: BA/LMT/TXN/NOC/RTX/GD/HII; farma: MRNA/PFE).
- `.claude/memory/ref_skills_repo.md` — Los skills `pre-market.md`/`post-close.md` viven en `~/.claude/commands/` como repo git local-only sin remote (decisión explícita del usuario).
- `.claude/memory/ref_supabase.md` — Pointer al proyecto Supabase (`project_id` + tablas clave: trades, analysis_log, session_state, session_memory, volume_profiles, champion_strategy, alpaca_state).

## Ethical Constraints (permanent)

- NO defense sector: BA, LMT, TXN, NOC, RTX, GD, HII
- NO: MRNA, PFE
- **Universe: QQQ ONLY** — no exceptions. See memory `feedback-qqq-only-universe` for full reasoning.
