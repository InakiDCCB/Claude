# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A paper trading research system for studying market behavior and developing strategies. Execution and market data go through **Alpaca** (paper account, configured in `.mcp.json`). All trade records and analysis are stored in **Supabase**.

## Key Principle

Claude uses the `mcp__alpaca__*` MCP tools directly for market data and order execution. No separate Python agent scripts — Claude IS the agent.

## Dashboard (`dashboard/`)

Next.js 14 app deployed to Vercel. Server components fetch all data from Supabase in parallel and pass it to client components as props.

```bash
cd dashboard && npm run dev      # dev server (port 3000)
cd dashboard && npm run build    # production build
cd dashboard && npm run start    # run production build locally
```

**Key files:**
- `app/page.tsx` — server component; parallel-fetches trades, analysis_log, agent_status, champion_strategy filtered by date range (`from`/`to` search params)
- `app/actions.ts` — `toggleAgentStatus()` server action; updates agent_status and revalidates page cache
- `app/api/account/route.ts` — proxies Alpaca `/v2/account` + `/v2/positions` with 30s revalidation
- `app/api/ping/route.ts` — health check
- `components/TradingPanel.tsx` — root client component; owns trade-event toast notifications
- `lib/supabase.ts` — `createSupabase()` factory + all TypeScript types

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

Defined in `supabase/schema.sql`. Five tables:

| Table | Purpose | Key details |
|---|---|---|
| `trades` | Paper trade ledger | `exit_type` ∈ {TP, SL, TIME, MANUAL}; `total_value` is a generated column |
| `market_snapshots` | OHLCV captures | `timeframe` ∈ {1m, 5m, 1h, 1d} |
| `analysis_log` | Signals + indicator readings | `indicators` is JSONB; `signal` ∈ {bullish, bearish, neutral, watching} |
| `agent_status` | Agent heartbeats | `status` ∈ {running, idle, error}; `metadata` is JSONB |
| `champion_strategy` | Active strategy config | Single row keyed `"current"`; full config stored as JSONB in `config` column |

TypeScript types for all tables live in `lib/supabase.ts` (`Trade`, `AnalysisEntry`, `MarketSnapshot`, `AgentStatus`, `ChampionConfig`).

## Backtesting (`backtest_v2.py`)

Python script at the repo root for offline strategy analysis.

```bash
pip install -r requirements.txt
python backtest_v2.py
```

## Ethical Constraints (permanent)

- NO defense sector: BA, LMT, TXN, NOC, RTX, GD, HII
- NO: MRNA, PFE
- Preferred universe: QQQ, TSLA, OKLO, RIVN, COST, HUM, CVS
