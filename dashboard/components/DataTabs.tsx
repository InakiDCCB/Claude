'use client'

import { useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import type { Trade, AnalysisEntry } from '@/lib/supabase'

// ─── CSV helpers ─────────────────────────────────────────────────────────────

function toCSV(headers: string[], rows: (string | number | null | undefined)[][]): string {
  const escape = (v: string | number | null | undefined) =>
    `"${String(v ?? '').replace(/"/g, '""')}"`
  return [headers.map(escape).join(','), ...rows.map(r => r.map(escape).join(','))].join('\n')
}

function downloadCSV(filename: string, csv: string) {
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
  const url  = URL.createObjectURL(blob)
  const a    = Object.assign(document.createElement('a'), { href: url, download: filename })
  a.click()
  URL.revokeObjectURL(url)
}

function etTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-US', {
    timeZone: 'America/New_York',
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

// ─── Shared UI ────────────────────────────────────────────────────────────────

function TabBtn({ label, active, count, onClick }: {
  label: string; active: boolean; count: number; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
        active ? 'bg-gray-800 text-white' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-900'
      }`}
    >
      {label}
      <span className={`text-xs px-1.5 py-0.5 rounded font-normal ${
        active ? 'bg-gray-700 text-gray-300' : 'bg-gray-900 text-gray-600'
      }`}>
        {count}
      </span>
    </button>
  )
}

function ExportBtn({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-gray-900 border border-gray-800 text-gray-400 hover:text-gray-200 hover:border-gray-700 transition-colors"
    >
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      Exportar CSV
    </button>
  )
}

function Empty({ text }: { text: string }) {
  return (
    <div className="py-20 text-center text-gray-600 text-sm">
      <p className="text-2xl mb-3">📭</p>
      {text}
    </div>
  )
}

function TableWrap({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800/60">
      <table className="w-full text-sm">{children}</table>
    </div>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-3 py-3 text-left text-[10px] font-semibold text-gray-500 uppercase tracking-wider bg-gray-900/80 first:rounded-tl-xl last:rounded-tr-xl whitespace-nowrap">
      {children}
    </th>
  )
}

function Td({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <td className={`px-3 py-2.5 ${className}`}>{children}</td>
}

function Row({ children, odd }: { children: React.ReactNode; odd: boolean }) {
  return (
    <tr className={`border-b border-gray-800/40 hover:bg-gray-800/20 transition-colors ${odd ? 'bg-gray-900/10' : ''}`}>
      {children}
    </tr>
  )
}

// ─── Trades ──────────────────────────────────────────────────────────────────

function resolveExitPrice(t: Trade): number | null {
  if (t.exit_price != null) return t.exit_price
  if (t.pnl != null)        return t.price + t.pnl
  return null
}

const SIDE_COLORS: Record<string, string> = {
  buy:  'bg-emerald-500/10 text-emerald-400',
  sell: 'bg-red-500/10 text-red-400',
}

const STRATEGY_COLORS: Record<string, string> = {
  'TOB-V2':    'bg-violet-500/10 text-violet-400',
  'TOB-V2 Pipeline': 'bg-violet-500/10 text-violet-400',
}

function TradesTable({ trades }: { trades: Trade[] }) {
  if (!trades.length) return <Empty text="No hay trades en este período." />

  function exportCSV() {
    downloadCSV('trades.csv', toCSV(
      ['ID', 'Fecha', 'Hora ET', 'Ticker', 'Lado', 'Cantidad', 'P. Entrada', 'P. Salida', 'Notional', 'P&L', 'Estrategia', 'Estado'],
      trades.map(t => {
        const exit = resolveExitPrice(t)
        return [
          `T-${t.id.slice(0, 6).toUpperCase()}`,
          t.created_at.split('T')[0],
          etTime(t.filled_at ?? t.created_at),
          t.asset,
          t.side,
          t.quantity,
          t.price,
          exit,
          t.total_value ?? t.quantity * t.price,
          t.pnl,
          t.strategy,
          t.status,
        ]
      })
    ))
  }

  return (
    <div>
      <div className="flex justify-end mb-3"><ExportBtn onClick={exportCSV} /></div>
      <TableWrap>
        <thead>
          <tr>
            {['ID', 'Hora ET', 'Ticker', 'Lado', 'Cant.', 'P. Entrada', 'P. Salida', 'Notional', 'P&L', 'Estrategia', 'Estado'].map(h => (
              <Th key={h}>{h}</Th>
            ))}
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => {
            const exitPrice = resolveExitPrice(t)
            const notional  = t.total_value ?? t.quantity * t.price
            return (
              <Row key={t.id} odd={i % 2 === 1}>
                <Td className="font-mono text-[11px] text-gray-600 whitespace-nowrap">
                  T-{t.id.slice(0, 6).toUpperCase()}
                </Td>
                <Td className="font-mono text-xs text-gray-500 whitespace-nowrap">
                  {etTime(t.filled_at ?? t.created_at)}
                </Td>
                <Td className="font-semibold text-white">{t.asset}</Td>
                <Td>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold uppercase ${
                    SIDE_COLORS[t.side] ?? 'bg-gray-700 text-gray-400'
                  }`}>
                    {t.side}
                  </span>
                </Td>
                <Td className="font-mono text-gray-300 text-xs">{t.quantity}</Td>
                <Td className="font-mono text-gray-300 text-xs">${t.price.toFixed(2)}</Td>
                <Td className="font-mono text-gray-300 text-xs">
                  {exitPrice != null ? `$${exitPrice.toFixed(2)}` : '—'}
                </Td>
                <Td className="font-mono text-gray-400 text-xs">${notional.toFixed(2)}</Td>
                <Td className={`font-mono font-semibold text-xs ${
                  t.pnl == null ? 'text-gray-600'
                  : t.pnl > 0   ? 'text-emerald-400'
                  : t.pnl < 0   ? 'text-red-400'
                  : 'text-gray-400'
                }`}>
                  {t.pnl != null ? `${t.pnl > 0 ? '+' : ''}$${t.pnl.toFixed(2)}` : '—'}
                </Td>
                <Td>
                  {t.strategy ? (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                      STRATEGY_COLORS[t.strategy] ?? 'bg-gray-700/60 text-gray-400'
                    }`}>
                      {t.strategy}
                    </span>
                  ) : <span className="text-gray-600 text-xs">—</span>}
                </Td>
                <Td>
                  <span className={`flex items-center gap-1.5 text-xs whitespace-nowrap ${
                    t.status === 'filled'     ? 'text-emerald-400'
                    : t.status === 'cancelled' ? 'text-gray-500'
                    : 'text-amber-400'
                  }`}>
                    <span className={`w-1.5 h-1.5 rounded-full inline-block flex-shrink-0 ${
                      t.status === 'filled'     ? 'bg-emerald-400'
                      : t.status === 'cancelled' ? 'bg-gray-600'
                      : 'bg-amber-400'
                    }`} />
                    {t.status}
                  </span>
                </Td>
              </Row>
            )
          })}
        </tbody>
      </TableWrap>
    </div>
  )
}

// ─── P&L Chart ────────────────────────────────────────────────────────────────

function PnLChart({ trades }: { trades: Trade[] }) {
  const filled = trades
    .filter(t => t.pnl != null)
    .sort((a, b) => a.created_at.localeCompare(b.created_at))

  if (!filled.length) return <Empty text="No hay trades con P&L en este período." />

  let cum = 0
  const data = filled.map(t => {
    cum += t.pnl!
    return { date: t.created_at.split('T')[0], pnl: parseFloat(cum.toFixed(2)) }
  })

  const totalPnL   = data.at(-1)?.pnl ?? 0
  const isPositive = totalPnL >= 0
  const wins       = filled.filter(t => (t.pnl ?? 0) > 0).length
  const losses     = filled.filter(t => (t.pnl ?? 0) < 0).length
  const hr         = filled.length ? Math.round(wins / filled.length * 100) : 0
  const color      = isPositive ? '#34d399' : '#f87171'

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'P&L Total',     value: `${isPositive ? '+' : ''}$${totalPnL.toFixed(2)}`, color: isPositive ? 'text-emerald-400' : 'text-red-400' },
          { label: 'Trades',        value: String(filled.length), color: 'text-white' },
          { label: 'Win Rate',      value: `${hr}%`, color: hr >= 50 ? 'text-emerald-400' : 'text-red-400' },
          { label: 'Wins / Losses', value: `${wins} / ${losses}`, color: 'text-white' },
        ].map(s => (
          <div key={s.label} className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4">
            <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">{s.label}</p>
            <p className={`text-xl font-mono font-semibold ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      <div className="bg-gray-900/30 border border-gray-800/60 rounded-xl p-4" style={{ height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
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
              formatter={(v: number) => [`$${v.toFixed(2)}`, 'P&L acum.']}
            />
            <Line
              type="monotone" dataKey="pnl" stroke={color} strokeWidth={2.5}
              dot={{ fill: color, r: 4, strokeWidth: 0 }} activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// ─── Analysis Log ─────────────────────────────────────────────────────────────

const SIGNAL_COLORS: Record<string, string> = {
  bullish:  'bg-emerald-500/10 text-emerald-400',
  bearish:  'bg-red-500/10 text-red-400',
  neutral:  'bg-gray-700 text-gray-300',
  watching: 'bg-amber-500/10 text-amber-400',
}

function AnalysisLog({ entries }: { entries: AnalysisEntry[] }) {
  if (!entries.length) return <Empty text="No hay entradas de análisis en este período." />

  function exportCSV() {
    downloadCSV('analysis_log.csv', toCSV(
      ['Fecha', 'Asset', 'Timeframe', 'Señal', 'Confianza', 'Tesis', 'Outcome', 'Tags'],
      entries.map(e => [
        e.created_at, e.asset, e.timeframe, e.signal,
        e.confidence, e.thesis, e.outcome, (e.tags ?? []).join('; '),
      ])
    ))
  }

  return (
    <div>
      <div className="flex justify-end mb-3"><ExportBtn onClick={exportCSV} /></div>
      <TableWrap>
        <thead>
          <tr>
            {['Fecha', 'Asset', 'TF', 'Señal', 'Conf.', 'Tesis', 'Outcome'].map(h => (
              <Th key={h}>{h}</Th>
            ))}
          </tr>
        </thead>
        <tbody>
          {entries.map((e, i) => (
            <Row key={e.id} odd={i % 2 === 1}>
              <Td className="text-gray-500 font-mono text-xs whitespace-nowrap">{e.created_at.split('T')[0]}</Td>
              <Td className="font-semibold text-white">{e.asset}</Td>
              <Td className="text-gray-500 text-xs">{e.timeframe ?? '—'}</Td>
              <Td>
                {e.signal
                  ? <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SIGNAL_COLORS[e.signal] ?? 'bg-gray-700 text-gray-300'}`}>{e.signal}</span>
                  : <span className="text-gray-600">—</span>
                }
              </Td>
              <Td className="font-mono text-gray-300 text-xs">{e.confidence != null ? `${e.confidence}%` : '—'}</Td>
              <Td className="text-gray-400 text-xs max-w-xs">
                <span className="line-clamp-2" title={e.thesis ?? ''}>{e.thesis ?? '—'}</span>
              </Td>
              <Td className="text-gray-500 text-xs whitespace-nowrap">{e.outcome ?? '—'}</Td>
            </Row>
          ))}
        </tbody>
      </TableWrap>
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────

type TabId = 'trades' | 'pnl' | 'analysis'

export default function DataTabs({ trades, analysis }: {
  trades: Trade[]
  analysis: AnalysisEntry[]
}) {
  const [tab, setTab] = useState<TabId>('trades')

  const tabs: { id: TabId; label: string; count: number }[] = [
    { id: 'trades',   label: 'Trades',       count: trades.length },
    { id: 'pnl',      label: 'P&L',          count: trades.filter(t => t.pnl != null).length },
    { id: 'analysis', label: 'Analysis Log', count: analysis.length },
  ]

  return (
    <div>
      <div className="flex items-center gap-1 mb-5 border-b border-gray-800 pb-1">
        <div className="flex items-center gap-1 flex-1">
          {tabs.map(t => (
            <TabBtn key={t.id} label={t.label} active={tab === t.id} count={t.count} onClick={() => setTab(t.id)} />
          ))}
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-gray-600 pr-1">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse inline-block" />
          stream en vivo
        </div>
      </div>

      {tab === 'trades'   && <TradesTable trades={trades} />}
      {tab === 'pnl'      && <PnLChart trades={trades} />}
      {tab === 'analysis' && <AnalysisLog entries={analysis} />}
    </div>
  )
}
