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
  asset         text not null,              -- QQQ only (trades_asset_qqq_check NOT VALID; históricos TSLA/RIVN/TQQQ grandfathered)
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
  name        text not null unique,
  status      text not null default 'idle'
                check (status in ('running','idle','error','disconnected')),
  description text,
  updated_at  timestamptz not null default now(),
  metadata    jsonb
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

-- CHAMPION_STRATEGY
-- Active strategy config displayed in the dashboard
create table if not exists champion_strategy (
  key        text primary key default 'current',
  config     jsonb not null,
  updated_at timestamptz not null default now()
);

-- Indexes for common query patterns
create index if not exists trades_asset_idx       on trades (asset);
create index if not exists trades_created_idx     on trades (created_at desc);
create index if not exists analysis_asset_idx     on analysis_log (asset, created_at desc);

-- SESSION_MEMORY
-- Persistent learnings written by the autonomous agent after each session
create table if not exists session_memory (
  id           uuid primary key default gen_random_uuid(),
  session_date date not null unique,  -- unique desde 2026-06-11 (migración session_memory_unique_session_date) → ON CONFLICT (session_date) válido
  created_at   timestamptz not null default now(),
  regime       text,  -- v3.0 (2026-06-11): texto libre — el concepto TREND/RANGE fue eliminado; post-close escribe 'v3'
  assets       text[],
  total_pnl    numeric,
  win_rate     numeric check (win_rate between 0 and 100),
  trade_count  integer,
  observations jsonb,   -- { worked: [], failed: [], patterns: [] }
  parameters   jsonb,   -- suggested adjustments for next session
  summary      text     -- narrative written by the agent
);

create index if not exists session_memory_date_idx on session_memory (session_date desc);

-- SESSION_STATE (Pulse v3.0, 2026-06-11)
-- Intra-day loop state, one row per trading date.
-- `state` JSONB v3.0: last_1min_UTC, vol30_baseline, yesterday{vpoc,vah,val,close},
-- gates{rsi2_on,fvg_on,gapf_on,vwappb_on,gap_pct,open_loc,rvol30,xvwap60,computed_10,computed_1030},
-- session_low/high, QQQ{vwap_num,vwap_den,vwap,ema9,ema21,rsi14{ag,al},atr1m,last_close,
-- xvwap_count,m5{closes[],rsi2{ag2,al2},atr5m,last_seal_UTC}}, c4{fvg,vwappb,rsi2},
-- fvg{fills_today,active}, position. Seeded by /pre-market, updated each cycle via
-- `state || jsonb_build_object(...)` on changed paths, read by cycle_prompt.md STEP 0.
-- (Filas anteriores a 2026-06-11 usan la estructura v2.x — históricas.)
create table if not exists session_state (
  date       date primary key,
  state      jsonb not null,
  updated_at timestamptz not null default now()
);

-- ALPACA_STATE
-- Cached snapshot of live Alpaca account + positions (synced every minute by Vercel cron)
create table if not exists alpaca_state (
  key           text primary key default 'current',
  synced_at     timestamptz not null default now(),
  equity        numeric,
  cash          numeric,
  buying_power  numeric,
  day_pl        numeric,
  unrealized_pl numeric,
  positions     jsonb
);

-- VOLUME_PROFILES (Pulse v2.8)
-- End-of-session Volume Profile snapshot per (date, symbol).
-- Written by post-close from session_state.developing; read by pre-market the next morning
-- as `yesterday_profile`, avoiding a paginated tick re-fetch.
-- day_high, day_low and session_close are stored so the naked-POC check can be done
-- as a pure SQL self-join without any extra bar pulls.
create table if not exists volume_profiles (
  date          date not null,
  symbol        text not null,
  vpoc          numeric not null,        -- midpoint price of the highest-volume bin
  vah           numeric not null,        -- upper edge of the 70% value area
  val           numeric not null,        -- lower edge of the 70% value area
  total_volume  bigint  not null,        -- sum of size across all bins
  bin_size      numeric not null,        -- bin width used (= 0.0005 × prior-day close, min $0.01)
  day_high      numeric not null,        -- session high (for naked-POC touched check)
  day_low       numeric not null,        -- session low  (for naked-POC touched check)
  session_close numeric not null,        -- last close — feeds next day's bin_size
  created_at    timestamptz not null default now(),
  primary key (date, symbol)
);

