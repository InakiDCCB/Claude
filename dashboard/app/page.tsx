import { createSupabase } from '@/lib/supabase'
import type { Trade, AlpacaState, SessionStateRow, ShadowAccum, PnlPoint, StrategyRanking, StrategyRegistry } from '@/lib/supabase'
import TradingPanel from '@/components/TradingPanel'
import DashboardHeader from '@/components/DashboardHeader'

export const revalidate = 0

export default async function Page() {
  let trades:       Trade[]             = []
  let alpacaState:  AlpacaState | null  = null
  let sessionState: SessionStateRow | null = null
  let shadowAccum:  ShadowAccum[]       = []
  let pnlHistory:   PnlPoint[]          = []
  let ranking:      StrategyRanking[]   = []
  let registry:     StrategyRegistry[]  = []

  try {
    const sb = createSupabase()
    // trades: una sola fetch (limit 5000 — cubre tanto la tabla reciente como el
    // historial de P&L completo, hoy con margen amplio sobre las ~140 filas reales;
    // antes eran 2 queries redundantes con distinto limit/orden/filtro sobre la
    // misma tabla). Se deriva ambas vistas en memoria.
    const [tradesRes, alpacaStateRes, sessionStateRes, shadowAccumRes, rankingRes, registryRes] = await Promise.all([
      sb.from('trades').select('*').order('created_at', { ascending: false }).limit(5000),
      sb.from('alpaca_state').select('*').eq('key', 'current').single(),
      sb.from('session_state').select('*').order('date', { ascending: false }).limit(1).maybeSingle(),
      // C.4 — outcomes shadow acumulados (misma fuente que memoria)
      sb.from('v_shadow_accumulated').select('*'),
      // Fase 3 — ranking de estrategias (último snapshot)
      sb.from('v_strategy_ranking').select('*'),
      sb.from('strategy_registry').select('*').order('strategy_id'),
    ])
    const allTrades = (tradesRes.data ?? []) as Trade[]
    trades       = allTrades.slice(0, 2000)
    // Performance: P&L realizado de TODA la vida de la cuenta, fuente = trades (broker-reconciled)
    pnlHistory   = allTrades
      .filter((t): t is Trade & { pnl: number } => t.pnl !== null)
      .map(t => ({ created_at: t.created_at, pnl: t.pnl }))
      .sort((a, b) => a.created_at.localeCompare(b.created_at))
    alpacaState  = (alpacaStateRes.data  ?? null) as AlpacaState | null
    sessionState = (sessionStateRes.data ?? null) as SessionStateRow | null
    shadowAccum  = (shadowAccumRes.data  ?? []) as ShadowAccum[]
    ranking      = (rankingRes.data      ?? []) as StrategyRanking[]
    registry     = (registryRes.data     ?? []) as StrategyRegistry[]
  } catch {
    // Supabase unavailable (missing env vars or network) — render empty state
  }

  return (
    <main className="min-h-screen bg-[var(--surface-0)] pb-16">
      <DashboardHeader sessionState={sessionState} alpacaState={alpacaState} />

      <div className="max-w-[1680px] mx-auto px-8 pt-6 flex flex-col gap-6">
        <TradingPanel
          initialTrades={trades}
          alpacaState={alpacaState}
          sessionState={sessionState}
          shadowAccum={shadowAccum}
          pnlHistory={pnlHistory}
          ranking={ranking}
          registry={registry}
        />
      </div>
    </main>
  )
}
