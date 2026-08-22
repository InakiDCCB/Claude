'use client'

import { useEffect, useState } from 'react'
import type { SessionStateRow, AlpacaState } from '@/lib/supabase'

function getET(): Date {
  return new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' }))
}

function isMarketOpen(): boolean {
  const et = getET()
  const day = et.getDay()
  if (day === 0 || day === 6) return false
  const mins = et.getHours() * 60 + et.getMinutes()
  return mins >= 570 && mins < 960
}

function fmt(v: number | null | undefined, d = 2): string {
  return v == null || isNaN(v) ? '—' : v.toFixed(d)
}

export default function DashboardHeader({ sessionState, alpacaState }: {
  sessionState: SessionStateRow | null
  alpacaState:  AlpacaState | null
}) {
  const [open, setOpen] = useState(false)
  const [dateEt, setDateEt] = useState('')

  useEffect(() => {
    setOpen(isMarketOpen())
    setDateEt(getET().toLocaleDateString('en-CA', { timeZone: 'America/New_York' }))
    const id = setInterval(() => setOpen(isMarketOpen()), 30_000)
    return () => clearInterval(id)
  }, [])

  const st = sessionState?.state
  const alpacaPos = alpacaState?.positions?.find(p => p.symbol === 'QQQ') ?? null
  const price = alpacaPos?.price ?? st?.QQQ?.last_close ?? null
  const vwap  = st?.QQQ?.vwap ?? null

  return (
    <header className="flex items-center justify-between gap-8 px-8 py-4 border-b border-[var(--border-soft)] bg-[var(--surface-0-alt)] sticky top-0 z-20">
      <div className="flex items-baseline gap-4">
        <span className="font-mono text-sm font-semibold tracking-wide text-[var(--text-0)]">TRADING&nbsp;DASHBOARD</span>
        <span className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-5)]">paper · alpaca · supabase</span>
      </div>
      <div className="flex items-center gap-6">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-[10px] tracking-widest text-[var(--text-5)]">QQQ</span>
          <span className="font-mono text-[17px] font-semibold tabular-nums text-[var(--text-0)]">{fmt(price)}</span>
          <span className="font-mono text-[11px] tabular-nums text-[var(--text-4)]">vwap {fmt(vwap)}</span>
        </div>
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[var(--surface-chip)] border border-[var(--border)]">
          <span className={`w-1.5 h-1.5 rounded-full ${open ? 'bg-[var(--green-dim)] animate-pulse' : 'bg-[var(--text-5)]'}`} />
          <span className="font-mono text-[11px] tracking-wide text-[var(--text-3)]">{open ? 'MARKET OPEN' : 'MARKET CLOSED'}</span>
        </div>
        <span suppressHydrationWarning className="font-mono text-[11px] tabular-nums text-[var(--text-5)]">{dateEt} ET</span>
      </div>
    </header>
  )
}
