'use client'

import { useState } from 'react'
import type { Trade, AlpacaState } from '@/lib/supabase'
import type { DailyPnlPoint } from '@/lib/alpaca-sync'

const START_CAPITAL = 100_000
const GREEN = 'var(--green)'
const RED   = 'var(--red)'

function money(v: number): string {
  return (v >= 0 ? '+$' : '−$') + Math.abs(v).toFixed(2)
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

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-[var(--surface-2)] px-[13px] py-3">
      <div className="font-mono text-[10px] text-[var(--text-4)] mb-1.5">{label}</div>
      <div className="font-mono text-base font-semibold tabular-nums" style={{ color: color ?? 'var(--text-1)' }}>{value}</div>
    </div>
  )
}

export default function PerformanceSummary({ trades, alpacaState, dailyPnl }: {
  trades:      Trade[]
  alpacaState: AlpacaState | null
  dailyPnl:    DailyPnlPoint[]
}) {
  const [hover, setHover]  = useState<number | null>(null)
  const [sel, setSel]      = useState<number | null>(null)

  // ─── P&L diario: curva real de Alpaca (broker truth), NO trades.pnl agregado por día ───
  // El ledger interno (`trades`) arrastra ~$20 de drift acumulado vs. la cuenta real: fees
  // TAF/CAT/REG que Alpaca cobra y nunca se loguean ahí, más un puñado de fills viejos de
  // mayo-junio con precio de salida estimado a mano en vez de leído del fill real. Iguala
  // lo que se ve en la propia app de Alpaca. `trades` sigue siendo la fuente correcta para
  // métricas por-trade (hit ratio, avg P&L) — el broker no las expone.
  const days = [...dailyPnl].sort((a, b) => a.day.localeCompare(b.day))

  let cum = 0
  const cumSeries = days.map(d => { cum += d.pnl; return { day: d.day, pnl: d.pnl, cum } })

  // Headline: equity en vivo (fetch separado, más fresco que el último bar diario de arriba).
  // Fallback a cum (curva diaria) si ese fetch en vivo falló.
  const net = alpacaState?.equity != null ? alpacaState.equity - START_CAPITAL : cum
  const netPct = (net / START_CAPITAL) * 100

  const nowMonth = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' }).slice(0, 7)
  const mtd = days.filter(d => d.day.startsWith(nowMonth)).reduce((a, d) => a + d.pnl, 0)

  let peak = 0, maxDD = 0
  for (const c of cumSeries) { peak = Math.max(peak, c.cum); maxDD = Math.max(peak - c.cum, maxDD) }

  const grossW = days.reduce((a, d) => a + Math.max(d.pnl, 0), 0)
  const grossL = days.reduce((a, d) => a + Math.max(-d.pnl, 0), 0)
  const pf = grossL > 0 ? (grossW / grossL).toFixed(2) : grossW > 0 ? '∞' : '—'

  const closed = trades.filter(t => t.pnl != null)
  const wins   = closed.filter(t => (t.pnl ?? 0) > 0).length
  const losses = closed.filter(t => (t.pnl ?? 0) < 0).length
  const hitTotal = wins + losses
  const hitPct = hitTotal > 0 ? Math.round((wins / hitTotal) * 100) : 0
  const avgPnL = closed.length > 0 ? closed.reduce((s, t) => s + (t.pnl ?? 0), 0) / closed.length : 0

  const equity   = alpacaState?.equity ?? null
  const cash     = alpacaState?.cash ?? 0
  const invested = (alpacaState?.positions ?? []).reduce((s, p) => s + p.market_value, 0)

  // ─── Last 8 sessions: equity curve + bar strip (ported from the design canvas) ───
  const last8 = cumSeries.slice(-8)
  const N = last8.length
  const peakBar = Math.max(...last8.map(s => Math.abs(s.pnl)), 1)
  const X = (i: number) => ((i - 0.5) / N) * 100
  const startCum = last8.length > 0 ? last8[0].cum - last8[0].pnl : 0
  const pts = [startCum, ...last8.map(s => s.cum)]
  const lo = Math.min(...pts), hi = Math.max(...pts), span = (hi - lo) || 1
  const Y = (v: number) => 96 - ((v - lo) / span) * 92

  const line = N > 0
    ? ['0,' + Y(pts[0]).toFixed(2)]
        .concat(pts.slice(1).map((v, i) => X(i + 1).toFixed(2) + ',' + Y(v).toFixed(2)))
        .concat(['100,' + Y(pts[pts.length - 1]).toFixed(2)])
        .join(' ')
    : ''

  const tipIdx = hover ?? sel
  const tip = tipIdx == null || N === 0 ? null : {
    left: X(tipIdx + 1).toFixed(2) + '%',
    shift: tipIdx > N - 3 ? 'translateX(-100%)' : tipIdx < 1 ? 'translateX(0)' : 'translateX(-50%)',
    date: fmtDate(last8[tipIdx].day),
    pnl: money(last8[tipIdx].pnl),
    color: last8[tipIdx].pnl >= 0 ? GREEN : RED,
    cum: `$${pts[tipIdx + 1].toFixed(2)}`,
  }

  const detailIdx = hover ?? sel
  const sessionDetail = detailIdx != null && N > 0
    ? `${fmtDate(last8[detailIdx].day)} · ${money(last8[detailIdx].pnl)}`
    : 'equity acumulado · fuente alpaca'

  function onChartMove(e: React.MouseEvent<HTMLDivElement>) {
    const r = e.currentTarget.getBoundingClientRect()
    const t = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width))
    const i = Math.max(0, Math.min(N - 1, Math.floor(t * N)))
    setHover(i)
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-2.5">
        <span className="font-mono text-[10px] font-semibold tracking-[0.16em] uppercase text-[var(--text-3)]">Performance</span>
        <span className="h-px flex-1 bg-[var(--border-soft)]" />
        <span className="font-mono text-[10px] text-[var(--text-5)]">{days.length} sesiones · fuente alpaca</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-4">
        {/* Equity actual */}
        <div className="bg-[var(--surface-1)] border border-[var(--border)] rounded-lg p-[18px] flex flex-col gap-4">
          <div>
            <div className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-4)] mb-1.5">Equity actual</div>
            <div className="font-mono text-[32px] font-semibold tabular-nums tracking-tight text-[var(--text-0)]">{fmtUSD(equity)}</div>
            <div className="flex gap-4 mt-1.5 font-mono text-[11px] text-[var(--text-4)]">
              <span>cash {fmtUSD(cash)}</span>
              <span>invertido {fmtUSD(invested)}</span>
            </div>
          </div>
          <div className="pt-3.5 border-t border-[var(--border-soft)]">
            <div className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-4)] mb-1.5">Net P&amp;L</div>
            <div className="font-mono text-[26px] font-semibold tabular-nums tracking-tight" style={{ color: net >= 0 ? GREEN : RED }}>{money(net)}</div>
            <div className="font-mono text-[11px] text-[var(--text-4)] mt-1">{netPct >= 0 ? '+' : ''}{netPct.toFixed(2)}% · avg {money(avgPnL)} / trade</div>
          </div>
          <div className="grid grid-cols-2 gap-px bg-[var(--border)] border border-[var(--border)] rounded-md overflow-hidden">
            <Stat label="MTD" value={money(mtd)} color={mtd >= 0 ? GREEN : RED} />
            <Stat label="profit factor" value={pf} />
            <div className="bg-[var(--surface-2)] px-[13px] py-3">
              <div className="font-mono text-[10px] text-[var(--text-4)] mb-1.5">hit ratio</div>
              <div className="flex items-baseline gap-1.5">
                <span className="font-mono text-base font-semibold tabular-nums text-[var(--text-1)]">{hitTotal > 0 ? `${hitPct}%` : '—'}</span>
                <span className="font-mono text-[10px] text-[var(--text-5)]">{wins}W/{losses}L</span>
              </div>
              <div className="flex h-[3px] mt-1.5 rounded-full overflow-hidden bg-[var(--border)]">
                <span style={{ width: `${hitPct}%`, background: GREEN }} />
                <span style={{ width: `${100 - hitPct}%`, background: RED }} />
              </div>
            </div>
            <Stat label="max dd" value={maxDD > 0 ? `−$${maxDD.toFixed(2)}` : '—'} color={maxDD > 0 ? RED : undefined} />
          </div>
        </div>

        {/* P&L acumulado */}
        <div className="bg-[var(--surface-1)] border border-[var(--border)] rounded-lg p-[18px] flex flex-col">
          <div className="flex items-center justify-between mb-1.5">
            <span className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-4)]">P&amp;L acumulado</span>
            <span className="font-mono text-[10px] text-[var(--text-5)]">equity diario · source: alpaca</span>
          </div>

          {N === 0 ? (
            <p className="text-sm text-[var(--text-4)] py-10 text-center">Sin trades cerrados todavía.</p>
          ) : (
            <>
              <div onMouseMove={onChartMove} onMouseLeave={() => setHover(null)} className="relative h-[150px] my-1.5 mb-1">
                <div className="absolute inset-0 flex flex-col justify-between">
                  {[0, 1, 2, 3].map(i => <span key={i} className="h-px bg-[var(--border-faint)]" />)}
                </div>
                <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 w-full h-full overflow-hidden">
                  <defs>
                    <linearGradient id="eqFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--cyan)" stopOpacity={0.28} />
                      <stop offset="100%" stopColor="var(--cyan)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <polygon points={`${line} 100,100 0,100`} fill="url(#eqFill)" />
                  <polyline points={line} fill="none" stroke="var(--cyan-dim)" strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
                </svg>
                <div className="absolute left-0 top-0 font-mono text-[10px] tabular-nums text-[var(--text-4)] bg-[var(--surface-1)] px-1">${hi.toFixed(0)}</div>
                <div className="absolute left-0 bottom-0 font-mono text-[10px] tabular-nums text-[var(--text-4)] bg-[var(--surface-1)] px-1">${lo.toFixed(0)}</div>
                <div className="absolute w-[9px] h-[9px] rounded-full border-2 border-[var(--cyan)] bg-[var(--surface-0)]"
                  style={{ left: '100%', marginLeft: -5, marginTop: -4.5, top: `${Y(pts[pts.length - 1])}%` }} />
                <div className="absolute right-0 font-mono text-[11px] font-semibold tabular-nums bg-[var(--surface-1)] px-1.5 py-px rounded"
                  style={{ color: 'var(--cyan)', transform: 'translateY(-140%)', top: `${Y(pts[pts.length - 1])}%` }}>
                  ${pts[pts.length - 1].toFixed(2)}
                </div>
                {tip && (
                  <>
                    <div className="absolute top-0 bottom-0 w-px bg-[var(--cyan-dim)] pointer-events-none" style={{ left: tip.left }} />
                    <div className="absolute top-1.5 z-10 pointer-events-none px-2.5 py-2 rounded bg-[var(--surface-3)] border border-[var(--border)] shadow-xl whitespace-nowrap"
                      style={{ left: tip.left, transform: tip.shift }}>
                      <div className="font-mono text-[11px] font-semibold text-[var(--text-0)] mb-1">{tip.date} 2026</div>
                      <div className="flex gap-3.5">
                        <div>
                          <div className="font-mono text-[9px] tracking-wider uppercase text-[var(--text-5)]">día</div>
                          <div className="font-mono text-xs font-semibold tabular-nums" style={{ color: tip.color }}>{tip.pnl}</div>
                        </div>
                        <div>
                          <div className="font-mono text-[9px] tracking-wider uppercase text-[var(--text-5)]">acum</div>
                          <div className="font-mono text-xs tabular-nums text-[var(--text-1)]">{tip.cum}</div>
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </div>

              <div className="flex items-stretch gap-0 h-[62px] pt-3 border-t border-[var(--border-soft)]">
                {last8.map((s, i) => {
                  const upH = s.pnl >= 0 ? Math.max(3, Math.round((Math.abs(s.pnl) / peakBar) * 100)) : 0
                  const dnH = s.pnl < 0 ? Math.max(3, Math.round((Math.abs(s.pnl) / peakBar) * 100)) : 0
                  const active = sel === i || hover === i
                  return (
                    <div key={s.day}
                      onClick={() => setSel(v => v === i ? null : i)}
                      onMouseEnter={() => setHover(i)}
                      onMouseLeave={() => setHover(null)}
                      className="flex-1 flex flex-col cursor-pointer rounded"
                      style={{ background: active ? 'var(--surface-hover)' : 'transparent' }}>
                      <div className="flex-1 flex items-end justify-center">
                        <span className="w-[40%] rounded-t-sm" style={{ background: GREEN, height: `${upH}%` }} />
                      </div>
                      <div className="h-px bg-[var(--border)]" />
                      <div className="flex-1 flex items-start justify-center">
                        <span className="w-[40%] rounded-b-sm" style={{ background: RED, height: `${dnH}%` }} />
                      </div>
                      <div className="text-center mt-1 font-mono text-[9px]" style={{ color: active ? 'var(--cyan-dim)' : 'var(--text-5)' }}>{fmtDate(s.day)}</div>
                    </div>
                  )
                })}
              </div>
              <div className="flex items-baseline justify-between mt-2.5 font-mono text-[11px] text-[var(--text-3)]">
                <span>{sessionDetail}</span>
                <span className="text-[var(--text-5)]">últimas {N} sesiones · click para detalle</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
