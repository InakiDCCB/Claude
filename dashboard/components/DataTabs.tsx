'use client'

import { Fragment, useMemo, useState } from 'react'
import type { Trade } from '@/lib/supabase'

// ─── CSV helpers ─────────────────────────────────────────────────────────────

function toCSV(headers: string[], rows: (string | number | null | undefined)[][]): string {
  const escape = (v: string | number | null | undefined) => `"${String(v ?? '').replace(/"/g, '""')}"`
  return [headers.map(escape).join(','), ...rows.map(r => r.map(escape).join(','))].join('\n')
}
function downloadCSV(filename: string, csv: string) {
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
  const url  = URL.createObjectURL(blob)
  const a    = Object.assign(document.createElement('a'), { href: url, download: filename })
  a.click()
  URL.revokeObjectURL(url)
}
function etDateTime(iso: string): string {
  const d = new Date(iso)
  const date = d.toLocaleDateString('en-CA', { timeZone: 'America/New_York' })
  const time = d.toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  return `${date} ${time}`
}
function resolveExitPrice(t: Trade): number | null {
  if (t.exit_price != null) return t.exit_price
  if (t.pnl != null) return t.price + t.pnl
  return null
}
function holdLabel(t: Trade): string {
  if (!t.filled_at) return '—'
  const start = new Date(t.filled_at).getTime()
  const end   = Date.now()
  const mins  = Math.max(0, Math.round((end - start) / 60000))
  return mins < 60 ? `${mins}m` : `${Math.floor(mins / 60)}h ${mins % 60}m`
}

const EXIT_STYLE: Record<string, { bg: string; fg: string }> = {
  TP:   { bg: 'var(--green-bg)', fg: 'var(--green-dim)' },
  SL:   { bg: 'var(--red-bg)',   fg: 'var(--red)' },
  TIME: { bg: 'var(--amber-bg)', fg: 'var(--amber)' },
}

// ─── Calendario NYSE ─────────────────────────────────────────────────────────

type CalEvent = { date: string; label: string; type: 'holiday' | 'early_close'; closeTime?: string }
const NYSE_2026: CalEvent[] = [
  { date: '2026-01-01', label: "New Year's Day", type: 'holiday' },
  { date: '2026-01-19', label: 'Martin Luther King Jr. Day', type: 'holiday' },
  { date: '2026-02-16', label: "Presidents' Day", type: 'holiday' },
  { date: '2026-04-03', label: 'Good Friday', type: 'holiday' },
  { date: '2026-05-25', label: 'Memorial Day', type: 'holiday' },
  { date: '2026-06-19', label: 'Juneteenth', type: 'holiday' },
  { date: '2026-07-03', label: 'Independence Day (obs.)', type: 'holiday' },
  { date: '2026-09-07', label: 'Labor Day', type: 'holiday' },
  { date: '2026-11-26', label: 'Thanksgiving Day', type: 'holiday' },
  { date: '2026-11-27', label: 'Day after Thanksgiving', type: 'early_close', closeTime: '13:00 ET' },
  { date: '2026-12-24', label: 'Christmas Eve', type: 'early_close', closeTime: '13:00 ET' },
  { date: '2026-12-25', label: 'Christmas Day', type: 'holiday' },
]

function CalendarSidebar() {
  const today = new Date().toISOString().slice(0, 10)
  const upcoming = NYSE_2026.filter(e => e.date >= today).slice(0, 5)
  return (
    <div className="bg-[var(--surface-1)] border border-[var(--border)] rounded-lg p-4">
      <div className="flex items-center justify-between mb-3.5">
        <span className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-4)]">Calendario NYSE</span>
        <span className="font-mono text-[9px] tracking-wide text-[var(--text-5)]">2026</span>
      </div>
      <div className="flex flex-col gap-0.5">
        {upcoming.map(e => {
          const days = Math.round((new Date(e.date + 'T12:00:00Z').getTime() - Date.now()) / 86400000)
          return (
            <div key={e.date} className="p-2.5 rounded-md bg-[var(--surface-2)] flex flex-col gap-1">
              <div className="flex items-baseline justify-between gap-2.5">
                <span className="font-mono text-[11px] tabular-nums text-[var(--text-1)]">
                  {new Date(e.date + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })}
                </span>
                <span className="font-mono text-[9px] tracking-wide px-1.5 py-0.5 rounded"
                  style={{ background: e.type === 'holiday' ? 'var(--red-bg)' : 'var(--amber-bg)', color: e.type === 'holiday' ? 'var(--red)' : 'var(--amber)' }}>
                  {e.type === 'holiday' ? 'CERRADO' : e.closeTime}
                </span>
              </div>
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[11px] text-[var(--text-2)]">{e.label}</span>
                <span className="font-mono text-[9px] text-[var(--text-5)] whitespace-nowrap">{days === 0 ? 'hoy' : `en ${days}d`}</span>
              </div>
            </div>
          )
        })}
        {upcoming.length === 0 && <p className="text-[11px] text-[var(--text-5)]">Sin feriados próximos.</p>}
      </div>
      <div className="mt-3 pt-2.5 border-t border-[var(--border-soft)] font-mono text-[10px] leading-relaxed text-[var(--text-5)]">
        early close = 13:00 ET · el loop debería pausar gates después de 12:30 en esas sesiones
      </div>
    </div>
  )
}

