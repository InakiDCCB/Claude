'use client'

import { useState } from 'react'
import type { StrategyRanking, StrategyRegistry, ShadowAccum, Trade } from '@/lib/supabase'

// strategy_id canónico -> código `sys` que usa v_shadow_accumulated
const ID_TO_SYS: Record<string, string> = {
  rsi2_v3: 'RSI2', fvg_v3: 'FVG', swp_v3: 'SWP', lwr_v1: 'LWR',
  gt_closelow_v2: 'GTCLV2',
}

const GREEN = 'var(--green)', RED = 'var(--red)'

// Descripciones y notas de investigación por sistema — texto curado, no viene de la DB.
const INFO: Record<string, { desc: string; badges?: string[]; rule?: string }> = {
  fvg_v3: { desc: 'Busca huecos de precio que dejan las velas de impulso (fair value gaps) y entra cuando el precio vuelve a rellenar ese hueco, con confirmación de volumen relativo por encima de lo normal.' },
  rsi2_v3: { desc: 'Espera una caída corta y profunda — RSI de 2 periodos en sobreventa — dentro de la tendencia intradía, y compra el rebote inmediato.' },
  swp_v3: { desc: 'Espera que el precio barra un mínimo previo (caza de stops) y lo recupere de inmediato; entra en esa recuperación, no en el barrido.' },
  gt_closelow_v2: {
    desc: 'Busca días en los que el cierre queda pegado al mínimo del día — venta agotada. Compra en la apertura del día siguiente y mantiene la posición 3 días hábiles, sin stop intradía.',
    badges: ['PF 2.36', 'hit 66.5%', 't +3.01', '10/11 años +'],
    rule: 'Regla: clr(ayer)<0.1 → long open hoy, exit = close del día+2. El más fuerte de toda la sesión de research.',
  },
  lwr_v1: {
    desc: 'Busca velas de 1 minuto con una mecha inferior muy larga y volumen muy por encima de lo normal — un barrido de liquidez bajo el precio. Entra en contra de ese movimiento esperando el rebote inmediato.',
    rule: 'Regla: mecha inferior ≥60% del rango + volumen ≥3× avgv5 → fade alcista. Offline: n=79, hit 72.2%, PF 1.49, Horizon Score 60.1/100. SHORT descartado (killed 96/96 celdas).',
  },
}

const TIER_LABEL: Record<string, string> = { established: 'established', provisional: 'provisional', insufficient_data: 'sin muestra' }

function money(v: number): string { return (v >= 0 ? '+$' : '−$') + Math.abs(v).toFixed(2) }

// ─── Live table ──────────────────────────────────────────────────────────────

const LIVE_COLS = 'grid-cols-[minmax(120px,1fr)_40px_48px_50px_76px_62px_92px_48px]'

