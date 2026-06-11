'use client'

import { useEffect, useState } from 'react'
import type { Trade, AlpacaState } from '@/lib/supabase'

type AlpacaAccount = {
  portfolio_value: string
  equity: string
  last_equity: string
  long_market_value: string
  short_market_value: string
  cash: string
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

function PortfolioCard({ account, loading }: { account: AlpacaAccount | null; loading: boolean }) {
  const portDelta    = account ? parseFloat(account.equity) - parseFloat(account.last_equity) : null
  const portDeltaPct = portDelta != null && account && parseFloat(account.last_equity) > 0
    ? (portDelta / parseFloat(account.last_equity)) * 100
    : null
  const pColor = portDelta == null ? 'text-white' : portDelta >= 0 ? 'text-emerald-400' : 'text-red-400'

  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4 flex flex-col h-full">
      <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-3">Account</p>

      <div className="flex flex-col divide-y divide-gray-800/60 flex-1">
        {/* Portfolio Value */}
        <div className="pb-3 flex-1 flex flex-col justify-center">
          <p className="text-[10px] text-gray-600 mb-1">Portfolio</p>
          {loading ? (
            <div className="h-5 w-28 bg-gray-800 rounded animate-pulse" />
          ) : (
            <p className={`text-sm font-mono font-semibold truncate ${pColor}`}>{fmtUSD(account?.portfolio_value)}</p>
          )}
          {portDeltaPct != null && (
            <p className="text-[10px] text-gray-600 mt-0.5">
              {portDeltaPct >= 0 ? '▲' : '▼'} {portDeltaPct >= 0 ? '+' : ''}{portDeltaPct.toFixed(2)}% vs yesterday
            </p>
          )}
        </div>

        {/* Market Value */}
        <div className="py-3 flex-1 flex flex-col justify-center">
          <p className="text-[10px] text-gray-600 mb-1">Market Value</p>
          {loading ? (
            <div className="h-5 w-24 bg-gray-800 rounded animate-pulse" />
          ) : (
            <p className="text-sm font-mono font-semibold text-white truncate">{fmtUSD(account?.long_market_value)}</p>
          )}
          <p className="text-[10px] text-gray-700 mt-0.5">
            {account ? (parseFloat(account.long_market_value) > 0 ? 'long' : 'no exposure') : ''}
          </p>
        </div>

        {/* Cash */}
        <div className="pt-3 flex-1 flex flex-col justify-center">
          <p className="text-[10px] text-gray-600 mb-1">Cash</p>
          {loading ? (
            <div className="h-5 w-24 bg-gray-800 rounded animate-pulse" />
          ) : (
            <p className="text-sm font-mono font-semibold text-white truncate">{fmtUSD(account?.cash)}</p>
          )}
          <p className="text-[10px] text-gray-700 mt-0.5">available</p>
        </div>
      </div>
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
  const filled  = total === 0 ? 0 : pct >= 50 ? (wins / total) * ARC : (losses / total) * ARC

  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
      <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-1">Hit Ratio</p>
      <div className="flex flex-col items-center gap-2">
        <svg viewBox="0 0 100 60" className="w-full max-w-[130px] mx-auto">
          <path d="M 14 50 A 36 36 0 0 1 86 50" fill="none" stroke="#1f2937" strokeWidth="7" strokeLinecap="round" />
          <path
            d="M 14 50 A 36 36 0 0 1 86 50"
            fill="none"
            stroke={color}
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={`${filled} ${ARC - filled}`}
          />
          <text x="50" y="42" textAnchor="middle" fill={color} fontSize="14" fontWeight="700" fontFamily="ui-monospace,monospace">
            {total === 0 ? '—' : `${pct}%`}
          </text>
          <text x="50" y="54" textAnchor="middle" fill="#6b7280" fontSize="7.5" fontFamily="ui-monospace,monospace">
            {total > 0 ? `${total} trades` : ''}
          </text>
        </svg>
        <div className="grid grid-cols-3 gap-1 w-full text-center">
          <div>
            <p className="text-[10px] text-gray-600 uppercase">Wins</p>
            <p className="text-sm font-mono font-semibold text-emerald-400">{wins}</p>
          </div>
          <div>
            <p className="text-[10px] text-gray-600 uppercase">Losses</p>
            <p className="text-sm font-mono font-semibold text-red-400">{losses}</p>
          </div>
          <div>
            <p className="text-[10px] text-gray-600 uppercase">W/L</p>
            <p className="text-sm font-mono font-semibold text-white">{wl}</p>
          </div>
        </div>
      </div>
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
  const avg       = closed.length > 0 ? net / closed.length : null

  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
      <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-3">P&L ($)</p>

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
          Net {net >= 0 ? '+' : ''}{fmtUSD(net)}
        </span>
      </div>

    </div>
  )
}

