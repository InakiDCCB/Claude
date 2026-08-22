'use client'

import { useEffect, useState } from 'react'
import { createSupabase } from '@/lib/supabase'
import type { Trade, AlpacaState, SessionStateRow, ShadowAccum, PnlPoint, StrategyRanking, StrategyRegistry } from '@/lib/supabase'
import PerformanceSummary from './PerformanceSummary'
import HealthGrid from './HealthGrid'
import DataTabs from './DataTabs'
import SystemsCard from './SystemsCard'

// ─── Toast ────────────────────────────────────────────────────────────────────

function TradeToast({ trade, onClose }: { trade: Trade; onClose: () => void }) {
  const isExit   = trade.exit_price != null
  const pnl      = trade.pnl
  const exitType = trade.exit_type

  return (
    <div className="fixed bottom-5 right-5 z-50 animate-slide-in">
      <div className="bg-[var(--surface-1)] border border-[var(--border)] rounded-lg p-4 shadow-2xl w-72">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: 'var(--green-dim)' }} />
              <span className="font-mono text-[10px] font-semibold uppercase tracking-widest" style={{ color: 'var(--green-dim)' }}>
                {isExit ? 'Trade closed' : 'Trade opened'}
              </span>
            </div>
            <p className="text-sm font-semibold truncate" style={{ color: 'var(--text-0)' }}>
              {trade.asset}&nbsp;&middot;&nbsp;
              <span style={{ color: trade.side === 'buy' ? 'var(--green-dim)' : 'var(--red)' }}>{trade.side.toUpperCase()}</span>
              &nbsp;{trade.quantity} @ ${trade.price.toFixed(2)}
            </p>
            {isExit && (
              <p className="font-mono text-xs mt-0.5">
                <span style={{ color: 'var(--text-4)' }}>exit:&nbsp;</span>
                <span style={{ color: 'var(--text-0)' }}>${trade.exit_price!.toFixed(2)}</span>
                {exitType && (
                  <span className="ml-2 px-1 py-px rounded text-[9px]" style={{ background: 'var(--surface-2)', color: 'var(--text-3)' }}>{exitType}</span>
                )}
              </p>
            )}
            {pnl != null && (
              <p className="font-mono text-xs font-semibold mt-0.5" style={{ color: pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
                P&amp;L: {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
              </p>
            )}
          </div>
          <button onClick={onClose} className="flex-shrink-0 mt-0.5 transition-colors" style={{ color: 'var(--text-5)' }} aria-label="Close">
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
  alpacaState,
  sessionState,
  shadowAccum,
  pnlHistory,
  ranking,
  registry,
}: {
  initialTrades: Trade[]
  alpacaState:   AlpacaState | null
  sessionState:  SessionStateRow | null
  shadowAccum:   ShadowAccum[]
  pnlHistory:    PnlPoint[]
  ranking:       StrategyRanking[]
  registry:      StrategyRegistry[]
}) {
  const [trades,     setTrades]     = useState<Trade[]>(initialTrades)
  const [newTradeId, setNewTradeId] = useState<string | null>(null)
  const [toast,      setToast]      = useState<Trade | null>(null)

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 5000)
    return () => clearTimeout(t)
  }, [toast])

  useEffect(() => {
    const sb = createSupabase()
    const channel = sb
      .channel('trades-live')
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'trades' }, (payload) => {
        const t = payload.new as Trade
        setTrades(prev => [t, ...prev])
        setNewTradeId(t.id)
        setToast(t)
        setTimeout(() => setNewTradeId(null), 3000)
      })
      .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'trades' }, (payload) => {
        const updated = payload.new as Trade
        setTrades(prev => prev.map(t => t.id === updated.id ? updated : t))
        setToast(updated)
      })
      .subscribe()
    return () => { sb.removeChannel(channel) }
  }, [])

  return (
    <>
      {toast && <TradeToast trade={toast} onClose={() => setToast(null)} />}

      <PerformanceSummary trades={trades} alpacaState={alpacaState} pnlHistory={pnlHistory} />
      <HealthGrid sessionState={sessionState} alpacaState={alpacaState} trades={trades} />
      <DataTabs trades={trades} newTradeId={newTradeId} />
      <SystemsCard ranking={ranking} registry={registry} accum={shadowAccum} trades={trades} />
    </>
  )
}
