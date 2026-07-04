'use client'

import { useEffect, useState } from 'react'
import type { Trade, AlpacaState, SessionStateRow, SessionPosition } from '@/lib/supabase'

// ─── helpers ─────────────────────────────────────────────────────────────────

function fmt(v: unknown, d = 2): string {
  const n = Number(v)
  return v == null || isNaN(n) ? '—' : n.toFixed(d)
}

function etToday(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' })
}

// "HH:MM:SS" ET → segundos del día
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

// ─── Posición (ladder SL → entry → precio → TP) ──────────────────────────────

function PositionLadder({ pos, currentPrice, unrealized }: {
  pos: SessionPosition; currentPrice: number | null; unrealized: number | null
}) {
  const entry = pos.entry, tp = pos.tp, sl = pos.sl
  const label = pos.sys ?? pos.strategy_id ?? '?'
  if (entry == null || tp == null || sl == null) {
    return <p className="text-xs text-gray-500">Posición sin niveles completos: {JSON.stringify(pos)}</p>
  }
  const isLong = tp > entry
  const cur    = currentPrice ?? entry
  const lo     = Math.min(tp, sl, cur) - 0.05
  const hi     = Math.max(tp, sl, cur) + 0.05
  const pct    = (p: number) => ((p - lo) / (hi - lo)) * 100
  const risk   = Math.abs(entry - sl)
  const r      = risk > 0 ? ((isLong ? cur - entry : entry - cur) / risk) : 0
  const rColor = r >= 0 ? 'text-emerald-400' : 'text-red-400'

  const marks: { label: string; price: number; cls: string; line: string }[] = [
    { label: 'TP',     price: tp,    cls: 'text-emerald-400', line: 'bg-emerald-500/60' },
    { label: 'entry',  price: entry, cls: 'text-gray-400',    line: 'bg-gray-600' },
    { label: 'SL',     price: sl,    cls: 'text-red-400',     line: 'bg-red-500/60' },
  ]

  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <p className="text-sm font-semibold text-white">
          {label}
          <span className={`ml-2 text-[10px] font-semibold ${isLong ? 'text-emerald-400' : 'text-red-400'}`}>
            {isLong ? 'LONG' : 'SHORT'}
          </span>
          <span className="ml-2 text-[11px] font-mono text-gray-400">{pos.qty ?? '?'} sh</span>
        </p>
        <p className="text-[10px] text-gray-500 font-mono">{pos.opened_ET ? `desde ${pos.opened_ET} ET` : ''}</p>
      </div>

      <div className="relative h-36 ml-1 mr-16">
        {/* riel */}
        <div className="absolute left-2 top-0 bottom-0 w-px bg-gray-800" />
        {marks.map(m => (
          <div key={m.label} className="absolute left-0 right-0 flex items-center gap-2"
               style={{ top: `${100 - pct(m.price)}%`, transform: 'translateY(-50%)' }}>
            <div className={`h-px flex-1 ${m.line}`} />
            <span className={`text-[10px] font-mono w-14 text-right ${m.cls}`}>{m.label} {m.price.toFixed(2)}</span>
          </div>
        ))}
        {/* precio actual */}
        <div className="absolute left-0 right-[-3.75rem] flex items-center gap-2"
             style={{ top: `${100 - pct(cur)}%`, transform: 'translateY(-50%)' }}>
          <span className="w-2 h-2 rounded-full bg-sky-400 shrink-0 ml-1" />
          <div className="h-px flex-1 bg-sky-400/40" />
          <span className="text-[11px] font-mono font-semibold text-sky-300 bg-gray-900 px-1 rounded">
            {cur.toFixed(2)}
          </span>
        </div>
      </div>

      <div className="flex justify-between text-[11px] font-mono mt-2 pt-2 border-t border-gray-800/60">
        <span className={rColor}>R actual {r >= 0 ? '+' : ''}{r.toFixed(2)}</span>
        {unrealized != null && (
          <span className={unrealized >= 0 ? 'text-emerald-400' : 'text-red-400'}>
            unrealized {unrealized >= 0 ? '+' : ''}${unrealized.toFixed(2)}
          </span>
        )}
      </div>
    </div>
  )
}

// ─── Trades de hoy (strip compacto) ──────────────────────────────────────────

const EXIT_STYLE: Record<string, string> = {
  TP:     'bg-emerald-500/15 text-emerald-400',
  SL:     'bg-red-500/15 text-red-400',
  TIME:   'bg-amber-500/15 text-amber-400',
  MANUAL: 'bg-gray-700/60 text-gray-400',
}

