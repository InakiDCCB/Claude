'use client'

import { useEffect, useState } from 'react'
import type { Trade } from '@/lib/supabase'

type AlpacaAccount = {
  portfolio_value: string
  equity: string
  last_equity: string
  long_market_value: string
  short_market_value: string
  positions_count: number
}

function fmtUSD(v: string | number | null | undefined): string {
  if (v == null || v === '') return '—'
  const n = typeof v === 'string' ? parseFloat(v) : v
  if (isNaN(n)) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(n)
}

function StatCard({ label, value, sub, loading, valueColor }: {
  label: string
  value: string
  sub?: string
  loading?: boolean
  valueColor?: string
}) {
  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
      <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-1.5">{label}</p>
      {loading ? (
        <div className="h-7 w-28 bg-gray-800 rounded animate-pulse" />
      ) : (
        <p className={`text-xl font-mono font-semibold truncate ${valueColor ?? 'text-white'}`}>{value}</p>
      )}
      {sub && <p className="text-[11px] text-gray-600 mt-0.5 truncate">{sub}</p>}
    </div>
  )
}

function HitRatioGauge({ trades }: { trades: Trade[] }) {
  const closed  = trades.filter(t => t.pnl != null)
  const wins    = closed.filter(t => (t.pnl ?? 0) > 0).length
  const losses  = closed.filter(t => (t.pnl ?? 0) < 0).length
  const total   = wins + losses
  const pct     = total > 0 ? Math.round(wins / total * 100) : 0
  const wl      = losses > 0 ? (wins / losses).toFixed(2) : wins > 0 ? '∞' : '—'
  const color   = total === 0 ? '#374151' : pct >= 50 ? '#34d399' : '#f87171'
  const ARC     = Math.PI * 36
  const filled  = total > 0 ? (wins / total) * ARC : 0

  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
      <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-1">Hit Ratio</p>
      <div className="flex flex-col items-center gap-1">
        <svg viewBox="0 0 100 60" className="w-full max-w-[130px]">
          <path d="M 14 50 A 36 36 0 0 1 86 50" fill="none" stroke="#1f2937" strokeWidth="7" strokeLinecap="round" />
          <path
            d="M 14 50 A 36 36 0 0 1 86 50"
            fill="none"
            stroke={color}
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={`${filled} ${ARC - filled}`}
          />
          <text x="50" y="43" textAnchor="middle" fill="white" fontSize="13" fontWeight="700" fontFamily="ui-monospace,monospace">
            {total === 0 ? '—' : `${pct}%`}
          </text>
          <text x="50" y="54" textAnchor="middle" fill="#6b7280" fontSize="7" fontFamily="ui-monospace,monospace">
            {total > 0 ? `${total} trades` : ''}
          </text>
        </svg>
        <div className="grid grid-cols-3 gap-1 w-full text-center">
          <div>
            <p className="text-[9px] text-gray-600 uppercase">Wins</p>
            <p className="text-xs font-mono font-semibold text-emerald-400">{wins}</p>
          </div>
          <div>
            <p className="text-[9px] text-gray-600 uppercase">Losses</p>
            <p className="text-xs font-mono font-semibold text-red-400">{losses}</p>
          </div>
          <div>
            <p className="text-[9px] text-gray-600 uppercase">W/L</p>
            <p className="text-xs font-mono font-semibold text-white">{wl}</p>
          </div>
        </div>
        <span className="text-[9px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-500 font-mono">TOB-V2</span>
      </div>
    </div>
  )
}

