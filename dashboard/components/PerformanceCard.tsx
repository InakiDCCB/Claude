'use client'

import {
  ComposedChart, Bar, Cell, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import type { PnlPoint } from '@/lib/supabase'

const START_CAPITAL = 100_000

function fmtUSD(n: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(n)
}

function fmtDate(isoDay: string): string {
  return new Date(isoDay + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function signColor(n: number): string {
  return n > 0 ? 'text-emerald-400' : n < 0 ? 'text-red-400' : 'text-white'
}

function Kpi({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
      <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-1.5">{label}</p>
      <p className={`text-xl font-mono font-semibold truncate ${color ?? 'text-white'}`}>{value}</p>
      {sub && <p className="text-[11px] text-gray-600 mt-0.5 truncate">{sub}</p>}
    </div>
  )
}

export default function PerformanceCard({ pnlHistory }: { pnlHistory: PnlPoint[] }) {
  if (!pnlHistory.length) {
    return (
      <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
        <p className="text-xs text-gray-600">No closed trades yet</p>
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

  // Serie diaria + acumulada
  let cum = 0
  const data = days.map(([day, d]) => {
    cum += d.pnl
    return { date: fmtDate(day), pnl: Number(d.pnl.toFixed(2)), cum: Number(cum.toFixed(2)) }
  })

  const net    = cum
  const netPct = (net / START_CAPITAL) * 100

  const nowMonth = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' }).slice(0, 7)
  const mtd = days
    .filter(([day]) => day.startsWith(nowMonth))
    .reduce((a, [, d]) => a + d.pnl, 0)

  const [lastDay, lastStats] = days[days.length - 1]

  // Max drawdown peak-to-trough sobre la curva acumulada
  let peak = 0, maxDD = 0
  for (const d of data) {
    peak  = Math.max(peak, d.cum)
    maxDD = Math.max(maxDD, peak - d.cum)
  }

  const grossW    = days.reduce((a, [, d]) => a + Math.max(d.pnl, 0), 0)
  const grossL    = days.reduce((a, [, d]) => a + Math.max(-d.pnl, 0), 0)
  const pf        = grossL > 0 ? (grossW / grossL).toFixed(2) : grossW > 0 ? '∞' : '—'
  const greenDays = days.filter(([, d]) => d.pnl > 0).length
  const redDays   = days.filter(([, d]) => d.pnl < 0).length

  const recent = [...days].reverse().slice(0, 8)

  return (
    <div className="space-y-3">
      {/* KPIs de periodo */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <Kpi
          label="Net P&L"
          value={`${net >= 0 ? '+' : ''}${fmtUSD(net)}`}
          sub={`${netPct >= 0 ? '+' : ''}${netPct.toFixed(2)}% · ${days.length} sessions`}
          color={signColor(net)}
        />
        <Kpi
          label="MTD"
          value={`${mtd >= 0 ? '+' : ''}${fmtUSD(mtd)}`}
          sub={new Date().toLocaleDateString('en-US', { month: 'long' })}
          color={signColor(mtd)}
        />
        <Kpi
          label="Last Session"
          value={`${lastStats.pnl >= 0 ? '+' : ''}${fmtUSD(lastStats.pnl)}`}
          sub={fmtDate(lastDay)}
          color={signColor(lastStats.pnl)}
        />
        <Kpi
          label="Max Drawdown"
          value={maxDD > 0 ? `-${fmtUSD(maxDD)}` : '—'}
          sub="peak-to-trough"
          color={maxDD > 0 ? 'text-red-400' : 'text-white'}
        />
        <Kpi
          label="Profit Factor"
          value={pf}
          sub={`green/red days ${greenDays}/${redDays}`}
          color={grossL > 0 && grossW / grossL >= 1 ? 'text-emerald-400' : 'text-white'}
        />
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

        <div className="lg:w-80 bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
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
  )
}
