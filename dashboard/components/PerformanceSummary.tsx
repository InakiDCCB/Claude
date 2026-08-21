'use client'

import { useEffect, useState } from 'react'
import {
  ComposedChart, Bar, Cell, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import type { Trade, AlpacaState, PnlPoint } from '@/lib/supabase'

const START_CAPITAL = 100_000

type AlpacaAccount = {
  portfolio_value: string
  equity: string
  last_equity: string
  long_market_value: string
  cash: string
}

function fmtUSD(v: string | number | null | undefined): string {
  if (v == null || v === '') return '—'
  const n = typeof v === 'string' ? parseFloat(v) : v
  if (isNaN(n)) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(n)
}

function fmtDate(isoDay: string): string {
  return new Date(isoDay + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function signColor(n: number): string {
  return n > 0 ? 'text-emerald-400' : n < 0 ? 'text-red-400' : 'text-white'
}

// ─── Hero stat card ─────────────────────────────────────────────────────────

function Hero({ label, value, sub, color, loading }: {
  label: string; value: string; sub?: string; color?: string; loading?: boolean
}) {
  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
      <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-1.5">{label}</p>
      {loading ? (
        <div className="h-7 w-24 bg-gray-800 rounded animate-pulse" />
      ) : (
        <p className={`text-xl font-mono font-semibold truncate ${color ?? 'text-white'}`}>{value}</p>
      )}
      {sub && <p className="text-[11px] text-gray-600 mt-0.5 truncate">{sub}</p>}
    </div>
  )
}

// ─── Hit Ratio gauge (única representación de win/loss del dashboard) ───────

function HitRatioHero({ trades }: { trades: Trade[] }) {
  const closed = trades.filter(t => t.pnl != null)
  const wins   = closed.filter(t => (t.pnl ?? 0) > 0).length
  const losses = closed.filter(t => (t.pnl ?? 0) < 0).length
  const total  = wins + losses
  const pct    = total > 0 ? Math.round(wins / total * 100) : 0
  const color  = total === 0 ? '#374151' : pct >= 50 ? '#34d399' : '#f87171'
  const ARC    = Math.PI * 36
  const filled = total === 0 ? 0 : pct >= 50 ? (wins / total) * ARC : (losses / total) * ARC

  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
      <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-1">Hit Ratio</p>
      <div className="flex items-center gap-3">
        <svg viewBox="0 0 100 60" className="w-20 shrink-0">
          <path d="M 14 50 A 36 36 0 0 1 86 50" fill="none" stroke="#1f2937" strokeWidth="7" strokeLinecap="round" />
          <path d="M 14 50 A 36 36 0 0 1 86 50" fill="none" stroke={color} strokeWidth="7" strokeLinecap="round"
            strokeDasharray={`${filled} ${ARC - filled}`} />
          <text x="50" y="42" textAnchor="middle" fill={color} fontSize="15" fontWeight="700" fontFamily="ui-monospace,monospace">
            {total === 0 ? '—' : `${pct}%`}
          </text>
        </svg>
        <div className="text-[11px] font-mono text-gray-500 leading-relaxed">
          <p><span className="text-emerald-400">{wins}</span> wins</p>
          <p><span className="text-red-400">{losses}</span> losses</p>
        </div>
      </div>
    </div>
  )
}

// ─── Live positions (broker state, no derived P&L) ──────────────────────────

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
        <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider">Live Positions (broker)</p>
        <span suppressHydrationWarning className={`text-[10px] font-mono ${syncColor}`}>● synced {syncLabel}</span>
      </div>

      {positions.length === 0 ? (
        <p className="text-xs text-gray-600">Flat — no open positions</p>
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

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function PerformanceSummary({ trades, alpacaState, pnlHistory }: {
  trades:      Trade[]
  alpacaState: AlpacaState | null
  pnlHistory:  PnlPoint[]
}) {
  const [account, setAccount] = useState<AlpacaAccount | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/account')
      .then(r => r.json())
      .then(d => { setAccount(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const portDelta    = account ? parseFloat(account.equity) - parseFloat(account.last_equity) : null
  const portDeltaPct = portDelta != null && account && parseFloat(account.last_equity) > 0
    ? (portDelta / parseFloat(account.last_equity)) * 100 : null

  if (!pnlHistory.length) {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Hero label="Portfolio" value={fmtUSD(account?.portfolio_value)} loading={loading} />
          <Hero label="Cash" value={fmtUSD(account?.cash)} loading={loading} />
          <Hero label="Net P&L" value="—" />
          <HitRatioHero trades={trades} />
        </div>
        <p className="text-xs text-gray-600">No closed trades yet.</p>
      </div>
    )
  }

  // Agregación por día de sesión ET desde trades (fuente reconciliada con el broker)
  const byDay = new Map<string, { pnl: number; n: number; w: number }>()
  for (const r of pnlHistory) {
    const day = new Date(r.created_at).toLocaleDateString('en-CA', { timeZone: 'America/New_York' })
    const d = byDay.get(day) ?? { pnl: 0, n: 0, w: 0 }
    d.pnl += Number(r.pnl)
    d.n   += 1
    if (Number(r.pnl) > 0) d.w += 1
    byDay.set(day, d)
  }
  const days = [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b))

  let cum = 0
  const data = days.map(([day, d]) => {
    cum += d.pnl
    return { date: fmtDate(day), pnl: Number(d.pnl.toFixed(2)), cum: Number(cum.toFixed(2)) }
  })

  const net    = cum
  const netPct = (net / START_CAPITAL) * 100

  const nowMonth = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' }).slice(0, 7)
  const mtd = days.filter(([day]) => day.startsWith(nowMonth)).reduce((a, [, d]) => a + d.pnl, 0)

  let peak = 0, maxDD = 0
  for (const d of data) { peak = Math.max(peak, d.cum); maxDD = Math.max(maxDD, peak - d.cum) }

  const grossW    = days.reduce((a, [, d]) => a + Math.max(d.pnl, 0), 0)
  const grossL    = days.reduce((a, [, d]) => a + Math.max(-d.pnl, 0), 0)
  const pf        = grossL > 0 ? (grossW / grossL).toFixed(2) : grossW > 0 ? '∞' : '—'
  const greenDays = days.filter(([, d]) => d.pnl > 0).length
  const redDays   = days.filter(([, d]) => d.pnl < 0).length
  const recent    = [...days].reverse().slice(0, 8)

  const closedTrades = trades.filter(t => t.status === 'filled' && t.pnl != null)
  const avgPnL = closedTrades.length > 0
    ? closedTrades.reduce((s, t) => s + (t.pnl ?? 0), 0) / closedTrades.length : 0

  return (
    <div className="space-y-3">
      {/* Fila única: estado de cuenta + veredicto de performance. Todo lo demás del dashboard
          referencia estos números — no se repiten en ningún otro card. */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <Hero label="Portfolio" value={fmtUSD(account?.portfolio_value)} loading={loading}
          color={portDelta == null ? undefined : signColor(portDelta)}
          sub={portDeltaPct != null ? `${portDeltaPct >= 0 ? '▲' : '▼'} ${portDeltaPct >= 0 ? '+' : ''}${portDeltaPct.toFixed(2)}% vs yesterday` : undefined} />
        <Hero label="Cash" value={fmtUSD(account?.cash)} loading={loading} />
        <Hero label="Net P&L" value={`${net >= 0 ? '+' : ''}${fmtUSD(net)}`} color={signColor(net)}
          sub={`${netPct >= 0 ? '+' : ''}${netPct.toFixed(2)}% · ${days.length} sesiones · avg ${avgPnL >= 0 ? '+' : ''}${fmtUSD(avgPnL)}/trade`} />
        <Hero label="MTD" value={`${mtd >= 0 ? '+' : ''}${fmtUSD(mtd)}`} color={signColor(mtd)}
          sub={new Date().toLocaleDateString('en-US', { month: 'long' })} />
        <HitRatioHero trades={trades} />
        <Hero label="Profit Factor" value={pf} sub={`DD -${fmtUSD(maxDD)} · ${greenDays}/${redDays} verde/rojo`}
          color={grossL > 0 && grossW / grossL >= 1 ? 'text-emerald-400' : 'text-white'} />
      </div>

      {/* Curva acumulada + P&L diario · sesiones recientes */}
      <div className="flex flex-col lg:flex-row gap-3">
        <div className="flex-1 bg-gray-900/30 border border-gray-800/60 rounded-xl p-4" style={{ minHeight: 260 }}>
          <div className="flex items-center justify-between mb-2">
            <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider">
              Realized P&L by Session
            </p>
            <p className="text-[10px] text-gray-700">source: trades (broker-reconciled)</p>
          </div>
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <ReferenceLine y={0} stroke="#374151" strokeDasharray="4 4" />
                <XAxis dataKey="date" tick={{ fill: '#4b5563', fontSize: 11 }} tickLine={false} />
                <YAxis
                  tick={{ fill: '#4b5563', fontSize: 11 }}
                  tickFormatter={v => `$${v}`}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: '8px', fontSize: 13 }}
                  labelStyle={{ color: '#9ca3af', marginBottom: 4 }}
                  formatter={(v: number, name: string) =>
                    [`${v >= 0 ? '+' : ''}$${v.toFixed(2)}`, name === 'pnl' ? 'Day P&L' : 'Cumulative']}
                />
                <Bar dataKey="pnl" barSize={14} radius={[3, 3, 0, 0]}>
                  {data.map((d, i) => (
                    <Cell key={i} fill={d.pnl >= 0 ? '#10b981' : '#ef4444'} fillOpacity={0.85} />
                  ))}
                </Bar>
                <Line
                  type="monotone" dataKey="cum" stroke="#38bdf8" strokeWidth={2.5}
                  dot={false} activeDot={{ r: 5 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="lg:w-80 flex flex-col gap-3">
          <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
            <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-3">
              Recent Sessions
            </p>
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-gray-600 border-b border-gray-800">
                  <th className="text-left pb-1 font-normal">Date</th>
                  <th className="text-right pb-1 font-normal">Trades</th>
                  <th className="text-right pb-1 font-normal">Hit</th>
                  <th className="text-right pb-1 font-normal">P&L</th>
                </tr>
              </thead>
              <tbody>
                {recent.map(([day, d]) => (
                  <tr key={day} className="border-b border-gray-800/40">
                    <td className="py-1.5 font-mono text-gray-400">{fmtDate(day)}</td>
                    <td className="py-1.5 text-right font-mono text-gray-400">{d.n}</td>
                    <td className="py-1.5 text-right font-mono text-gray-400">
                      {d.n > 0 ? `${Math.round((d.w / d.n) * 100)}%` : '—'}
                    </td>
                    <td className={`py-1.5 text-right font-mono font-semibold ${d.pnl > 0 ? 'text-emerald-400' : d.pnl < 0 ? 'text-red-400' : 'text-gray-500'}`}>
                      {`${d.pnl >= 0 ? '+' : ''}${fmtUSD(d.pnl)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <LivePositions alpacaState={alpacaState} />
    </div>
  )
}
