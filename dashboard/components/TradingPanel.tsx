'use client'

import { useEffect, useState } from 'react'
import { createSupabase } from '@/lib/supabase'
import type { Trade, AnalysisEntry, AgentStatus, ChampionConfig, AlpacaState, SessionStateRow, ShadowSignal, PnlPoint, StrategyRanking, MarketCondition, StrategyRegistry, MarketContext, MarketPattern, MarketHypothesis, EmergingLabel, MarketIntel } from '@/lib/supabase'
import AccountSummary from './AccountSummary'
import PerformanceCard from './PerformanceCard'
import AgentGrid from './AgentGrid'
import ChampionCard from './ChampionCard'
import DataTabs from './DataTabs'
import MarketCalendarCard from './MarketCalendarCard'
import SessionGatesCard from './SessionGatesCard'
import ShadowPanel from './ShadowPanel'
import StrategyRankingCard from './StrategyRankingCard'
import MarketConditionsCard from './MarketConditionsCard'
import MarketIntelligencePanel from './MarketIntelligencePanel'

// ─── Toast ────────────────────────────────────────────────────────────────────

function TradeToast({ trade, onClose }: { trade: Trade; onClose: () => void }) {
  const isExit  = trade.exit_price != null
  const pnl     = trade.pnl
  const exitType = trade.exit_type

  return (
    <div className="fixed bottom-5 right-5 z-50 animate-slide-in">
      <div className="bg-gray-800 border border-emerald-500/40 rounded-xl p-4 shadow-2xl w-72">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse flex-shrink-0" />
              <span className="text-[10px] font-semibold text-emerald-400 uppercase tracking-widest">
                {isExit ? 'Trade closed' : 'Trade opened'}
              </span>
            </div>
            <p className="text-sm font-semibold text-white truncate">
              {trade.asset}&nbsp;&middot;&nbsp;
              <span className={trade.side === 'buy' ? 'text-emerald-400' : 'text-red-400'}>
                {trade.side.toUpperCase()}
              </span>
              &nbsp;{trade.quantity} @ ${trade.price.toFixed(2)}
            </p>
            {isExit && (
              <p className="text-xs font-mono mt-0.5">
                <span className="text-gray-500">exit:&nbsp;</span>
                <span className="text-white">${trade.exit_price!.toFixed(2)}</span>
                {exitType && (
                  <span className="ml-2 px-1 py-px rounded text-[9px] bg-gray-700 text-gray-400 uppercase">
                    {exitType}
                  </span>
                )}
              </p>
            )}
            {pnl != null && (
              <p className={`text-xs font-mono font-semibold mt-0.5 ${pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                P&L: {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="flex-shrink-0 text-gray-600 hover:text-gray-300 transition-colors mt-0.5"
            aria-label="Close"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M6 18L18 6M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function TradingPanel({
  initialTrades,
  initialAnalysis,
  agents,
  champion,
  alpacaState,
  sessionState,
  shadowSignals,
  pnlHistory,
  ranking,
  conditions,
  registry,
  miContexts,
  miPatterns,
  miHypotheses,
  miEmerging,
  miIntel,
}: {
  initialTrades:   Trade[]
  initialAnalysis: AnalysisEntry[]
  agents:          AgentStatus[]
  champion:        ChampionConfig | null
  alpacaState:     AlpacaState | null
  sessionState:    SessionStateRow | null
  shadowSignals:   ShadowSignal[]
  pnlHistory:      PnlPoint[]
  ranking:         StrategyRanking[]
  conditions:      MarketCondition[]
  registry:        StrategyRegistry[]
  miContexts:      MarketContext[]
  miPatterns:      MarketPattern[]
  miHypotheses:    MarketHypothesis[]
  miEmerging:      EmergingLabel[]
  miIntel:         MarketIntel | null
}) {
  const [trades,        setTrades]        = useState<Trade[]>(initialTrades)
  const [liveAgents,    setLiveAgents]    = useState<AgentStatus[]>(agents)
  const [newTradeId,    setNewTradeId]    = useState<string | null>(null)
  const [toast,         setToast]         = useState<Trade | null>(null)
  const [isLive,        setIsLive]        = useState(false)

  // Auto-dismiss toast
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 5000)
    return () => clearTimeout(t)
  }, [toast])

  // Supabase Realtime subscription
  useEffect(() => {
    const sb = createSupabase()

    const channel = sb
      .channel('trades-live')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'trades' },
        (payload) => {
          const t = payload.new as Trade
          setTrades(prev => [t, ...prev])
          setNewTradeId(t.id)
          setToast(t)
          setTimeout(() => setNewTradeId(null), 3000)
        }
      )
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'trades' },
        (payload) => {
          const updated = payload.new as Trade
          setTrades(prev => prev.map(t => t.id === updated.id ? updated : t))
          setToast(updated)
        }
      )
      .subscribe((status) => {
        setIsLive(status === 'SUBSCRIBED')
      })

    return () => { sb.removeChannel(channel) }
  }, [])

  // Realtime: agent_status
  useEffect(() => {
    const sb = createSupabase()
    const channel = sb
      .channel('agents-live')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'agent_status' },
        (payload) => {
          const a = payload.new as AgentStatus
          setLiveAgents(prev => [...prev.filter(x => x.id !== a.id), a]
            .sort((a, b) => a.name.localeCompare(b.name)))
        }
      )
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'agent_status' },
        (payload) => {
          const a = payload.new as AgentStatus
          setLiveAgents(prev => prev.map(x => x.id === a.id ? a : x))
        }
      )
      .subscribe()
    return () => { sb.removeChannel(channel) }
  }, [])

  return (
    <>
      {toast && <TradeToast trade={toast} onClose={() => setToast(null)} />}

      {/* Niveles 1–3: Portfolio · Métricas · P&L por sistema */}
      <AccountSummary trades={trades} alpacaState={alpacaState} />

      {/* Nivel 3b: Performance histórica de la cuenta (vista Asset Management) */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Performance
        </h2>
        <PerformanceCard pnlHistory={pnlHistory} />
      </section>

      {/* Niveles 4-5: Agente + Active Strategy (izq) · Market Calendar (der, full height) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-8">
          <section>
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
              Agent
            </h2>
            <AgentGrid agents={liveAgents} />
          </section>
          <section>
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
              Active strategy
            </h2>
            <ChampionCard champion={champion} trades={trades} isBestPerformer={champion != null} />
          </section>
        </div>
        <div className="lg:h-full">
          <MarketCalendarCard />
        </div>
      </div>

      {/* Nivel 5b (v3.0): Gates del día · Shadow validation */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SessionGatesCard sessionState={sessionState} />
        <ShadowPanel signals={shadowSignals} registry={registry} />
      </div>

      {/* Nivel 5c (Fase 3): Ranking de estrategias · Condiciones de mercado */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Aprendizaje continuo
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <StrategyRankingCard ranking={ranking} />
          </div>
          <MarketConditionsCard conditions={conditions} />
        </div>
      </section>

      {/* Nivel 5d (Fase 3.1): Market Intelligence — contexto, patrones, hipótesis (advisory) */}
      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Market Intelligence
        </h2>
        <MarketIntelligencePanel
          intel={miIntel}
          contexts={miContexts}
          patterns={miPatterns}
          hypotheses={miHypotheses}
          emerging={miEmerging}
        />
      </section>

      {/* Nivel 6: Trades · P&L · Analysis Log */}
      <section>
        <DataTabs
          trades={trades}
          analysis={initialAnalysis}
          newTradeId={newTradeId}
          isLive={isLive}
        />
      </section>
    </>
  )
}
