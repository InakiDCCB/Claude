import { createSupabase } from '@/lib/supabase'
import type { Trade, AlpacaState, SessionStateRow, ShadowAccum, StrategyRanking, StrategyRegistry } from '@/lib/supabase'
import { fetchAlpacaState, fetchAlpacaDailyPnl, type DailyPnlPoint } from '@/lib/alpaca-sync'
import TradingPanel from '@/components/TradingPanel'
import DashboardHeader from '@/components/DashboardHeader'

export const revalidate = 0

export default async function Page() {
  let trades:       Trade[]             = []
  let alpacaState:  AlpacaState | null  = null
  let sessionState: SessionStateRow | null = null
  let shadowAccum:  ShadowAccum[]       = []
  let dailyPnl:     DailyPnlPoint[]     = []
  let ranking:      StrategyRanking[]   = []
  let registry:     StrategyRegistry[]  = []
  let alpacaDebug:  string              = ''

  try {
    const sb = createSupabase()
    const [tradesRes, liveAlpaca, dailyPnlRes, sessionStateRes, shadowAccumRes, rankingRes, registryRes] = await Promise.all([
      sb.from('trades').select('*').order('created_at', { ascending: false }).limit(5000),
      // Cuenta/posiciones: directo a Alpaca en cada carga (Next revalidate=15s server-side),
      // NO vía alpaca_state — esa tabla depende del cron externo (cron-job.org) que estuvo
      // muerto 11 días (2026-09-04→09-15) sin que nada lo notara. Ver lib/alpaca-sync.ts.
      fetchAlpacaState(),
      // Performance (Net P&L, equity curve): curva diaria real de Alpaca, NO trades.pnl
      // agregado por día — ese ledger interno arrastra ~$20 de drift (fees no logueadas +
      // fills viejos con precio de salida estimado a mano). Ver fetchAlpacaDailyPnl.
      fetchAlpacaDailyPnl(),
      sb.from('session_state').select('*').order('date', { ascending: false }).limit(1).maybeSingle(),
      // C.4 — outcomes shadow acumulados (misma fuente que memoria)
      sb.from('v_shadow_accumulated').select('*'),
      // Fase 3 — ranking de estrategias (último snapshot)
      sb.from('v_strategy_ranking').select('*'),
      sb.from('strategy_registry').select('*').order('strategy_id'),
    ])
    const allTrades = (tradesRes.data ?? []) as Trade[]
    trades       = allTrades.slice(0, 2000)
    dailyPnl     = dailyPnlRes
    if (!liveAlpaca.ok) {
      // Visible en Vercel → Project → Logs. Causa típica: ALPACA_API_KEY/
      // ALPACA_SECRET_KEY ausentes o desactualizadas para el environment
      // Production (distintas de dashboard/.env.local en local).
      console.error('fetchAlpacaState failed:', liveAlpaca.error)
      alpacaDebug = liveAlpaca.error ?? 'unknown'
    }
    if (dailyPnlRes.length === 0) {
      console.error('fetchAlpacaDailyPnl returned empty — check ALPACA_API_KEY/ALPACA_SECRET_KEY in Vercel')
    }
    alpacaState  = liveAlpaca.ok
      ? {
          key: 'current', synced_at: liveAlpaca.synced_at!, equity: liveAlpaca.equity ?? null,
          cash: liveAlpaca.cash ?? null, buying_power: liveAlpaca.buying_power ?? null,
          day_pl: liveAlpaca.day_pl ?? null, unrealized_pl: liveAlpaca.unrealized_pl ?? null,
          positions: liveAlpaca.positions ?? [],
        } as AlpacaState
      : null
    sessionState = (sessionStateRes.data ?? null) as SessionStateRow | null
    shadowAccum  = (shadowAccumRes.data  ?? []) as ShadowAccum[]
    ranking      = (rankingRes.data      ?? []) as StrategyRanking[]
    registry     = (registryRes.data     ?? []) as StrategyRegistry[]
  } catch {
    // Supabase unavailable (missing env vars or network) — render empty state
  }

  return (
    <main className="min-h-screen bg-[var(--surface-0)] pb-16">
      {/* TEMP debug 2026-09-15 — remove once Alpaca prod fetch is confirmed fixed */}
      {alpacaDebug && <div dangerouslySetInnerHTML={{ __html: `<!-- alpaca-debug: ${alpacaDebug.replace(/--/g, '—')} -->` }} />}
      <DashboardHeader sessionState={sessionState} alpacaState={alpacaState} />

      <div className="max-w-[1680px] mx-auto px-8 pt-6 flex flex-col gap-6">
        <TradingPanel
          initialTrades={trades}
          alpacaState={alpacaState}
          sessionState={sessionState}
          shadowAccum={shadowAccum}
          dailyPnl={dailyPnl}
          ranking={ranking}
          registry={registry}
        />
      </div>
    </main>
  )
}
