import { createClient } from '@supabase/supabase-js'

export function createSupabase() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}

export type Trade = {
  id: string
  created_at: string
  filled_at: string | null
  asset: string
  side: 'buy' | 'sell'
  quantity: number
  price: number
  total_value: number
  order_id: string | null
  status: string
  strategy: string | null
  exit_price: number | null
  exit_type: string | null
  pnl: number | null
  notes: string | null
}

export type AnalysisEntry = {
  id: string
  created_at: string
  asset: string
  timeframe: string | null
  signal: 'bullish' | 'bearish' | 'neutral' | 'watching' | null
  confidence: number | null
  indicators: Record<string, unknown> | null
  thesis: string | null
  outcome: string | null
  tags: string[] | null
}

export type AgentStatus = {
  id: string
  name: string
  status: 'running' | 'idle' | 'error' | 'disconnected'
  description: string | null
  updated_at: string
  metadata: Record<string, unknown> | null
}

export type ChampionConfig = {
  key: string
  updated_at: string
  config: Record<string, unknown>
}

export type AlpacaPosition = {
  symbol:       string
  qty:          number
  avg_entry:    number
  price:        number
  market_value: number
  pl:           number
  pl_pct:       number
}

export type AlpacaState = {
  key:           string
  synced_at:     string
  equity:        number | null
  cash:          number | null
  buying_power:  number | null
  day_pl:        number | null
  unrealized_pl: number | null
  positions:     AlpacaPosition[] | null
}

// ─── Pulse v3.0 ───────────────────────────────────────────────────────────────

// session_state.state JSONB (v3.0) — campos que el dashboard lee; todos opcionales
// porque las filas pre-v3 usan otra estructura.
export type SessionGates = {
  rsi2_on?: boolean
  fvg_on?: boolean
  gapf_on?: boolean
  vwappb_on?: boolean
  gap_pct?: number
  open_loc?: string
  rvol30?: number
  xvwap60?: number
  computed_10?: boolean
  computed_1030?: boolean
}

export type SessionStateRow = {
  date: string
  updated_at: string
  state: {
    gates?: SessionGates
    c4?: Record<string, number>
    fvg?: { fills_today?: number; active?: Record<string, unknown> | null }
    position?: Record<string, unknown> | null
    session_low?: number
    session_high?: number
    QQQ?: { vwap?: number; last_close?: number; atr1m?: number; [k: string]: unknown }
    [k: string]: unknown
  }
}

// Punto de P&L realizado (trades cerrados, vida completa de la cuenta) — fuente del PerformanceCard.
// Se deriva de `trades` (reconciliada con broker), NO de session_memory (diario cualitativo).
export type PnlPoint = {
  created_at: string
  pnl: number
}

// Fila de la vista shadow_signals (validación 5 sesiones de S1/S4/S5)
export type ShadowSignal = {
  log_id: string
  created_at: string
  session_date: string
  sys: string | null
  ts_signal_et: string | null
  ts_eval_et: string | null
  latency_s: number | null
  entry: number | null
  sl: number | null
  tp: number | null
  note: string | null
}

// Fila de la vista v_strategy_ranking (Fase 3 — aprendizaje continuo)
export type StrategyRanking = {
  strategy_id:  string
  name:         string
  status:       'live' | 'shadow' | 'archived' | 'research'
  direction:    'long' | 'short'
  family:       string | null
  n:            number
  wr:           number | null
  wr_wilson_lb: number | null
  pf:           number | null
  expectancy:   number | null
  exp_lb:       number | null
  max_drawdown: number | null
  consistency:  number | null
  robustness:   number | null
  tier:         'insufficient_data' | 'provisional' | 'established'
  score:        number | null
  as_of:        string
}

// Fila de strategy_registry (catálogo canónico de estrategias + su status)
export type StrategyRegistry = {
  strategy_id:  string
  name:         string
  family:       string | null
  direction:    'long' | 'short'
  status:       'live' | 'shadow' | 'archived' | 'research'
  spec_version: string | null
  notes:        string | null
}

// Fila de market_conditions (Fase 3B — clasificación por sesión)
export type MarketCondition = {
  session_date:  string
  symbol:        string
  rvol30:        number | null
  gap_pct:       number | null
  open_loc:      string | null
  xvwap60:       number | null
  day_range_pct: number | null
  liquidity:     'low' | 'high' | null
  volatility:    'low' | 'high' | null
  regime:        string | null
  quadrant:      string | null
}

// ─── Fase 3.1 — Market Intelligence (capa cualitativa/contextual, advisory) ────

// Contexto cualitativo por sesión (v_market_context). signature = vector de features usado.
export type MarketContext = {
  session_date:    string
  symbol:          string
  context_label:   string | null
  context_tags:    string[] | null
  signature:       Record<string, unknown> | null
  agent_note:      string | null
  candidate_label: string | null
}

// Patrón recurrente descubierto por el motor (v_market_patterns)
export type MarketPattern = {
  pattern_key:    string
  kind:           'context_strategy' | 'context_transition' | 'context_outcome' | 'precursor'
  context_bucket: string | null
  subject:        string | null
  description:    string | null
  n_support:      number
  n_contra:       number
  effect:         number | null
  baseline:       number | null
  stability:      number | null
  status:         'emerging' | 'consolidated' | 'dormant'
  first_seen:     string | null
  last_seen:      string | null
}

// Hipótesis en validación continua (v_market_hypotheses)
export type MarketHypothesis = {
  pattern_key:        string
  hypothesis:         string
  context_bucket:     string | null
  subject:            string | null
  status:             'active' | 'observing' | 'discarded' | 'consolidated'
  n_support:          number
  n_contra:           number
  stability:          number | null
  since:              string | null
  last_evidence_date: string | null
  discarded_reason:   string | null
}

// Etiqueta de contexto emergente propuesta por el agente (v_emerging_context_labels)
export type EmergingLabel = {
  candidate_label: string
  n_sessions:      number
  first_seen:      string | null
  last_seen:       string | null
  recognized:      boolean
}

// Roll-up compacto para cabecera + memoria (v_market_intelligence, fila única)
export type MarketIntel = {
  latest_context:        string | null
  dominant_recent:       string | null
  sessions_classified:   number
  patterns_consolidated: number
  patterns_emerging:     number
  hypotheses_active:     number
  hypotheses_discarded:  number
  emerging_labels:       number
  favored_strategies:    string[] | null
}

// Server-only: bypasses RLS — use only in API routes, never in client components
export function createSupabaseAdmin() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  )
}
