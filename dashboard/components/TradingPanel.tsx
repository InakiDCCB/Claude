'use client'

import { useEffect, useState } from 'react'
import { createSupabase } from '@/lib/supabase'
import type { Trade, AnalysisEntry, AgentStatus, ChampionConfig } from '@/lib/supabase'
import AccountSummary from './AccountSummary'
import AgentGrid from './AgentGrid'
import ChampionCard, { IncomingSlot } from './ChampionCard'
import DataTabs from './DataTabs'

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
                {isExit ? 'Trade cerrado' : 'Trade abierto'}
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
                <span className="text-gray-500">salida:&nbsp;</span>
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
            aria-label="Cerrar"
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
}: {
  initialTrades:   Trade[]
  initialAnalysis: AnalysisEntry[]
  agents:          AgentStatus[]
  champion:        ChampionConfig | null
}) {
  const [trades,      setTrades]      = useState<Trade[]>(initialTrades)
  const [newTradeId,  setNewTradeId]  = useState<string | null>(null)
  const [toast,       setToast]       = useState<Trade | null>(null)
  const [isLive,      setIsLive]      = useState(false)

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

  return (
    <>
      {toast && <TradeToast trade={toast} onClose={() => setToast(null)} />}

      <AccountSummary trades={trades} />

      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Estrategias
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
          <ChampionCard champion={champion} />
          <IncomingSlot />
          <IncomingSlot />
          <IncomingSlot />
        </div>
      </section>

      <section>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Agentes
        </h2>
        <AgentGrid agents={agents} />
      </section>

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