create index if not exists volume_profiles_symbol_date_idx
  on volume_profiles (symbol, date desc);

-- SITUATIONAL_ANALYSIS (Pulse v2.8, 2026-06-01)
-- D-1 → D bias snapshots written by the `/situational` skill.
-- Informational only — does NOT affect the trading loop.
-- Multiple rows per (session_date, symbol) are expected (pre-market, midday,
-- pre-close snapshots all coexist).
create table if not exists situational_analysis (
  id              uuid primary key default gen_random_uuid(),
  created_at      timestamptz not null default now(),
  session_date    date not null,
  symbol          text not null,
  -- Yesterday's reference levels (from volume_profiles)
  y_close         numeric,
  y_high          numeric,
  y_low           numeric,
  y_vpoc          numeric,
  y_vah           numeric,
  y_val           numeric,
  -- Today's developing levels at snapshot time
  t_open          numeric,
  t_high          numeric,
  t_low           numeric,
  t_current       numeric,
  -- Classification
  gap_type        text check (gap_type in (
                    'gap_up_outside','gap_up_inside','inside',
                    'gap_down_inside','gap_down_outside','overlap')),
  range_structure text check (range_structure in (
                    'higher_high','lower_low','inside_day','expansion','contraction')),
  bias            text not null check (bias in ('bullish','bearish','neutral','mixed')),
  confidence      numeric check (confidence between 0 and 1),
  target_levels   jsonb default '[]'::jsonb,   -- [{ price, label, reason }]
  invalidation    numeric,                     -- price below/above which thesis is void
  thesis          text,
  notes           text,
  -- Universe is QQQ-only. Constraint applied with NOT VALID so any
  -- pre-existing non-QQQ rows are grandfathered; new inserts must be QQQ.
  constraint situational_analysis_symbol_check
    check (symbol = 'QQQ')
);

create index if not exists situational_session_date_idx
  on situational_analysis (session_date desc);
create index if not exists situational_symbol_date_idx
  on situational_analysis (symbol, session_date desc);

-- SHADOW_SIGNALS (Pulse v3.0, 2026-06-11) — vista
-- Expande analysis_log.indicators->'shadow_signals' (array JSONB que el loop
-- loggea cuando un sistema SHADOW dispara: S1 RSI2-dip / S4 SWP / S5 GAPF)
-- a filas planas para el dashboard y la validación de 5 sesiones.
-- security_invoker => respeta el RLS de analysis_log (anon select).
create or replace view public.shadow_signals
  with (security_invoker = true) as
select
  al.id          as log_id,
  al.created_at,
  (al.created_at at time zone 'America/New_York')::date as session_date,
  s->>'sys'                     as sys,
  s->>'ts_signal_ET'            as ts_signal_et,
  s->>'ts_eval_ET'              as ts_eval_et,
  nullif(s->>'latency_s','')::numeric as latency_s,
  nullif(s->>'entry','')::numeric     as entry,
  nullif(s->>'sl','')::numeric        as sl,
  nullif(s->>'tp','')::numeric        as tp,
  s->>'note'                    as note
from public.analysis_log al
cross join lateral jsonb_array_elements(al.indicators->'shadow_signals') as s
where al.indicators ? 'shadow_signals';

grant select on public.shadow_signals to anon;