function TodayTrades({ trades, sessionDate }: { trades: Trade[]; sessionDate: string }) {
  const today = trades.filter(t =>
    new Date(t.filled_at ?? t.created_at).toLocaleDateString('en-CA', { timeZone: 'America/New_York' }) === sessionDate)
  if (today.length === 0) return <p className="text-[11px] text-gray-600 mt-3">Sin trades hoy.</p>
  const pnl = today.reduce((s, t) => s + (t.pnl ?? 0), 0)
  return (
    <div className="mt-3 pt-2 border-t border-gray-800/60">
      <div className="flex items-baseline justify-between mb-1.5">
        <p className="text-[10px] text-gray-500 uppercase tracking-wider">Trades de la sesión</p>
        <span className={`text-[11px] font-mono font-semibold ${pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
          {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
        </span>
      </div>
      <div className="space-y-1">
        {today.slice(0, 5).map(t => (
          <div key={t.id} className="flex items-center gap-2 text-[11px] font-mono">
            <span className="text-gray-600 w-12 shrink-0">
              {new Date(t.filled_at ?? t.created_at).toLocaleTimeString('en-GB', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit' })}
            </span>
            <span className="text-gray-300">{t.strategy ?? t.side}</span>
            <span className="text-gray-500">{t.quantity}@{t.price.toFixed(2)}</span>
            <span className="ml-auto flex items-center gap-1.5">
              {t.exit_type && (
                <span className={`px-1 py-px rounded text-[9px] font-semibold ${EXIT_STYLE[t.exit_type] ?? 'bg-gray-700 text-gray-400'}`}>
                  {t.exit_type}
                </span>
              )}
              <span className={t.pnl == null ? 'text-gray-600' : t.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                {t.pnl != null ? `${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}` : 'open'}
              </span>
            </span>
          </div>
        ))}
        {today.length > 5 && <p className="text-[10px] text-gray-600">+{today.length - 5} más en la tabla de trades</p>}
      </div>
    </div>
  )
}

// ─── Gates + GT ──────────────────────────────────────────────────────────────

function GateTag({ label, on, detail }: { label: string; on: boolean | null; detail?: string }) {
  const cls = on === null ? 'bg-gray-800 text-gray-500'
    : on ? 'bg-emerald-900/50 text-emerald-400' : 'bg-red-900/30 text-red-400'
  const dot = on === null ? 'bg-gray-600' : on ? 'bg-emerald-400' : 'bg-red-500'
  return (
    <div className={`flex items-center gap-1.5 text-[11px] px-2 py-1 rounded font-medium ${cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
      <span>{label}</span>
      {detail && <span className="font-mono text-[10px] opacity-70">{detail}</span>}
    </div>
  )
}

// ─── Pulso del loop (cycle_log v3.0.6) ───────────────────────────────────────

function CyclePulse({ cycleLog, isToday }: { cycleLog: string[]; isToday: boolean }) {
  const [nowSec, setNowSec] = useState(() => etNowSec())
  useEffect(() => {
    const id = setInterval(() => setNowSec(etNowSec()), 30_000)
    return () => clearInterval(id)
  }, [])

  const secs = cycleLog.map(secOfDay)
  const intervals: number[] = []
  for (let i = 1; i < secs.length; i++) {
    const d = secs[i] - secs[i - 1]
    if (d > 0 && d < 3600) intervals.push(d)
  }
  const sorted = [...intervals].sort((a, b) => a - b)
  const median = sorted.length ? sorted[Math.floor(sorted.length / 2)] : null

  const lastAge  = isToday && secs.length ? nowSec - secs[secs.length - 1] : null
  const alive    = lastAge != null && lastAge >= 0 && lastAge < 420          // <7 min = vivo
  const warming  = lastAge != null && lastAge >= 420 && lastAge < 900        // 7-15 min
  const ageColor = lastAge == null ? 'text-gray-600' : alive ? 'text-emerald-400' : warming ? 'text-amber-400' : 'text-red-400'

  const strip = intervals.slice(-40)

  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <p className="text-[11px] text-gray-400">
          <span className="font-mono font-semibold text-white">{cycleLog.length}</span> ciclos
          {median != null && <span className="text-gray-500"> · mediana <span className="font-mono">{fmtDur(median)}</span></span>}
        </p>
        {lastAge != null && lastAge >= 0 && (
          <span className={`text-[11px] font-mono ${ageColor}`}>● último hace {fmtDur(lastAge)}</span>
        )}
      </div>

      {strip.length > 0 ? (
        <div className="flex items-end gap-px h-10">
          {strip.map((d, i) => (
            <div
              key={i}
              className={`flex-1 rounded-sm ${d <= 340 ? 'bg-emerald-500/70' : d <= 450 ? 'bg-amber-400/70' : 'bg-red-400/70'}`}
              style={{ height: `${Math.max(8, Math.min(d, 600) / 600 * 100)}%` }}
              title={fmtDur(d)}
            />
          ))}
        </div>
      ) : (
        <p className="text-[11px] text-gray-600">Sin cycle_log (sesión pre-v3.0.6 o loop sin arrancar).</p>
      )}
      <p className="text-[9.5px] text-gray-600 mt-1.5">
        1 barra = 1 intervalo entre ciclos · verde ≤5:40 (alineado a vela 5-min) · ámbar ≤7:30 · rojo más
      </p>
    </div>
  )
}

// ─── Panel principal ─────────────────────────────────────────────────────────

export default function LiveSessionPanel({ sessionState, alpacaState, trades }: {
  sessionState: SessionStateRow | null
  alpacaState:  AlpacaState | null
  trades:       Trade[]
}) {
  const st = sessionState?.state
  const g  = st?.gates
  const isToday = sessionState?.date === etToday()

  if (!st) {
    return (
      <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest mb-2">Sesión</p>
        <p className="text-sm text-gray-600">Sin session_state — /pre-market siembra el estado a las 9:30 ET.</p>
      </div>
    )
  }

  // v3.1.0: lista multi-posición; fallback al objeto único legacy (v3.0)
  const positions = (st.positions && st.positions.length > 0)
    ? st.positions
    : st.position ? [st.position] : []
  const alpacaPos = alpacaState?.positions?.find(p => p.symbol === 'QQQ') ?? null
  const curPrice  = alpacaPos?.price ?? st.QQQ?.last_close ?? null
  const c4        = st.c4 ?? {}
  const fills     = st.fvg?.fills_today ?? 0
  const gt        = st.gt ?? null
  const c4Entries = Object.entries(c4).filter(([, v]) => typeof v === 'number')

  const liveGates: { label: string; on: boolean | null; detail?: string }[] = [
    { label: 'S2 FVG',    on: g?.computed_10 ? (g.fvg_on ?? false) : null,
      detail: g?.rvol30 != null ? `rvol ${fmt(g.rvol30)}` : undefined },
    { label: 'S3 VWAPPB', on: g?.computed_1030 ? (g.vwappb_on ?? false) : null,
      detail: g?.xvwap60 != null ? `xvwap ${g.xvwap60}` : undefined },
    { label: 'S1 RSI2', on: g?.computed_10 ? (g.rsi2_on ?? false) : null, detail: g?.open_loc ?? undefined },
    { label: 'S5 GAPF sh', on: g?.computed_10 ? (g.gapf_on ?? false) : null,
      detail: g?.gap_pct != null ? `gap ${fmt(g.gap_pct)}%` : undefined },
  ]

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
          Sesión{isToday ? ' de hoy' : ''} · {sessionState!.date}
          {!isToday && <span className="ml-2 normal-case text-gray-600">(última registrada)</span>}
        </p>
        <span className="text-[11px] text-gray-500 font-mono">
          QQQ {fmt(st.QQQ?.last_close)} · VWAP {fmt(st.QQQ?.vwap)}
          {st.session_low != null && st.session_high != null &&
            <span className="text-gray-600"> · rango {fmt(st.session_low)}–{fmt(st.session_high)}</span>}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-x-8 gap-y-6">
        {/* Col 1: posición + trades de hoy */}
        <div>
          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">
            {positions.length > 1 ? `Posiciones (${positions.length}/4)` : 'Posición'}
          </p>
          {positions.length > 0 ? (
            <div className="space-y-4">
              {positions.map((p, i) => (
                <PositionLadder key={p.oco_id ?? i} pos={p} currentPrice={curPrice}
                  unrealized={positions.length === 1 ? (alpacaPos?.pl ?? null) : null} />
              ))}
              {positions.length > 1 && alpacaPos?.pl != null && (
                <p className={`text-[11px] font-mono ${alpacaPos.pl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  unrealized total {alpacaPos.pl >= 0 ? '+' : ''}${alpacaPos.pl.toFixed(2)}
                </p>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <span className="w-2 h-2 rounded-full bg-gray-600" /> Flat — sin posición abierta
            </div>
          )}
          <TodayTrades trades={trades} sessionDate={sessionState!.date} />
        </div>

        {/* Col 2: gates + GT + C4 */}
        <div>
          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">Gates del día</p>
          <div className="flex flex-wrap gap-1.5 mb-3">
            {liveGates.map(t => <GateTag key={t.label} label={t.label} on={t.on} detail={t.detail} />)}
          </div>

          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1.5 mt-4">Golden Ticket (diario)</p>
          {gt ? (
            <div className="flex flex-wrap gap-1.5">
              <GateTag label="GTR2D" on={gt.rsi2d_on ?? false} detail={gt.rsi2_d != null ? `rsi2 ${fmt(gt.rsi2_d, 1)}` : undefined} />
              <GateTag label="GT3D" on={gt.d3_on ?? false} detail={gt.consec_down != null ? `${gt.consec_down} abajo` : undefined} />
            </div>
          ) : (
            <p className="text-[11px] text-gray-600">Se computa en /pre-market (activo desde 07-03).</p>
          )}

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-500 border-t border-gray-800/60 pt-2.5 mt-4">
            <span>FVG fills: <span className="font-mono text-gray-300">{fills}</span></span>
            {c4Entries.length > 0 && (
              <span>C4:{' '}
                {c4Entries.map(([k, v]) => (
                  <span key={k} className={`font-mono mr-1.5 ${Number(v) >= 2 ? 'text-red-400' : 'text-gray-300'}`}>
                    {k} {String(v)}/2
                  </span>
                ))}
              </span>
            )}
          </div>
        </div>

        {/* Col 3: pulso del loop */}
        <div>
          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">Pulso del loop (v3.0.6)</p>
          <CyclePulse cycleLog={(st.cycle_log ?? []) as string[]} isToday={isToday} />
        </div>
      </div>
    </div>
  )
}
