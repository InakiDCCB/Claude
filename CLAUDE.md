# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A paper trading research system for studying market behavior and developing strategies. Execution and market data go through **Alpaca** (paper account, configured in `.mcp.json`). All trade records and analysis are stored in **Supabase**. Strategy specs live in `strategies/` (current: `pulse_v2.md`).

## Key Principle

Claude uses the `mcp__alpaca__*` MCP tools directly for market data and order execution. No separate Python agent scripts — Claude IS the agent.

## Trading Loop (Pulse v2.4)

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
6. Evaluate setups per active mode + EMA bias: **10:00–11:15 ET use EMA 9** (EMA 21 not yet valid); **≥11:15 ET use EMA 21 as hard filter** (reject long if price < EMA 21). **Slippage buffer (v2.3):** if price is within ±$0.25 of the hard filter level, require price > level + $0.20 before placing order.
7. **TREND DOWN regime (v2.3):** do not enter long until price is ≥1.5% above session low AND 3 consecutive 5-min bars have closed above EMA 21. EMA 21 acts as resistance in TREND DOWN until reversal is confirmed.
8. On signal → `place_stock_order` as **market order only** (no bracket at this step — SL/TP set after fill per step 9). **Round all prices to 2 decimal places** — Alpaca rejects sub-penny prices. RSI min is **45** (not 40). **Sizing (v2.3 — mandatory):** `shares = floor(equity × 0.10 / entry_price)` — calculate before every order, no exceptions. Skip if shares < 2.
9. **SL post-fill (v2.4 — mandatory):** place market order first (no bracket), confirm fill price with `get_order_by_id`, then calculate `SL = fill_price − 2×ATR(14, 1-min)`. Place OCO/bracket only after fill is confirmed.
10. **TP Dinámico (v2.4 — P5):** identify nearest structural resistance on 5-min bars before entry. `TP1 = entry + 2×ATR` (close 50%, move SL to break-even). `TP2 = structural resistance or entry + 4×ATR` (close remaining 50%).
11. **Volume Absorption entry (v2.3):** valid without classic pullback when: bar volume >3× avg of prior 5 bars, closes within ±0.15% of VWAP or support, does NOT close at new session low, and EMA 21 is below price. Enter at next bar open.
12. **Post-stop-hunt re-entry (v2.4 — P6):** if SL was swept by <$0.25 AND price reversed within ≤2 bars AND volume ≥ avg AND within 3 bars of sweep → re-entry valid at open of next confirmation bar. Full SL/TP rules apply.
13. Log cycle to `analysis_log` (include EMAs in `indicators` JSONB) + heartbeat to `agent_status`
14. If any asset within ±0.30% of VWAP but no full setup → schedule next wakeup at **90s** (alert zone)

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
