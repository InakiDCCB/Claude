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

export type MarketSnapshot = {
  id: string
  captured_at: string
  asset: string
  timeframe: string
  open: number | null
  high: number | null
  low: number | null
  close: number
  volume: number | null
  vwap: number | null
  notes: string | null
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
