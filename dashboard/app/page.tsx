import { createSupabase } from '@/lib/supabase'
import type { Trade, AnalysisEntry, AgentStatus, ChampionConfig, AlpacaState, SessionStateRow, ShadowSignal } from '@/lib/supabase'
import TradingPanel from '@/components/TradingPanel'
import MarketStatus from '@/components/MarketStatus'

export const revalidate = 0

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ from?: string; to?: string }>
}) {
  const { from, to } = await searchParams

  // Default: last 30 days
  const fromDate = from ?? new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString()
  const toDate   = to   ?? new Date().toISOString()

  let trades:       Trade[]             = []
  let analysis:     AnalysisEntry[]     = []
  let agents:       AgentStatus[]       = []
  let champion:     ChampionConfig | null = null
  let alpacaState:  AlpacaState | null  = null
  let sessionState: SessionStateRow | null = null
  let shadowSignals: ShadowSignal[]     = []

  try {
    const sb = createSupabase()
    const [tradesRes, analysisRes, agentsRes, championRes, alpacaStateRes, sessionStateRes, shadowRes] = await Promise.all([
      sb.from('trades').select('*')
        .gte('created_at', fromDate).lte('created_at', toDate)
        .order('created_at', { ascending: false }),
      sb.from('analysis_log').select('*')
        .gte('created_at', fromDate).lte('created_at', toDate)
        .order('created_at', { ascending: false }),
      sb.from('agent_status').select('*').order('name'),
      sb.from('champion_strategy').select('*').eq('key', 'current').single(),
      sb.from('alpaca_state').select('*').eq('key', 'current').single(),
      sb.from('session_state').select('*').order('date', { ascending: false }).limit(1).maybeSingle(),
      sb.from('shadow_signals').select('*')
        .gte('created_at', fromDate).lte('created_at', toDate)
        .order('created_at', { ascending: false }).limit(500),
    ])
    trades        = (tradesRes.data       ?? []) as Trade[]
    analysis      = (analysisRes.data     ?? []) as AnalysisEntry[]
    agents        = (agentsRes.data       ?? []) as AgentStatus[]
    champion      = (championRes.data     ?? null) as ChampionConfig | null
    alpacaState   = (alpacaStateRes.data  ?? null) as AlpacaState | null
    sessionState  = (sessionStateRes.data ?? null) as SessionStateRow | null
    shadowSignals = (shadowRes.data       ?? []) as ShadowSignal[]
  } catch {
    // Supabase unavailable (missing env vars or network) — render empty state
  }

  return (
    <main className="min-h-screen bg-gray-950">
      {/* Header */}
      <div className="sticky top-0 z-10 border-b border-gray-800 bg-gray-950/90 backdrop-blur">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center gap-4">
          <div className="mr-auto">
            <h1 className="text-lg font-semibold tracking-tight text-white">Trading Dashboard</h1>
            <p className="text-xs text-gray-500 mt-0.5">Paper trading · Alpaca · Supabase</p>
          </div>
          <MarketStatus />
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-8">
        <TradingPanel
          initialTrades={trades}
          initialAnalysis={analysis}
          agents={agents}
          champion={champion}
          alpacaState={alpacaState}
          sessionState={sessionState}
          shadowSignals={shadowSignals}
        />
      </div>
    </main>
  )
}
