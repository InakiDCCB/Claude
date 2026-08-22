'use client'

import { useEffect, useState } from 'react'
import type { Trade, AlpacaState, SessionStateRow } from '@/lib/supabase'

function fmt(v: unknown, d = 2): string {
  const n = Number(v)
  return v == null || isNaN(n) ? '—' : n.toFixed(d)
}
function fmtUSD(v: number | null | undefined): string {
  if (v == null) return '—'
  return (v >= 0 ? '+$' : '−$') + Math.abs(v).toFixed(2)
}
function etToday(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' })
}
function secOfDay(hms: string): number {
  const [h, m, s] = hms.split(':').map(Number)
  return h * 3600 + m * 60 + (s || 0)
}
function etNowSec(): number {
  const t = new Date().toLocaleTimeString('en-GB', { timeZone: 'America/New_York', hour12: false })
  return secOfDay(t)
}
function fmtDur(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`
  const m = Math.floor(sec / 60)
  return m < 60 ? `${m}m ${Math.round(sec % 60)}s` : `${Math.floor(m / 60)}h ${m % 60}m`
}

function CardShell({ children }: { children: React.ReactNode }) {
  return <div className="bg-[var(--surface-1)] p-4 px-[18px] flex flex-col gap-3">{children}</div>
}
function CardLabel({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-4)]">{children}</span>
      {right}
    </div>
  )
}

// ─── Broker ──────────────────────────────────────────────────────────────────

function BrokerCard({ alpacaState, trades, sessionDate }: {
  alpacaState: AlpacaState | null; trades: Trade[]; sessionDate: string
}) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 10_000); return () => clearInterval(id) }, [])

  const pos = alpacaState?.positions?.find(p => p.symbol === 'QQQ') ?? null
  const syncAge = alpacaState?.synced_at ? Math.floor((now - new Date(alpacaState.synced_at).getTime()) / 1000) : null
  const syncColor = syncAge == null ? 'var(--text-5)' : syncAge < 120 ? 'var(--green-dim)' : syncAge < 300 ? 'var(--amber)' : 'var(--red)'
  const syncLabel = syncAge == null ? '—' : syncAge < 60 ? `${syncAge}s` : `${Math.floor(syncAge / 60)}m`

  const todayTrades = trades.filter(t =>
    new Date(t.filled_at ?? t.created_at).toLocaleDateString('en-CA', { timeZone: 'America/New_York' }) === sessionDate)
  const dayPnl = todayTrades.reduce((s, t) => s + (t.pnl ?? 0), 0)
  const hasClosedToday = todayTrades.some(t => t.pnl != null)

  return (
    <CardShell>
      <CardLabel right={<span className="font-mono text-[10px] tracking-wide" style={{ color: syncColor }}>SYNCED {syncLabel}</span>}>Broker</CardLabel>
      <div>
        <div className="font-mono text-[22px] font-semibold tracking-tight text-[var(--text-0)]">{pos ? `${pos.qty > 0 ? 'LONG' : 'SHORT'}` : 'FLAT'}</div>
        <div className="font-mono text-[11px] text-[var(--text-4)] mt-0.5">{pos ? `${Math.abs(pos.qty)} sh @ $${pos.avg_entry.toFixed(2)}` : 'sin posición abierta'}</div>
      </div>
      <div className="flex gap-5 pt-2.5 border-t border-[var(--border-soft)] mt-auto">
        <div>
          <div className="font-mono text-[10px] text-[var(--text-5)]">day p&amp;l</div>
          <div className="font-mono text-[13px] tabular-nums text-[var(--text-2)]">{hasClosedToday ? fmtUSD(dayPnl) : '—'}</div>
        </div>
        <div>
          <div className="font-mono text-[10px] text-[var(--text-5)]">unrealized</div>
          <div className="font-mono text-[13px] tabular-nums text-[var(--text-2)]">{fmtUSD(pos?.pl ?? (pos ? 0 : 0))}</div>
        </div>
        <div>
          <div className="font-mono text-[10px] text-[var(--text-5)]">trades hoy</div>
          <div className="font-mono text-[13px] tabular-nums text-[var(--text-2)]">{todayTrades.length}</div>
        </div>
      </div>
    </CardShell>
  )
}

// ─── Gates ───────────────────────────────────────────────────────────────────

function GatesCard({ sessionState }: { sessionState: SessionStateRow | null }) {
  const g = sessionState?.state?.gates
  const c4 = sessionState?.state?.c4 ?? {}
  const gates: { label: string; on: boolean | null; detail?: string }[] = [
    { label: 'S2 fvg',  on: g?.computed_10 ? (g.fvg_on ?? false) : null, detail: g?.rvol30 != null ? `rvol ${fmt(g.rvol30)}` : undefined },
    { label: 'S1 rsi2', on: g?.computed_10 ? (g.rsi2_on ?? false) : null, detail: g?.open_loc ?? undefined },
  ]
  const blocked = gates.filter(x => x.on === false).length
  const c4Chips = ['fvg', 'swp', 'rsi2'].map(k => ({ k, v: Number(c4[k] ?? 0) }))

  return (
    <CardShell>
      <CardLabel right={blocked > 0 ? <span className="font-mono text-[10px] tracking-wide text-[var(--amber)]">{blocked} BLOCKED</span> : undefined}>Gates</CardLabel>
      <div className="flex flex-col gap-2">
        {gates.map(gt => (
          <div key={gt.label} className="flex items-center justify-between gap-2.5">
            <span className="flex items-center gap-1.5">
              <span className="w-[5px] h-[5px] rounded-full" style={{ background: gt.on === null ? 'var(--text-5)' : gt.on ? 'var(--green-dim)' : 'var(--amber)' }} />
              <span className="font-mono text-[11px] text-[var(--text-2)]">{gt.label}</span>
            </span>
            <span className="font-mono text-[11px] tabular-nums" style={{ color: gt.on === null ? 'var(--text-5)' : gt.on ? 'var(--green-dim)' : 'var(--amber)' }}>{gt.detail ?? (gt.on === null ? '—' : gt.on ? 'ON' : 'off')}</span>
          </div>
        ))}
      </div>
      <div className="flex gap-1 mt-auto pt-2.5 border-t border-[var(--border-soft)]">
        {c4Chips.map(c => (
          <span key={c.k} className="flex-1 text-center py-1.5 rounded font-mono text-[10px] tabular-nums"
            style={{ background: 'var(--surface-chip)', color: c.v >= 2 ? 'var(--red)' : 'var(--text-3)' }}>{c.k} {c.v}/2</span>
        ))}
      </div>
    </CardShell>
  )
}

// ─── Rango de hoy ────────────────────────────────────────────────────────────

function RangeCard({ sessionState, alpacaState }: { sessionState: SessionStateRow | null; alpacaState: AlpacaState | null }) {
  const st = sessionState?.state
  const lo = st?.session_low, hi = st?.session_high
  const alpacaPos = alpacaState?.positions?.find(p => p.symbol === 'QQQ')
  const price = alpacaPos?.price ?? st?.QQQ?.last_close ?? null
  const vwap  = st?.QQQ?.vwap ?? null

  const have = lo != null && hi != null && hi > lo
  const pct = (v: number) => have ? ((v - lo!) / (hi! - lo!)) * 100 : 0

  return (
    <CardShell>
      <CardLabel right={have ? <span className="font-mono text-[10px] text-[var(--text-5)]">{(hi! - lo!).toFixed(2)} pts</span> : undefined}>Rango de hoy</CardLabel>
      {have ? (
        <div className="pt-2.5">
          <div className="relative h-[5px] rounded-full bg-[var(--border-soft)]">
            {vwap != null && <div className="absolute -top-[3px] w-0.5 h-[11px]" style={{ left: `${pct(vwap)}%`, background: 'var(--text-3)' }} />}
            {price != null && <div className="absolute -top-1.5 w-0.5 h-[17px]" style={{ left: `${pct(price)}%`, background: 'var(--cyan)' }} />}
          </div>
          <div className="flex justify-between mt-2.5 font-mono text-[10px] tabular-nums text-[var(--text-5)]">
            <span>{lo!.toFixed(2)}</span>
            <span>{hi!.toFixed(2)}</span>
          </div>
        </div>
      ) : (
        <p className="text-[11px] text-[var(--text-5)]">Sin rango de sesión todavía.</p>
      )}
      <div className="mt-auto pt-2.5 border-t border-[var(--border-soft)] font-mono text-[10px] leading-relaxed text-[var(--text-5)]">precio spot vs vwap de la sesión</div>
    </CardShell>
  )
}

// ─── Loop pulse ──────────────────────────────────────────────────────────────

function PulseCard({ sessionState }: { sessionState: SessionStateRow | null }) {
  const [nowSec, setNowSec] = useState(() => etNowSec())
  const [pulseHover, setPulseHover] = useState<number | null>(null)
  useEffect(() => { const id = setInterval(() => setNowSec(etNowSec()), 30_000); return () => clearInterval(id) }, [])

  const isToday = sessionState?.date === etToday()
  const cycleLog = (sessionState?.state?.cycle_log ?? []) as string[]
  const secs = cycleLog.map(secOfDay)
  const intervals: number[] = []
  for (let i = 1; i < secs.length; i++) { const d = secs[i] - secs[i - 1]; if (d > 0 && d < 3600) intervals.push(d) }
  const sorted = [...intervals].sort((a, b) => a - b)
  const median = sorted.length ? sorted[Math.floor(sorted.length / 2)] : null
  const lastAge = isToday && secs.length ? nowSec - secs[secs.length - 1] : null
  const alive = lastAge != null && lastAge >= 0 && lastAge < 420
  const warming = lastAge != null && lastAge >= 420 && lastAge < 900
  const statusColor = lastAge == null ? 'var(--text-5)' : alive ? 'var(--green-dim)' : warming ? 'var(--amber)' : 'var(--red)'
  const statusLabel = lastAge == null ? '—' : alive ? 'ACTIVE' : warming ? 'WARMING' : 'IDLE'

  const strip = intervals.slice(-24)
  const gapColor = (g: number) => g <= 340 ? 'var(--green-dim)' : g <= 450 ? 'var(--amber)' : 'var(--red)'
  const lastCycleSec = secs.length ? secs[secs.length - 1] : null

  return (
    <CardShell>
      <CardLabel right={
        <span className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full animate-pulse-dot" style={{ background: statusColor }} />
          <span className="font-mono text-[10px] tracking-wide" style={{ color: statusColor }}>{statusLabel}</span>
        </span>
      }>Loop v3.0.6</CardLabel>
      <div className="flex items-baseline gap-2.5">
        <span className="font-mono text-[30px] font-semibold tabular-nums tracking-tight text-[var(--text-0)]">{median != null ? fmtDur(median) : '—'}</span>
        <span className="font-mono text-[11px] text-[var(--text-4)]">mediana / ciclo</span>
      </div>
      <div className="relative">
        <div className="flex h-[5px] gap-0.5 items-end">
          {strip.length > 0 ? strip.map((g, i) => (
            <span key={i} onMouseEnter={() => setPulseHover(i)} onMouseLeave={() => setPulseHover(null)}
              className="flex-1 h-[9px] -mt-1 rounded-sm cursor-default" style={{ background: gapColor(g) }} />
          )) : <span className="font-mono text-[10px] text-[var(--text-5)]">Sin cycle_log.</span>}
        </div>
        {pulseHover != null && strip.length > 0 && (
          <div className="absolute bottom-3.5 z-10 pointer-events-none px-2 py-1.5 rounded bg-[var(--surface-3)] border border-[var(--border)] shadow-xl whitespace-nowrap"
            style={{ left: `${((pulseHover + 0.5) / strip.length) * 100}%`, transform: pulseHover < 3 ? 'translateX(-10%)' : pulseHover > strip.length - 4 ? 'translateX(-90%)' : 'translateX(-50%)' }}>
            <div className="font-mono text-[10px] tabular-nums" style={{ color: gapColor(strip[pulseHover]) }}>gap {fmtDur(strip[pulseHover])}</div>
          </div>
        )}
      </div>
      <div className="flex justify-between font-mono text-[10px] text-[var(--text-5)]">
        <span>{cycleLog.length} ciclos hoy</span>
        <span>{lastAge != null && lastAge >= 0 ? `último hace ${fmtDur(lastAge)}` : lastCycleSec != null ? 'no es sesión de hoy' : 'sin ciclos'}</span>
      </div>
      <div className="mt-auto pt-2.5 border-t border-[var(--border-soft)] font-mono text-[10px] leading-relaxed text-[var(--text-5)]">cadencia verde ≤5:40 · ámbar ≤7:30 · rojo más</div>
    </CardShell>
  )
}

// ─── Main ────────────────────────────────────────────────────────────────────

export default function HealthGrid({ sessionState, alpacaState, trades }: {
  sessionState: SessionStateRow | null
  alpacaState:  AlpacaState | null
  trades:       Trade[]
}) {
  if (!sessionState?.state) {
    return (
      <div>
        <div className="flex items-center gap-3 mb-2.5">
          <span className="font-mono text-[10px] font-semibold tracking-[0.16em] uppercase text-[var(--text-3)]">Health</span>
          <span className="h-px flex-1 bg-[var(--border-soft)]" />
        </div>
        <p className="text-sm text-[var(--text-5)] bg-[var(--surface-1)] border border-[var(--border)] rounded-lg p-4">
          Sin session_state — /pre-market siembra el estado a las 9:30 ET.
        </p>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-2.5">
        <span className="font-mono text-[10px] font-semibold tracking-[0.16em] uppercase text-[var(--text-3)]">Health</span>
        <span className="h-px flex-1 bg-[var(--border-soft)]" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-px bg-[var(--border)] border border-[var(--border)] rounded-lg overflow-hidden">
        <BrokerCard alpacaState={alpacaState} trades={trades} sessionDate={sessionState.date} />
        <GatesCard sessionState={sessionState} />
        <RangeCard sessionState={sessionState} alpacaState={alpacaState} />
        <PulseCard sessionState={sessionState} />
      </div>
    </div>
  )
}
