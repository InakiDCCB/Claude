# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A paper trading research system for studying market behavior and developing strategies. Execution and market data go through **Alpaca** (paper account, configured in `.mcp.json`). All trade records and analysis are stored in **Supabase**. Strategy specs live in `strategies/` (current: `pulse_v2.md`).

## Key Principle

Claude uses the `mcp__alpaca__*` MCP tools directly for market data and order execution. No separate Python agent scripts — Claude IS the agent.

## Trading Loop (Pulse v3.0 — 2026-06-11)

**`strategies/cycle_prompt.md` es la ÚNICA fuente de verdad operacional** (sistemas, gates, fórmulas, wakeups). Este resumen es orientativo; si difieren, manda el cycle_prompt. v3.0 sale del playbook validado en 32 sesiones (`strategies/research/playbook_2026_06_10.md`). Versión anterior archivada en `strategies/history/cycle_prompt_v2.9.2_2026-06-10.md`.

Session phases:

| Phase          | ET window   | Action                                                       |
| -------------- | ----------- | ------------------------------------------------------------ |
| Pre-market     | 9:30–9:55   | `/pre-market`: seeds incrementales + niveles ayer + gates conocibles |
| Gates 10:00    | 10:00       | rvol30, gap_pct, open_loc → fija fvg_on / rsi2_on / gapf_on  |
| Gates 10:30    | 10:30       | xvwap60 (cruces close-VWAP 1ª hora) → fija vwappb_on         |
| Active trading | 10:00–15:30 | Ciclos ALINEADOS a velas 5-min (wake = sello + 10s)          |
| Passive        | 15:30–15:55 | Solo gestión de posición; sin entries nuevos                  |
| Close          | 15:55       | Cierre forzado total (exit_type=TIME)                         |
| Post-close     | ≥16:00      | `/post-close`: niveles de mañana + resolución de shadows      |

Sistemas v3.0: **LIVE** = S2 FVG (limit al midpoint on-formation; max 1 fill/día; gate rvol30 ≥ 0.85) y S3 VWAPPB (pullback a VWAP; solo días choppy con xvwap60 ≥ 6). **SHADOW** (computar y loggear señal con precios exactos, CERO órdenes; validación 5 sesiones) = S1 RSI2-dip, S4 Sweep&Reclaim, S5 GapFill. **C4 global**: 2 pérdidas consecutivas de un sistema → ese sistema apagado hasta mañana. **ELIMINADOS en v3.0** (no evaluar): ORB, Volume Absorption, filtro EMA, filtro VP, régimen TREND/RANGE, VP developing intradía, tick fetches.

Claves de ejecución: una sola fuente de datos (1-min IEX; las 5-min se derivan por resampleo — sin SIP ni su lag de 15min), indicadores incrementales persistidos en `session_state`, exits SIEMPRE broker-side vía OCO (4 params obligatorios; `order_class="bracket"` PROHIBIDO), safety-net de posición desprotegida como primera acción de cada ciclo, wakeup alineado al próximo múltiplo de 5 min ET (~290-310s; 60s tras placear un limit o con precio cerca de TP/SL). Timing crítico: las señales RSI2 pierden el edge si la orden llega >1 min tarde del sello (playbook §7b).

Loop manual desde sesión local: `/model haiku` → `/load-memory` → `/pre-market` → `/loop @strategies/cycle_prompt.md`. **Modelo: Haiku 4.5 (`claude-haiku-4-5`) para pre-market + loop** — cada wake (~300s) re-lee el contexto con cache expirado (TTL 5 min), Haiku cuesta 1/3 de Sonnet y el ciclo es ejecución mecánica de reglas escritas para ello. **Sonnet 4.6 para `/post-close` y research.** Direct `mcp__alpaca__*` tool calls are blocked in cloud/remote environments; Alpaca data is available in Vercel via the `alpaca_state` sync table.

## Dashboard (`dashboard/`)