-- ============================================================
-- QQQ-only enforcement (migration qqq_only_check_constraints_not_valid, 2026-06-17)
-- NOT VALID: las filas históricas no-QQQ (era v2: TSLA/RIVN/TQQQ) quedan grandfathered;
-- solo los INSERT nuevos se validan. situational_analysis ya trae su propio check QQQ.
-- Idempotente para re-ejecución de este archivo.
-- ============================================================
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'trades_asset_qqq_check') then
    alter table public.trades add constraint trades_asset_qqq_check check (asset = 'QQQ') not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'analysis_log_asset_qqq_check') then
    alter table public.analysis_log add constraint analysis_log_asset_qqq_check check (asset = 'QQQ') not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'volume_profiles_symbol_qqq_check') then
    alter table public.volume_profiles add constraint volume_profiles_symbol_qqq_check check (symbol = 'QQQ') not valid;
  end if;
end $$;

-- ============================================================
-- Row Level Security
-- All tables have RLS enabled.
-- anon role: SELECT only (dashboard reads via NEXT_PUBLIC_SUPABASE_ANON_KEY).
-- Writes (INSERT/UPDATE/UPSERT) go through service_role key in API routes —
-- service_role bypasses RLS so no write policies are needed.
-- ============================================================

alter table public.trades               enable row level security;
alter table public.analysis_log         enable row level security;
alter table public.agent_status         enable row level security;
alter table public.champion_strategy    enable row level security;
alter table public.session_memory       enable row level security;
alter table public.session_state        enable row level security;
alter table public.alpaca_state         enable row level security;
alter table public.volume_profiles      enable row level security;
alter table public.situational_analysis enable row level security;

-- Public read policies (dashboard uses anon key)
create policy "anon_select" on public.trades               for select to anon using (true);
create policy "anon_select" on public.analysis_log         for select to anon using (true);
create policy "anon_select" on public.agent_status         for select to anon using (true);
create policy "anon_select" on public.champion_strategy    for select to anon using (true);
create policy "anon_select" on public.session_memory       for select to anon using (true);
create policy "anon_select" on public.session_state        for select to anon using (true);
create policy "anon_select" on public.alpaca_state         for select to anon using (true);
create policy "anon_select" on public.volume_profiles      for select to anon using (true);
create policy "anon_select" on public.situational_analysis for select to anon using (true);

-- Data API grants (required from October 30, 2026)
grant select on public.trades               to anon;
grant select on public.analysis_log         to anon;
grant select on public.agent_status         to anon;
grant select on public.champion_strategy    to anon;
grant select on public.session_memory       to anon;
grant select on public.session_state        to anon;
grant select on public.alpaca_state         to anon;
grant select on public.volume_profiles      to anon;
grant select on public.situational_analysis to anon;

-- ============================================================
-- Fase 3A (2026-06-17): registro canónico de estrategias + normalización
-- migration: fase3a_strategy_registry_and_backfill
-- Versiones granulares: cada (nombre+versión) es su propia estrategia; `aliases`
-- solo unifica variantes de formato del MISMO nombre+versión (p.ej. pulse_v2/pulse-v2).
-- ============================================================
create table if not exists strategy_registry (
  strategy_id  text primary key,
  name         text not null,
  family       text,
  direction    text not null default 'long' check (direction in ('long','short')),
  status       text not null check (status in ('live','shadow','archived','research')),
  spec_version text,
  since        date,
  aliases      text[] default '{}',
  notes        text,
  updated_at   timestamptz default now()
);

-- columna canónica en trades (nullable, aditiva; el `strategy` raw se conserva como provenance)
alter table trades add column if not exists strategy_id text references strategy_registry(strategy_id);

-- auto-mapeo de trades nuevos: etiqueta raw -> strategy_id canónico (sin tocar cycle_prompt)
create or replace function trades_set_strategy_id() returns trigger as $$
begin
  if new.strategy_id is null and new.strategy is not null then
    select strategy_id into new.strategy_id from strategy_registry where new.strategy = any(aliases);
  end if;
  return new;
end $$ language plpgsql;

drop trigger if exists trg_trades_strategy_id on trades;
create trigger trg_trades_strategy_id
  before insert or update of strategy on trades
  for each row execute function trades_set_strategy_id();

alter table public.strategy_registry enable row level security;
drop policy if exists "anon_select" on public.strategy_registry;
create policy "anon_select" on public.strategy_registry for select to anon using (true);
grant select on public.strategy_registry to anon;
