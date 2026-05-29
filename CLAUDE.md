# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A paper trading research system for studying market behavior and developing strategies. Execution and market data go through **Alpaca** (paper account, configured in `.mcp.json`). All trade records and analysis are stored in **Supabase**. Strategy specs live in `strategies/` (current: `pulse_v2.md`).

## Key Principle

Claude uses the `mcp__alpaca__*` MCP tools directly for market data and order execution. No separate Python agent scripts — Claude IS the agent.

## Trading Loop (Pulse v2.8)

Session phases:

| Phase               | ET window   | Action                                                   |
| ------------------- | ----------- | -------------------------------------------------------- |
| Chaotic open        | 9:30–10:00  | No trades. Collect regime data.                          |
| Regime detection    | 10:00       | Classify TREND / RANGE                                   |
| Active trading      | 10:00–15:45 | Entries + bracket management                             |
| Passive observation | 15:45–16:00 | No new entries. Manage open positions. Log observations. |
| Close positions     | 15:55       | Close all open positions                                 |
| Post-close analysis | ≥16:00      | See strategies/pulse_v2.md for full 5-step protocol.     |

Each ~5-min cycle during active trading:

1. `get_clock` → verify market open and current phase
2. `get_all_positions` → manage open positions + apply pending exit updates
3. `get_stock_bars` (1-min IEX) → real-time signals
4. [If 10:00 ET and first cycle] → regime detection (TREND vs RANGE)
5. Compute VWAP + EMAs (5, 9, 21, 34, 55) from 5-min SIP bars; SMA (100, 200) from 1-hour bars. **(v2.8)** Also incremental-update Volume Profile per symbol: pull `get_stock_trades` (SIP) since `last_tick_UTC`, bin volume at `bin_size = max($0.01, yesterday_close × 0.0005)`, recompute developing VPOC/VAH/VAL via TPO 70% expansion. `yesterday_profile` and `naked_pocs` are seeded by pre-market and immutable during the day.
6. Evaluate setups per active mode + EMA bias: **10:00–11:15 ET use EMA 9** (EMA 21 not yet valid); **≥11:15 ET use EMA 21 as hard filter** (reject long if price < EMA 21). **Slippage buffer (v2.3):** if price is within ±$0.25 of the hard filter level, require price > level + $0.20 before placing order. **(v2.8) VP hard filter:** VWAP Pullback rejects if price not within yesterday VA OR developing VA; Volume Absorption rejects unless close is within ±0.10% of yesterday VPOC, developing VPOC, or a naked POC; ORB Breakout requires close above `max(ORB_HIGH, yesterday VAH)`. **FVG (`strategy='fvg_v1'`) is explicitly exempt from VP — ICT gap thesis is orthogonal to value areas.** If `yesterday_profile` is missing (cold start without pre-market), fail-open on VP for v2.7 setups and log a warning.
7. **TREND DOWN regime (v2.3):** do not enter long until price is ≥1.5% above session low AND 3 consecutive 5-min bars have closed above EMA 21. EMA 21 acts as resistance in TREND DOWN until reversal is confirmed.
8. On signal → `place_stock_order` as **market order only** (no bracket at this step — SL/TP set after fill per step 9). **Round all prices to 2 decimal places** — Alpaca rejects sub-penny prices. RSI min is **45** (not 40). **Sizing (v2.3 — mandatory):** `shares = floor(equity × 0.10 / entry_price)` — calculate before every order, no exceptions. Skip if shares < 2.
9. **SL post-fill (v2.4 — mandatory):** place market order first (no bracket), confirm fill price with `get_order_by_id`, then calculate `SL = fill_price − 2×ATR(14, 1-min)`. Place OCO/bracket only after fill is confirmed.
10. **TP Dinámico (v2.4 — P5):** identify nearest structural resistance on 5-min bars before entry. `TP1 = entry + 2×ATR` (close 50%, move SL to break-even). `TP2 = structural resistance or entry + 4×ATR` (close remaining 50%).
11. **Volume Absorption entry (v2.3):** valid without classic pullback when: bar volume >3× avg of prior 5 bars, closes within ±0.15% of VWAP or support, does NOT close at new session low, and EMA 21 is below price. Enter at next bar open.
12. **Post-stop-hunt re-entry (v2.4 — P6):** if SL was swept by <$0.25 AND price reversed within ≤2 bars AND volume ≥ avg AND within 3 bars of sweep → re-entry valid at open of next confirmation bar. Full SL/TP rules apply.
13. Log cycle to `analysis_log` (include EMAs in `indicators` JSONB) + heartbeat to `agent_status`
14. If any asset within ±0.30% of VWAP but no full setup → schedule next wakeup at **90s** (alert zone)

Passive observation cycle (15:30–16:00): steps 1–2 only; no new entries; forced close of any open position at 15:55 ET (`exit_type='TIME'`).

Loop starts **manually at 10:00 ET** from a local interactive Claude Code session. Direct `mcp__alpaca__*` tool calls are blocked in cloud/remote environments; Alpaca data is available in Vercel via the `alpaca_state` sync table. `strategies/cycle_prompt.md` is the source of truth for step-by-step cycle behavior. To reduce token consumption, start the session with `/model haiku`.

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
| `ChampionCard.tsx` | Displays active strategy config from `champion_strategy` table; also exports `IncomingSlot` |
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

Configured in `.mcp.json` (use `.mcp.json.example` as a template). Use `mcp__alpaca__*` tools for all market data and order execution. Must run from local machine — Alpaca endpoints are blocked in cloud/web environments.

## Supabase Schema

Defined in `supabase/schema.sql`. Tables: `trades`, `analysis_log`, `agent_status`, `champion_strategy`, `session_memory`, `alpaca_state`. All have RLS enabled with `anon` SELECT policies; writes go through `service_role` in `/api/db/*` routes.

Full table reference:

| Table | Purpose | Key details |
|---|---|---|
| `trades` | Paper trade ledger | `exit_type` ∈ {TP, SL, TIME, MANUAL}; `total_value` is a generated column |
| `analysis_log` | Signals + indicator readings | `indicators` is JSONB; `signal` ∈ {bullish, bearish, neutral, watching} |
| `agent_status` | Agent heartbeats | `status` ∈ {running, idle, error}; `metadata` is JSONB |
| `champion_strategy` | Active strategy config | Single row keyed `"current"`; full config stored as JSONB in `config` column |
| `alpaca_state` | Live Alpaca account snapshot | Single row keyed `"current"`; synced by `/api/db/sync-alpaca` (manual) and `/api/cron/sync` (external cron-job.org every minute) |
| `session_memory` | Post-close analysis storage | Session learnings written after each trading day |

TypeScript types for all tables live in `lib/supabase.ts` (`Trade`, `AnalysisEntry`, `AgentStatus`, `ChampionConfig`, `AlpacaState`, `AlpacaPosition`).

## Ethical Constraints (permanent)

- NO defense sector: BA, LMT, TXN, NOC, RTX, GD, HII
- NO: MRNA, PFE
- Universe: QQQ, TSLA, RIVN