Next.js 14 app deployed to Vercel. Server components fetch all data from Supabase in parallel and pass it to client components as props.

```bash
cd dashboard && npm run dev      # dev server (port 3000)
cd dashboard && npm run build    # production build
cd dashboard && npm run start    # run production build locally
cd dashboard && npx tsc --noEmit # type-check without building
```

**Data flow:** `app/page.tsx` (server) fetches all Supabase data → passes as props to `TradingPanel` (client root) → distributed to child components.

**Dashboard layout (6 levels):**
1–3. Portfolio · Metrics · Top Performers → `AccountSummary`
4. Agent status → `AgentGrid`
5. Strategies grid (champion) → `ChampionCard`
6. Trades · P&L · Analysis Log → `DataTabs`

**Key files:**
- `app/page.tsx` — server component; parallel-fetches trades, analysis_log, agent_status, champion_strategy, alpaca_state filtered by date range (`from`/`to` search params)
- `app/actions.ts` — reserved for server actions (currently empty)
- `app/api/account/route.ts` — proxies Alpaca `/v2/account` + `/v2/positions` (legacy; dashboard reads `alpaca_state` directly)
- `app/api/db/*.ts` — agent HTTP endpoints: `heartbeat`, `log`, `trade`, `trade-exit`, `read`, `memory`, `sync-alpaca`, `reconcile-trades`; all require `?secret=AGENT_SECRET`
- `app/api/cron/sync/route.ts` — sync endpoint called by external cron (cron-job.org) every minute; requires `Authorization: Bearer CRON_SECRET`
- `app/api/ping/route.ts` — health check
- `lib/supabase.ts` — `createSupabase()` factory + all TypeScript types
- `lib/alpaca-sync.ts` — `syncAlpacaState()` fetches Alpaca account + positions, upserts to `alpaca_state`
- `lib/auth.ts` — `checkSecret()` validates `AGENT_SECRET` for all `/api/db/` routes

**Components:**

| Component | Role |
|---|---|
| `TradingPanel.tsx` | Root client component; owns trade-event toast notifications; Supabase realtime subscription |
| `AccountSummary.tsx` | Reads live Alpaca data from `alpaca_state` table; displays equity, cash, buying power, day P&L as stat cards |
| `DataTabs.tsx` | Tabbed interface for trades & analysis; line charts (Recharts); CSV export |
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

Defined in `supabase/schema.sql`. Tables: `trades`, `analysis_log`, `agent_status`, `champion_strategy`, `session_memory`, `alpaca_state`, `session_state`, `volume_profiles`, `situational_analysis`. All have RLS enabled with `anon` SELECT policies; writes go through `service_role` in `/api/db/*` routes or direct service_role SQL.

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

TypeScript types for all tables live in `lib/supabase.ts` (`Trade`, `AnalysisEntry`, `AgentStatus`, `ChampionConfig`, `AlpacaState`, `AlpacaPosition`).

## User Skills (manual `/commands`)

Skills live in `~/.claude/commands/` (local git-only repo, no remote). Invoke with `/<name>`:

| Skill | Purpose | Affects loop? |
|---|---|---|
| `/load-memory` | Carga memoria: default = modo trading lean (7 reglas); `full` = research | No — contexto |
| `/pre-market` | 9:30–9:55 ET: seeds incrementales + niveles ayer + vol30_baseline + gates conocibles → `session_state` | Yes — seeds state |
| `/post-close` | ≥16:00 ET: snapshot niveles mañana (`volume_profiles`) + resolución shadow trades (validación 5 sesiones) + `session_memory` | Yes — produce los gates de mañana |
| `/situational` | D-1 → D multi-day bias analysis → writes `situational_analysis` | **No — informational only**, manual trigger any time |

## Ethical Constraints (permanent)

- NO defense sector: BA, LMT, TXN, NOC, RTX, GD, HII
- NO: MRNA, PFE
- **Universe: QQQ ONLY** — no exceptions. See memory `feedback-qqq-only-universe` for full reasoning.
