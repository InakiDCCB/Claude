import { createSupabase } from '@/lib/supabase'
import type { Trade, AnalysisEntry, AgentStatus, ChampionConfig, AlpacaState, SessionStateRow, ShadowSignal, PnlPoint, StrategyRanking, MarketCondition, StrategyRegistry, MarketContext, MarketPattern, MarketHypothesis, EmergingLabel, MarketIntel } from '@/lib/supabase'
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
  let pnlHistory:   PnlPoint[]          = []
  let ranking:      StrategyRanking[]   = []
  let conditions:   MarketCondition[]   = []
  let registry:     StrategyRegistry[]  = []
  let miContexts:   MarketContext[]     = []
  let miPatterns:   MarketPattern[]     = []
  let miHypotheses: MarketHypothesis[]  = []
  let miEmerging:   EmergingLabel[]     = []
  let miIntel:      MarketIntel | null  = null

  try {
    const sb = createSupabase()
    const [tradesRes, analysisRes, agentsRes, championRes, alpacaStateRes, sessionStateRes, shadowRes, pnlRes, rankingRes, conditionsRes, registryRes, miCtxRes, miPatRes, miHypRes, miEmgRes, miIntelRes] = await Promise.all([
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
      // Performance view: P&L realizado de TODA la vida de la cuenta (no filtrado por from/to);
      // fuente = trades (reconciliada con broker), no session_memory
      sb.from('trades')
        .select('created_at,pnl')
        .not('pnl', 'is', null)
        .order('created_at', { ascending: true }).limit(5000),
      // Fase 3 — ranking de estrategias (último snapshot) + condiciones recientes
      sb.from('v_strategy_ranking').select('*'),
      sb.from('market_conditions').select('*').order('session_date', { ascending: false }).limit(12),
      sb.from('strategy_registry').select('*').order('strategy_id'),
      // Fase 3.1 — Market Intelligence (capa cualitativa/contextual)
      sb.from('v_market_context').select('*').limit(12),
      sb.from('v_market_patterns').select('*').limit(40),
      sb.from('v_market_hypotheses').select('*').limit(40),
      sb.from('v_emerging_context_labels').select('*'),
      sb.from('v_market_intelligence').select('*').maybeSingle(),
    ])
    trades        = (tradesRes.data       ?? []) as Trade[]
    analysis      = (analysisRes.data     ?? []) as AnalysisEntry[]
    agents        = (agentsRes.data       ?? []) as AgentStatus[]
    champion      = (championRes.data     ?? null) as ChampionConfig | null
    alpacaState   = (alpacaStateRes.data  ?? null) as AlpacaState | null
    sessionState  = (sessionStateRes.data ?? null) as SessionStateRow | null
    shadowSignals = (shadowRes.data       ?? []) as ShadowSignal[]
    pnlHistory    = (pnlRes.data          ?? []) as PnlPoint[]
    ranking       = (rankingRes.data      ?? []) as StrategyRanking[]
    conditions    = (conditionsRes.data   ?? []) as MarketCondition[]
    registry      = (registryRes.data     ?? []) as StrategyRegistry[]
    miContexts    = (miCtxRes.data        ?? []) as MarketContext[]
    miPatterns    = (miPatRes.data        ?? []) as MarketPattern[]
    miHypotheses  = (miHypRes.data        ?? []) as MarketHypothesis[]
    miEmerging    = (miEmgRes.data        ?? []) as EmergingLabel[]
    miIntel       = (miIntelRes.data      ?? null) as MarketIntel | null
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
          pnlHistory={pnlHistory}
          ranking={ranking}
          conditions={conditions}
          registry={registry}
          miContexts={miContexts}
          miPatterns={miPatterns}
          miHypotheses={miHypotheses}
          miEmerging={miEmerging}
          miIntel={miIntel}
        />
      </div>
    </main>
  )
}