// ─── Trades table ────────────────────────────────────────────────────────────

const COLS = 'grid-cols-[148px_repeat(8,minmax(0,1fr))]'

function TradesTable({ trades, newTradeId, rangeCount }: { trades: Trade[]; newTradeId?: string | null; rangeCount: string }) {
  const [open, setOpen] = useState<string | null>(null)

  function exportCSV() {
    downloadCSV('trades.csv', toCSV(
      ['ID', 'Date', 'Time ET', 'Ticker', 'Side', 'Qty', 'Entry Price', 'Exit Price', 'Notional', 'P&L', 'Strategy', 'Status'],
      trades.map(t => [
        `T-${t.order_id?.split('-')[0] ?? t.id.slice(0, 8)}`, t.created_at.split('T')[0], etDateTime(t.filled_at ?? t.created_at),
        t.asset, t.side, t.quantity, t.price, resolveExitPrice(t), t.total_value ?? t.quantity * t.price, t.pnl, t.strategy, t.status,
      ])
    ))
  }

  return (
    <div className="bg-[var(--surface-1)] border border-[var(--border)] rounded-lg overflow-hidden">
      <div className="flex items-center justify-between gap-2 px-3 py-1.5 border-b border-[var(--border-soft)]">
        <span className="font-mono text-[10px] text-[var(--text-5)]">{rangeCount}</span>
        <button onClick={exportCSV}
          className="font-mono text-[10px] tracking-wide px-2.5 py-1 border border-[var(--border)] rounded cursor-pointer text-[var(--text-2)] hover:bg-[var(--surface-hover)] hover:border-[var(--text-4)] transition-colors">
          EXPORT CSV
        </button>
      </div>

      {trades.length === 0 ? (
        <p className="text-sm text-[var(--text-5)] py-12 text-center">Sin trades en este rango.</p>
      ) : (
        <div className="overflow-x-auto">
          <div className="min-w-[900px]">
            <div className={`grid ${COLS} gap-3.5 px-4 py-2 bg-[var(--surface-1-alt)] border-b border-[var(--border)] font-mono text-[9px] tracking-widest uppercase text-[var(--text-5)]`}>
              <span>fecha et</span><span>side</span><span className="text-right">qty</span><span className="text-right">entry</span>
              <span className="text-right">exit</span><span className="text-right">total</span><span className="text-center">salida</span>
              <span className="text-right">p&amp;l</span><span className="text-right">estrategia</span>
            </div>
            {trades.map(t => {
              const exitPrice = resolveExitPrice(t)
              const notional  = t.total_value ?? t.quantity * t.price
              const isOpen    = open === t.id
              const exitStyle = t.exit_type ? EXIT_STYLE[t.exit_type] : null
              return (
                <Fragment key={t.id}>
                  <div onClick={() => setOpen(isOpen ? null : t.id)}
                    className={`grid ${COLS} gap-3.5 items-center border-b border-[var(--border-faint)] cursor-pointer font-mono text-[11px] tabular-nums px-4 py-2 hover:bg-[var(--surface-hover)] transition-colors`}
                    style={{ background: t.id === newTradeId ? undefined : isOpen ? 'var(--surface-3)' : 'transparent' }}>
                    <span className={t.id === newTradeId ? 'animate-row-flash' : ''} style={{ color: 'var(--text-2)' }}>{etDateTime(t.filled_at ?? t.created_at)}</span>
                    <span style={{ color: 'var(--text-4)' }}>{t.side}</span>
                    <span className="text-right" style={{ color: 'var(--text-3)' }}>{t.quantity}</span>
                    <span className="text-right" style={{ color: 'var(--text-1)' }}>${t.price.toFixed(2)}</span>
                    <span className="text-right" style={{ color: 'var(--text-1)' }}>{exitPrice != null ? `$${exitPrice.toFixed(2)}` : '—'}</span>
                    <span className="text-right" style={{ color: 'var(--text-4)' }}>${notional.toFixed(2)}</span>
                    <span className="text-center">
                      {t.exit_type ? (
                        <span className="inline-block min-w-[40px] py-0.5 rounded font-semibold text-[9px] tracking-wide"
                          style={{ background: exitStyle!.bg, color: exitStyle!.fg }}>{t.exit_type}</span>
                      ) : <span style={{ color: 'var(--text-5)' }}>—</span>}
                    </span>
                    <span className="text-right font-semibold" style={{ color: t.pnl == null ? 'var(--text-5)' : t.pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
                      {t.pnl != null ? `${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}` : 'open'}
                    </span>
                    <span className="text-right text-[10px]" style={{ color: 'var(--text-3)' }}>{t.strategy ?? '—'}</span>
                  </div>
                  {isOpen && (
                    <div className="pt-3.5 pb-4 pl-[166px] pr-4 bg-[var(--surface-3)] border-b border-[var(--border)] flex gap-8">
                      <div>
                        <div className="font-mono text-[9px] tracking-widest uppercase text-[var(--text-5)] mb-1">hold</div>
                        <div className="font-mono text-xs text-[var(--text-1)]">{t.pnl == null ? holdLabel(t) : '—'}</div>
                      </div>
                      <div>
                        <div className="font-mono text-[9px] tracking-widest uppercase text-[var(--text-5)] mb-1">notional</div>
                        <div className="font-mono text-xs text-[var(--text-1)]">${notional.toFixed(2)}</div>
                      </div>
                      <div>
                        <div className="font-mono text-[9px] tracking-widest uppercase text-[var(--text-5)] mb-1">status</div>
                        <div className="font-mono text-xs" style={{ color: t.status === 'filled' ? 'var(--green-dim)' : 'var(--text-2)' }}>{t.status}</div>
                      </div>
                      <div className="flex-1">
                        <div className="font-mono text-[9px] tracking-widest uppercase text-[var(--text-5)] mb-1">notas</div>
                        <div className="text-xs leading-relaxed text-[var(--text-2)]">{t.notes ?? 'sin notas'}</div>
                      </div>
                    </div>
                  )}
                </Fragment>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────

const RANGE_DAYS: Record<string, number> = { '7d': 7, '30d': 30, '90d': 90, todo: 1e6 }

export default function DataTabs({ trades, newTradeId }: { trades: Trade[]; newTradeId?: string | null }) {
  const [range, setRange]       = useState<'7d' | '30d' | '90d' | 'todo'>('30d')
  const [strategy, setStrategy] = useState<string>('all')

  const rangeTrades = useMemo(() => {
    const cutoff = Date.now() - RANGE_DAYS[range] * 86400000
    return trades.filter(t => new Date(t.filled_at ?? t.created_at).getTime() >= cutoff)
  }, [trades, range])

  const strategies = useMemo(() => {
    const groups = new Map<string, number>()
    for (const t of rangeTrades) {
      const k = t.strategy ?? '—'
      groups.set(k, (groups.get(k) ?? 0) + (t.pnl ?? 0))
    }
    return [...groups.entries()].sort((a, b) => b[1] - a[1])
  }, [rangeTrades])

  const filteredTrades = useMemo(
    () => strategy === 'all' ? rangeTrades : rangeTrades.filter(t => (t.strategy ?? '—') === strategy),
    [rangeTrades, strategy]
  )

  return (
    <div>
      <div className="flex items-center gap-3 mb-2.5">
        <span className="font-mono text-[10px] font-semibold tracking-[0.16em] uppercase text-[var(--text-3)]">Trades</span>
        <span className="h-px flex-1 bg-[var(--border-soft)]" />
        <div className="flex items-center gap-1">
          {(['7d', '30d', '90d', 'todo'] as const).map(r => (
            <span key={r} onClick={() => setRange(r)}
              className="font-mono text-[10px] tracking-wide px-2.5 py-1 rounded cursor-pointer transition-colors"
              style={{ background: range === r ? 'var(--surface-chip-active)' : 'var(--surface-chip)', color: range === r ? 'var(--cyan)' : 'var(--text-3)' }}>
              {r}
            </span>
          ))}
          <span className="font-mono text-[10px] text-[var(--text-5)] ml-2 whitespace-nowrap">{filteredTrades.length} de {trades.length} trades</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[236px_1fr] gap-4 items-start">
        <CalendarSidebar />

        <div>
          <div className="flex flex-wrap items-center gap-1 mb-2">
            <span onClick={() => setStrategy('all')}
              className="font-mono text-[10px] px-2.5 py-1 rounded cursor-pointer transition-colors"
              style={{ background: strategy === 'all' ? 'var(--surface-chip-active)' : 'var(--surface-chip)', color: strategy === 'all' ? 'var(--cyan)' : 'var(--text-2)' }}>
              todas
            </span>
            {strategies.map(([name, pnl]) => (
              <span key={name} onClick={() => setStrategy(name)}
                className="inline-flex items-baseline gap-1.5 font-mono text-[10px] px-2.5 py-1 rounded cursor-pointer transition-colors"
                style={{ background: strategy === name ? 'var(--surface-chip-active)' : 'var(--surface-chip)' }}>
                <span style={{ color: 'var(--text-2)' }}>{name}</span>
                <span className="text-[9px] tabular-nums" style={{ color: pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>{pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</span>
              </span>
            ))}
          </div>
          <TradesTable trades={filteredTrades} newTradeId={newTradeId} rangeCount={`${filteredTrades.length} de ${rangeTrades.length} trades`} />
        </div>
      </div>
    </div>
  )
}
