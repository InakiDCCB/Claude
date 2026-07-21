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

## Ethical Constraints (permanent)

- NO defense sector: BA, LMT, TXN, NOC, RTX, GD, HII
- NO: MRNA, PFE
- **Universe: QQQ ONLY** — no exceptions. See memory `feedback-qqq-only-universe` for full reasoning.
