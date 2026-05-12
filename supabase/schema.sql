-- ============================================================
-- Trading System Ledger
-- Central record-keeping for paper trades and market analysis
-- ============================================================

-- TRADES
-- Records every paper trade executed via Alpaca
create table if not exists trades (
  id            uuid primary key default gen_random_uuid(),
  created_at    timestamptz not null default now(),
  filled_at     timestamptz,
  asset         text not null,              -- e.g. 'TQQQ', 'QQQ'
  side          text not null check (side in ('buy','sell')),
  quantity      numeric not null,
  price         numeric not null,           -- entry fill price
  exit_price    numeric,                    -- exit fill price
  exit_type     text check (exit_type in ('TP','SL','TIME','MANUAL')),
  total_value   numeric generated always as (quantity * price) stored,
  order_id      text,                       -- Alpaca parent order ID
  status        text not null default 'pending'
                  check (status in ('pending','filled','cancelled','rejected')),
  strategy      text,                       -- strategy name that triggered the trade
  pnl           numeric,                    -- realized P&L (filled on position close)
  notes         text
);

-- AGENT_STATUS
-- Heartbeat table for monitoring running agents from the dashboard
create table if not exists agent_status (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  status      text not null default 'idle' check (status in ('running','idle','error')),
  description text,
  updated_at  timestamptz not null default now(),
  metadata    jsonb
);

-- MARKET_SNAPSHOTS
-- Periodic OHLCV captures for each watched asset
create table if not exists market_snapshots (
  id            uuid primary key default gen_random_uuid(),
  captured_at   timestamptz not null default now(),
  asset         text not null,
  timeframe     text not null,              -- '1m','5m','1h','1d'
  open          numeric,
  high          numeric,
  low           numeric,
  close         numeric not null,
  volume        numeric,
  vwap          numeric,
  notes         text
);

-- ANALYSIS_LOG
-- Dated observations, signals, and indicator readings
create table if not exists analysis_log (
  id            uuid primary key default gen_random_uuid(),
  created_at    timestamptz not null default now(),
  asset         text not null,
  timeframe     text,                       -- timeframe analyzed
  signal        text check (signal in ('bullish','bearish','neutral','watching')),
  confidence    smallint check (confidence between 0 and 100),
  indicators    jsonb,                      -- { rsi: 58, macd: 'crossover', sma20: 412 ... }
  thesis        text,                       -- trade thesis narrative
  outcome       text,                       -- filled in after the fact
  tags          text[]
);

-- Indexes for common query patterns
create index if not exists trades_asset_idx       on trades (asset);
create index if not exists trades_created_idx     on trades (created_at desc);
create index if not exists snapshots_asset_idx    on market_snapshots (asset, captured_at desc);
create index if not exists analysis_asset_idx     on analysis_log (asset, created_at desc);