function LiveTable({ registry, ranking, trades }: { registry: StrategyRegistry[]; ranking: StrategyRanking[]; trades: Trade[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const rankingById = new Map(ranking.map(r => [r.strategy_id, r]))
  const live = registry.filter(r => r.status === 'live')

  const rows = live.map(reg => {
    const r = rankingById.get(reg.strategy_id) ?? null
    const pnl = trades.filter(t => t.strategy === reg.strategy_id && t.pnl != null).reduce((s, t) => s + (t.pnl ?? 0), 0)
    return { reg, r, pnl }
  })

  return (
    <div className="bg-[var(--surface-1)] border border-[var(--border)] rounded-lg overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[var(--border-soft)]">
        <span className="w-[5px] h-[5px] rounded-full" style={{ background: 'var(--green-dim)' }} />
        <span className="font-mono text-[10px] tracking-widest uppercase" style={{ color: 'var(--green-dim)' }}>Live</span>
      </div>
      <div className="overflow-x-auto">
        <div className="min-w-[640px]">
          <div className={`grid ${LIVE_COLS} gap-3.5 px-4 py-2 bg-[var(--surface-1-alt)] border-b border-[var(--border)] font-mono text-[9px] tracking-widest uppercase text-[var(--text-5)]`}>
            <span>estrategia</span><span className="text-right">n</span><span className="text-right">wr</span><span className="text-right">pf</span>
            <span className="text-right">p&amp;l acum</span><span className="text-right">exp_lb</span><span className="text-center">tier</span><span className="text-right">score</span>
          </div>
          {rows.length === 0 ? (
            <p className="text-sm text-[var(--text-5)] py-8 text-center">Sin sistemas live registrados.</p>
          ) : rows.map(({ reg, r, pnl }, i) => {
            const info = INFO[reg.strategy_id]
            const open = hover === i
            return (
              <div key={reg.strategy_id} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                <div className={`grid ${LIVE_COLS} gap-3.5 items-center px-4 py-3 border-b border-[var(--border-faint)] font-mono text-[11px] tabular-nums`}
                  style={{ color: 'var(--text-2)', background: open ? 'var(--surface-hover)' : 'transparent' }}>
                  <span className="font-sans text-xs font-medium" style={{ color: 'var(--text-1)' }}>{reg.name}</span>
                  <span className="text-right" style={{ color: 'var(--text-3)' }}>{r?.n ?? '—'}</span>
                  <span className="text-right">{r?.wr != null ? `${r.wr.toFixed(0)}%` : '—'}</span>
                  <span className="text-right">{r?.pf != null ? r.pf.toFixed(2) : '—'}</span>
                  <span className="text-right font-semibold" style={{ color: pnl >= 0 ? GREEN : RED }}>{money(pnl)}</span>
                  <span className="text-right" style={{ color: r?.exp_lb != null && r.exp_lb >= 0 ? GREEN : RED }}>{r?.exp_lb != null ? `${r.exp_lb >= 0 ? '+' : ''}${r.exp_lb.toFixed(2)}` : '—'}</span>
                  <span className="text-center">
                    {r ? (
                      <span className="inline-block px-1.5 py-0.5 rounded text-[9px] tracking-wide"
                        style={{ background: r.tier === 'established' ? 'var(--green-bg)' : r.tier === 'provisional' ? 'oklch(0.27 0.03 180)' : 'var(--surface-2)', color: r.tier === 'established' ? GREEN : r.tier === 'provisional' ? 'var(--cyan)' : 'var(--text-3)' }}>
                        {TIER_LABEL[r.tier] ?? r.tier}
                      </span>
                    ) : '—'}
                  </span>
                  <span className="text-right font-semibold">{r?.score != null ? r.score.toFixed(1) : '—'}</span>
                </div>
                {open && info && (
                  <div className="px-4 pt-2.5 pb-3 bg-[var(--surface-3)] border-b border-[var(--border)]">
                    <div className="font-mono text-[9px] tracking-widest uppercase mb-1" style={{ color: 'oklch(0.58 0.08 180)' }}>cómo funciona</div>
                    <div className="text-[11px] leading-relaxed" style={{ color: 'var(--text-2)' }}>{info.desc}</div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
      <div className="px-4 py-3 font-mono text-[10px] leading-relaxed text-[var(--text-5)]">
        p&amp;l acum = trades reconciliados con el broker · score = 0.45·calidad(PF + WR Wilson) + 0.25·exp_lb + 0.30·robustez − drawdown. sólo se puntúa con n≥20.
      </div>
    </div>
  )
}

// ─── Shadow cards ────────────────────────────────────────────────────────────

function ShadowCards({ registry, accum }: { registry: StrategyRegistry[]; accum: ShadowAccum[] }) {
  const accumById = new Map(accum.map(a => [a.strategy_id, a]))
  const shadows = registry.filter(r => r.status === 'shadow')

  return (
    <div className="bg-[var(--surface-1)] border border-[var(--border)] rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border-soft)]">
        <span className="flex items-center gap-2">
          <span className="w-[5px] h-[5px] rounded-full" style={{ background: 'var(--purple)' }} />
          <span className="font-mono text-[10px] tracking-widest uppercase" style={{ color: 'var(--purple)' }}>Shadow</span>
        </span>
        <span className="font-mono text-[10px] text-[var(--text-5)]">cero órdenes · resuelto en /post-close</span>
      </div>

      {shadows.length === 0 ? (
        <p className="text-sm text-[var(--text-5)] py-8 text-center">Sin sistemas en shadow.</p>
      ) : shadows.map((reg, i) => {
        const a = accumById.get(reg.strategy_id) ?? null
        const info = INFO[reg.strategy_id]
        const sys = ID_TO_SYS[reg.strategy_id] ?? reg.strategy_id
        const wr = a?.wr_pct != null ? Number(a.wr_pct) : null
        const pnl = a?.pnl_sh != null ? Number(a.pnl_sh) : null
        return (
          <div key={reg.strategy_id} className={i < shadows.length - 1 ? 'px-4 py-3.5 border-b border-[var(--border-faint)]' : 'px-4 py-3.5'}>
            <div className="flex items-baseline justify-between gap-3 mb-1.5">
              <span className="text-xs font-medium" style={{ color: 'var(--text-1)' }}>{reg.name}</span>
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-4)' }}>
                {a ? `${a.n} señal${a.n === 1 ? '' : 'es'}` : `sin señales aún (${sys})`}
              </span>
            </div>
            <div className="flex gap-1.5 mb-2 flex-wrap">
              {info?.badges?.map(b => (
                <span key={b} className="font-mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'var(--green-bg)', color: 'var(--green-dim)' }}>{b}</span>
              ))}
              {a && (
                <>
                  <span className="font-mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}>
                    {a.tp} TP{a.time_stops > 0 ? ` · ${a.time_stops} TIME` : ''} · {a.sl} SL
                  </span>
                  {wr != null && <span className="font-mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}>WR {wr.toFixed(0)}%</span>}
                  {pnl != null && (
                    <span className="font-mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: pnl >= 0 ? 'var(--green-bg)' : 'var(--red-bg)', color: pnl >= 0 ? GREEN : RED }}>
                      {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)} $/sh
                    </span>
                  )}
                </>
              )}
            </div>
            {info?.desc && (
              <div className="mb-2 px-2.5 py-2 rounded-md bg-[var(--surface-2)]">
                <div className="font-mono text-[9px] tracking-widest uppercase mb-1" style={{ color: 'oklch(0.60 0.08 285)' }}>cómo funciona</div>
                <div className="text-[11px] leading-relaxed" style={{ color: 'var(--text-2)' }}>{info.desc}</div>
              </div>
            )}
            {info?.rule && <div className="text-[11px] leading-relaxed" style={{ color: 'var(--text-4)' }}>{info.rule}</div>}
          </div>
        )
      })}
      <div className="px-4 py-3 border-t border-[var(--border-soft)] font-mono text-[10px] leading-relaxed text-[var(--text-5)]">
        cero órdenes reales · outcomes resueltos en /post-close · promoción a live = decisión tuya
      </div>
    </div>
  )
}

// ─── Main ────────────────────────────────────────────────────────────────────

export default function SystemsCard({ ranking, registry, accum, trades }: {
  ranking:  StrategyRanking[]
  registry: StrategyRegistry[]
  accum:    ShadowAccum[]
  trades:   Trade[]
}) {
  const established = ranking.filter(r => r.tier === 'established').length
  const totalShadowN = accum.reduce((s, a) => s + a.n, 0)
  const archived = registry.filter(r => r.status === 'archived' || r.status === 'research').length

  return (
    <div>
      <div className="flex items-center gap-3 mb-2.5">
        <span className="font-mono text-[10px] font-semibold tracking-[0.16em] uppercase text-[var(--text-3)]">Sistemas</span>
        <span className="h-px flex-1 bg-[var(--border-soft)]" />
        <span className="font-mono text-[10px] text-[var(--text-5)]">{established} established · {totalShadowN} señales shadow · {archived} archivadas fuera de esta vista</span>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <LiveTable registry={registry} ranking={ranking} trades={trades} />
        <ShadowCards registry={registry} accum={accum} />
      </div>
    </div>
  )
}