function LivePositions({ alpacaState }: { alpacaState: AlpacaState | null }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 10_000)
    return () => clearInterval(id)
  }, [])

  const positions = alpacaState?.positions ?? []
  const syncAge   = alpacaState?.synced_at
    ? Math.floor((now - new Date(alpacaState.synced_at).getTime()) / 1000)
    : null
  const syncColor = syncAge == null ? 'text-gray-600'
    : syncAge < 120  ? 'text-emerald-500'
    : syncAge < 300  ? 'text-yellow-500'
    : 'text-red-500'
  const syncLabel = syncAge == null ? '—'
    : syncAge < 60   ? `${syncAge}s ago`
    : `${Math.floor(syncAge / 60)}m ago`

  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider">Live Positions</p>
        <span className={`text-[10px] font-mono ${syncColor}`}>● {syncLabel}</span>
      </div>

      {positions.length === 0 ? (
        <p className="text-xs text-gray-600">No open positions</p>
      ) : (
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-gray-600 border-b border-gray-800">
              <th className="text-left pb-1 font-normal">Symbol</th>
              <th className="text-right pb-1 font-normal">Qty</th>
              <th className="text-right pb-1 font-normal">Entry</th>
              <th className="text-right pb-1 font-normal">Precio</th>
              <th className="text-right pb-1 font-normal">P&L</th>
            </tr>
          </thead>
          <tbody>
            {positions.map(p => (
              <tr key={p.symbol} className="border-b border-gray-800/40">
                <td className="py-1 font-mono font-semibold text-white">{p.symbol}</td>
                <td className="py-1 text-right font-mono text-gray-400">{p.qty}</td>
                <td className="py-1 text-right font-mono text-gray-400">${p.avg_entry.toFixed(2)}</td>
                <td className="py-1 text-right font-mono text-white">${p.price.toFixed(2)}</td>
                <td className={`py-1 text-right font-mono font-semibold ${p.pl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {p.pl >= 0 ? '+' : ''}{fmtUSD(p.pl)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {alpacaState && (
        <div className="mt-3 pt-2 border-t border-gray-800 flex justify-between text-[10px] text-gray-600">
          <span>
            Day P&L:&nbsp;
            <span className={`font-mono ${(alpacaState.day_pl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {fmtUSD(alpacaState.day_pl)}
            </span>
          </span>
          <span>
            Unrealized:&nbsp;
            <span className="font-mono text-white">{fmtUSD(alpacaState.unrealized_pl)}</span>
          </span>
        </div>
      )}
    </div>
  )
}

function SystemPnL({ trades }: { trades: Trade[] }) {
  // Universo QQQ-only: agrupar por activo no informa nada — agrupamos por sistema
  const bySys: Record<string, { pnl: number; n: number; w: number }> = {}
  for (const t of trades) {
    if (t.pnl == null) continue
    const k = t.strategy ?? 'manual'
    bySys[k] ??= { pnl: 0, n: 0, w: 0 }
    bySys[k].pnl += t.pnl
    bySys[k].n   += 1
    if (t.pnl > 0) bySys[k].w += 1
  }
  const rows = Object.entries(bySys).sort(([, a], [, b]) => b.pnl - a.pnl).slice(0, 6)
  const max  = Math.max(...rows.map(([, v]) => Math.abs(v.pnl)), 1)

  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
      <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-3">P&L by System</p>
      {!rows.length ? (
        <p className="text-xs text-gray-600">No closed trades yet</p>
      ) : (
        <div className="space-y-2">
          {rows.map(([sys, v]) => (
            <div key={sys} className="flex items-center gap-2">
              <span className="text-xs font-mono text-white w-24 truncate shrink-0" title={sys}>{sys}</span>
              <span className="text-[10px] font-mono text-gray-600 w-9 shrink-0">{v.w}/{v.n}</span>
              <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${v.pnl >= 0 ? 'bg-emerald-500' : 'bg-red-500'}`}
                  style={{ width: `${(Math.abs(v.pnl) / max) * 100}%` }}
                />
              </div>
              <span className={`text-xs font-mono w-20 text-right shrink-0 ${v.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {v.pnl >= 0 ? '+' : ''}{fmtUSD(v.pnl)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function AccountSummary({ trades, alpacaState }: { trades: Trade[]; alpacaState?: AlpacaState | null }) {
  const [account, setAccount] = useState<AlpacaAccount | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/account')
      .then(r => r.json())
      .then(d => { setAccount(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const filled       = trades.filter(t => t.status === 'filled')
  const closedTrades = filled.filter(t => t.pnl != null)
  const avgPnL       = closedTrades.length > 0
    ? closedTrades.reduce((s, t) => s + (t.pnl ?? 0), 0) / closedTrades.length
    : 0

  return (
    <div className="space-y-3">
      {/* Niveles 1+2: Portfolio vertical (izquierda) + métricas 2×2 (derecha) */}
      <div className="flex flex-col sm:flex-row gap-3 sm:items-stretch">
        <div className="sm:w-48 sm:flex-shrink-0">
          <PortfolioCard account={account} loading={loading} />
        </div>
        <div className="flex-1 grid grid-cols-2 gap-3">
          <HitRatioGauge trades={trades} />
          <div className="flex flex-col gap-3">
            <DollarPnL trades={trades} />
            <StatCard
              label="Avg P&L"
              value={closedTrades.length > 0 ? `${avgPnL >= 0 ? '+' : ''}${fmtUSD(avgPnL)}` : '—'}
              sub={closedTrades.length > 0 ? `${closedTrades.length} closed trade${closedTrades.length !== 1 ? 's' : ''}` : 'no closed trades'}
              valueColor={closedTrades.length === 0 ? 'text-white' : avgPnL >= 0 ? 'text-emerald-400' : 'text-red-400'}
            />
          </div>
        </div>
      </div>

      {/* Nivel 3: P&L por sistema + Posiciones Live */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <SystemPnL trades={trades} />
        <LivePositions alpacaState={alpacaState ?? null} />
      </div>
    </div>
  )
}