function TopPerformers({ trades }: { trades: Trade[] }) {
  const byAsset: Record<string, number> = {}
  for (const t of trades) {
    if (t.pnl != null) byAsset[t.asset] = (byAsset[t.asset] ?? 0) + t.pnl
  }
  const winners = Object.entries(byAsset)
    .filter(([, pnl]) => pnl > 0)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6)
  const max = winners[0]?.[1] ?? 1

  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
      <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-3">Top Performers</p>
      {!winners.length ? (
        <p className="text-xs text-gray-600">Sin operaciones ganadoras</p>
      ) : (
        <div className="space-y-2">
          {winners.map(([asset, pnl]) => (
            <div key={asset} className="flex items-center gap-2">
              <span className="text-xs font-mono text-white w-10 shrink-0">{asset}</span>
              <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${(pnl / max) * 100}%` }} />
              </div>
              <span className="text-xs font-mono text-emerald-400 w-20 text-right shrink-0">+{fmtUSD(pnl)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function DollarPnL({ trades }: { trades: Trade[] }) {
  const closed    = trades.filter(t => t.pnl != null)
  const winsTotal = closed.filter(t => (t.pnl ?? 0) > 0).reduce((s, t) => s + (t.pnl ?? 0), 0)
  const lossTotal = closed.filter(t => (t.pnl ?? 0) < 0).reduce((s, t) => s + Math.abs(t.pnl ?? 0), 0)
  const net       = winsTotal - lossTotal
  const ratio     = lossTotal > 0 ? (winsTotal / lossTotal).toFixed(2) : winsTotal > 0 ? '∞' : '—'
  const maxBar    = Math.max(winsTotal, lossTotal, 1)

  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
      <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-3">P&L en $</p>

      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-[10px] text-gray-500 w-10 shrink-0">Wins</span>
        <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${(winsTotal / maxBar) * 100}%` }} />
        </div>
        <span className="text-[10px] font-mono text-emerald-400 w-16 text-right shrink-0">
          {winsTotal > 0 ? `+${fmtUSD(winsTotal)}` : '—'}
        </span>
      </div>

      <div className="flex items-center gap-2 mb-3">
        <span className="text-[10px] text-gray-500 w-10 shrink-0">Loss</span>
        <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div className="h-full bg-red-500 rounded-full" style={{ width: `${(lossTotal / maxBar) * 100}%` }} />
        </div>
        <span className="text-[10px] font-mono text-red-400 w-16 text-right shrink-0">
          {lossTotal > 0 ? `-${fmtUSD(lossTotal)}` : '—'}
        </span>
      </div>

      <div className="flex justify-between text-[10px]">
        <span className="text-gray-600">
          Ratio $: <span className="text-white font-mono">{ratio}×</span>
        </span>
        <span className={`font-mono ${net >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
          Neto {net >= 0 ? '+' : ''}{fmtUSD(net)}
        </span>
      </div>
    </div>
  )
}

export default function AccountSummary({ trades }: { trades: Trade[] }) {
  const [account, setAccount] = useState<AlpacaAccount | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/account')
      .then(r => r.json())
      .then(d => { setAccount(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const filled = trades.filter(t => t.status === 'filled')

  const equity     = account ? parseFloat(account.equity) : null
  const lastEquity = account ? parseFloat(account.last_equity) : null
  const portVal    = account ? parseFloat(account.portfolio_value) : null
  const delta      = equity != null && lastEquity != null && lastEquity > 0 ? equity - lastEquity : null
  const deltaPct   = delta != null && lastEquity ? (delta / lastEquity) * 100 : null
  const longVal    = account ? parseFloat(account.long_market_value) : null
  const longPct    = longVal != null && portVal != null && portVal > 0 ? (longVal / portVal) * 100 : null

  const closedTrades = filled.filter(t => t.pnl != null)
  const avgPnL       = closedTrades.length > 0
    ? closedTrades.reduce((s, t) => s + (t.pnl ?? 0), 0) / closedTrades.length
    : 0

  const deltaStr = deltaPct != null
    ? `${delta! >= 0 ? '▲' : '▼'} ${fmtUSD(Math.abs(delta!))} (${deltaPct >= 0 ? '+' : ''}${deltaPct.toFixed(2)}%)`
    : undefined

  const posStr = account
    ? `${account.positions_count} posición${account.positions_count !== 1 ? 'es' : ''}`
    : undefined

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <StatCard
        label="Portfolio Value"
        value={fmtUSD(account?.portfolio_value)}
        sub={deltaStr}
        loading={loading}
        valueColor={delta == null ? 'text-white' : delta >= 0 ? 'text-emerald-400' : 'text-red-400'}
      />
      <StatCard
        label="Long Value"
        value={fmtUSD(account?.long_market_value)}
        sub={longPct != null ? `${longPct.toFixed(1)}% del NAV` : undefined}
        loading={loading}
        valueColor="text-emerald-400"
      />
      <HitRatioGauge trades={trades} />
      <DollarPnL trades={trades} />

      <StatCard
        label="Market Value"
        value={fmtUSD(account?.equity)}
        sub={posStr}
        loading={loading}
      />
      <StatCard
        label="P&L Promedio"
        value={closedTrades.length > 0 ? `${avgPnL >= 0 ? '+' : ''}${fmtUSD(avgPnL)}` : '—'}
        sub={closedTrades.length > 0 ? `sobre ${closedTrades.length} trade${closedTrades.length !== 1 ? 's' : ''} cerrado${closedTrades.length !== 1 ? 's' : ''}` : 'sin trades cerrados'}
        valueColor={closedTrades.length === 0 ? 'text-white' : avgPnL >= 0 ? 'text-emerald-400' : 'text-red-400'}
      />
      <div className="col-span-2">
        <TopPerformers trades={trades} />
      </div>
    </div>
  )
}
