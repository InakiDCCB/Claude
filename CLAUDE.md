# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A paper trading research system for studying market behavior and developing strategies. Execution and market data go through **Alpaca** (paper account, configured in `.mcp.json`). All trade records and analysis are stored in **Supabase**. Strategy specs live in `strategies/` (current: `pulse_v2.md`).

## Key Principle

Claude uses the `mcp__alpaca__*` MCP tools directly for market data and order execution. No separate Python agent scripts — Claude IS the agent.

## Trading Loop (Pulse v2.2)

Session phases:

| Phase | ET window | Action |
|---|---|---|
| Chaotic open | 9:30–10:00 | No trades. Collect regime data. |
| Regime detection | 10:00 | Classify TREND / RANGE |
| Active trading | 10:00–15:30 | Entries + bracket management |
| Passive observation | 15:30–16:00 | No new entries. Manage open positions. Log observations. |
| Post-close analysis | ≥16:00 | See strategies/pulse_v2.md for full 5-step protocol. |

Each ~5-min cycle during active trading:

1. `get_clock` → verify market open and current phase
2. `get_all_positions` → manage open positions; **update `status='pending'→'filled'` before applying exit updates** (prevents orphaned pending records)
3. `get_stock_bars` (1-min IEX) → real-time signals
4. [If 10:00 ET and first cycle] → regime detection (TREND vs RANGE)
5. Compute VWAP + EMAs (5, 9, 21, 34, 55) from 5-min SIP bars; SMA (100, 200) from 1-hour bars
6. Evaluate setups per active mode + EMA bias: **10:00–11:15 ET use EMA 9** (EMA 21 not yet valid); **≥11:15 ET use EMA 21 as hard filter** (reject long if price < EMA 21)
7. On signal → `place_stock_order` (bracket order; **round TP/SL to 2 decimal places** — Alpaca rejects sub-penny prices). RSI min is **45** (not 40).
8. Log cycle to `analysis_log` (include EMAs in `indicators` JSONB) + heartbeat to `agent_status`
9. If any asset within ±0.30% of VWAP but no full setup → schedule next wakeup at **90s** (alert zone)

Passive observation cycle (15:30–16:00): steps 1–2 only; no new entries; forced close of any open position at 15:55 ET (`exit_type='TIME'`).

Loop starts **manually at 10:00 ET** from a local interactive session (Alpaca MCP is blocked in cloud/remote environments).

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
5. Strategies grid (champion + 3 incoming slots) → `ChampionCard` + `IncomingSlot`
6. Trades · P&L · Analysis Log → `DataTabs`

**Key files:**
- `app/page.tsx` — server component; parallel-fetches trades, analysis_log, agent_status, champion_strategy filtered by date range (`from`/`to` search params)
- `app/actions.ts` — `toggleAgentStatus()` server action; updates agent_status and revalidates page cache
- `app/api/account/route.ts` — proxies Alpaca `/v2/account` + `/v2/positions` with 30s revalidation
- `app/api/ping/route.ts` — health check
- `lib/supabase.ts` — `createSupabase()` factory + all TypeScript types

**Components:**

| Component | Role |
|---|---|
| `TradingPanel.tsx` | Root client component; owns trade-event toast notifications; Supabase realtime subscription |
| `AccountSummary.tsx` | Fetches `/api/account`; displays equity, long/short value, position count as stat cards |
| `DataTabs.tsx` | Tabbed interface for trades & analysis; line charts (Recharts); CSV export |
| `DateFilter.tsx` | Updates URL `from`/`to` params via `useRouter.push()` to trigger server re-fetch |
| `MarketStatus.tsx` | ET clock + market open/closed indicator; pings `/api/ping` every 30s for latency |
| `ChampionCard.tsx` | Displays active strategy config from `champion_strategy` table; also exports `IncomingSlot` |
| `AgentGrid.tsx` | Lists agents from `agent_status`; calls `toggleAgentStatus()` server action |

**Env vars required:**

| Variable | Used by |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase client (all data fetching) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase client (all data fetching) |
| `ALPACA_API_KEY` | `/api/account` route (server-side proxy) |
| `ALPACA_SECRET_KEY` | `/api/account` route (server-side proxy) |

## Alpaca MCP

Configured in `.mcp.json` (use `.mcp.json.example` as a template). Use `mcp__alpaca__*` tools for all market data and order execution. Must run from local machine — Alpaca endpoints are blocked in cloud/web environments.

## Supabase Schema

Defined in `supabase/schema.sql`. That file defines four tables: `trades`, `market_snapshots`, `analysis_log`, `agent_status`.

**Note:** The `champion_strategy` table is used by the dashboard (`ChampionCard`, `page.tsx`) but is **not in `schema.sql`**. It must be created manually:

```sql
create table if not exists champion_strategy (
  key        text primary key,
  updated_at timestamptz not null default now(),
  config     jsonb not null
);
```

Full table reference:

| Table | Purpose | Key details |
|---|---|---|
| `trades` | Paper trade ledger | `exit_type` ∈ {TP, SL, TIME, MANUAL}; `total_value` is a generated column |
| `market_snapshots` | OHLCV captures | `timeframe` ∈ {1m, 5m, 1h, 1d} |
| `analysis_log` | Signals + indicator readings | `indicators` is JSONB; `signal` ∈ {bullish, bearish, neutral, watching} |
| `agent_status` | Agent heartbeats | `status` ∈ {running, idle, error}; `metadata` is JSONB |
| `champion_strategy` | Active strategy config | Single row keyed `"current"`; full config stored as JSONB in `config` column |

TypeScript types for all tables live in `lib/supabase.ts` (`Trade`, `AnalysisEntry`, `MarketSnapshot`, `AgentStatus`, `ChampionConfig`).

## Backtesting (`backtest_v2.py`)

Python script for offline analysis. **Currently imports from a `trading/` module that was retired** — the script will not run as-is. It previously relied on Alpaca MCP tool-result JSON files saved as `.txt` files from prior sessions (hardcoded absolute paths). Update `TSLA_FILES` / `QQQ_FILES` paths and restore the `trading/` module imports before running.

## Ethical Constraints (permanent)

- NO defense sector: BA, LMT, TXN, NOC, RTX, GD, HII
- NO: MRNA, PFE
- Preferred universe: QQQ, TSLA, OKLO, RIVN, COST, HUM, CVS
