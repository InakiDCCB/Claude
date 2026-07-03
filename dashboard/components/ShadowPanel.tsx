'use client'

import type { ShadowSignal, ShadowAccum, StrategyRegistry } from '@/lib/supabase'

// strategy_id canónico -> código `sys` que usa shadow_signals
const ID_TO_SYS: Record<string, string> = {
  rsi2_v3: 'RSI2', swp_v3: 'SWP', gapf_v3: 'GAPF', swp_short_v3: 'SWPS', ob_v3: 'OB',
  gt_rsi2d_v1: 'GTR2D', gt_3down_v1: 'GT3D',
}

const STATUS_STYLE: Record<string, string> = {
  live:     'bg-emerald-500/15 text-emerald-400',
  shadow:   'bg-indigo-500/15 text-indigo-300',
  archived: 'bg-gray-700/40 text-gray-500',
  research: 'bg-gray-700/40 text-gray-500',
}

// Barra segmentada TP / SL / TIME — proporción de outcomes resueltos
function OutcomeBar({ tp, sl, time }: { tp: number; sl: number; time: number }) {
  const total = tp + sl + time
  if (total === 0) return null
  const seg = (n: number) => `${(n / total) * 100}%`
  return (
    <div className="flex h-1.5 w-full rounded-full overflow-hidden bg-gray-800">
      {tp   > 0 && <div className="bg-emerald-500" style={{ width: seg(tp) }} title={`TP ${tp}`} />}
      {time > 0 && <div className="bg-amber-400"   style={{ width: seg(time) }} title={`TIME ${time}`} />}
      {sl   > 0 && <div className="bg-red-500"     style={{ width: seg(sl) }} title={`SL ${sl}`} />}
    </div>
  )
}

export default function ShadowPanel({ signals, accum, registry }: {
  signals: ShadowSignal[]; accum: ShadowAccum[]; registry: StrategyRegistry[]
}) {
  const shadows = registry.filter(s => s.status === 'shadow')
    .sort((a, b) => a.strategy_id.localeCompare(b.strategy_id))

  // acumulados por strategy_id (fuente C.4: v_shadow_accumulated)
  const accumById = new Map(accum.map(a => [a.strategy_id, a]))

  // señales del rango visible agrupadas por sys (ordenadas created_at desc desde page.tsx)
  const bySys = new Map<string, ShadowSignal[]>()
  for (const s of signals) {
    const k = s.sys ?? '?'
    bySys.set(k, [...(bySys.get(k) ?? []), s])
  }

  const totalN = accum.reduce((s, a) => s + a.n, 0)

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
          Shadow validation · outcomes acumulados
        </p>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-900/40 text-indigo-300 border border-indigo-800/40 font-semibold">
          {totalN} señales resueltas
        </span>
      </div>

      {shadows.length === 0 ? (
        <p className="text-sm text-gray-600">Sin estrategias en shadow.</p>
      ) : (
        <div className="space-y-0">
          {shadows.map(s => {
            const sys  = ID_TO_SYS[s.strategy_id] ?? s.strategy_id
            const a    = accumById.get(s.strategy_id) ?? null
            const list = bySys.get(sys) ?? []
            const wr   = a?.wr_pct != null ? Number(a.wr_pct) : null
            const pnl  = a?.pnl_sh != null ? Number(a.pnl_sh) : null
            return (
              <div key={s.strategy_id} className="border-t border-gray-800/40 py-2.5 first:border-0 first:pt-0">
                <div className="flex items-baseline justify-between gap-3 text-[12px]">
                  <div className="min-w-0">
                    <span className="text-gray-200 font-medium">{s.name}</span>
                    {s.direction === 'short' && <span className="ml-1 text-[9px] text-red-400">SHORT</span>}
                    <span className={`ml-2 px-1.5 py-px rounded text-[9px] uppercase font-semibold ${STATUS_STYLE[s.status] ?? ''}`}>{s.status}</span>
                    {s.family && <span className="ml-2 text-[10px] text-gray-600">{s.family}</span>}
                  </div>
                  <div className="shrink-0 font-mono text-[11px] text-right">
                    {a ? (
                      <>
                        <span className="text-gray-300">{a.n} señal{a.n === 1 ? '' : 'es'}</span>
                        <span className="text-gray-600"> · {a.sessions} ses</span>
                        {wr != null && (
                          <span className={`ml-2 font-semibold ${wr >= 55 ? 'text-emerald-400' : wr >= 45 ? 'text-amber-400' : 'text-red-400'}`}>
                            WR {wr.toFixed(0)}%
                          </span>
                        )}
                        {pnl != null && (
                          <span className={`ml-2 ${pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)} $/sh
                          </span>
                        )}
                      </>
                    ) : list.length > 0 ? (
                      <span className="text-gray-500">{list.length} señal{list.length === 1 ? '' : 'es'} · sin outcome aún</span>
                    ) : (
                      <span className="text-gray-600">sin señales aún</span>
                    )}
                  </div>
                </div>

                {a && (
                  <div className="flex items-center gap-2 mt-1.5">
                    <OutcomeBar tp={a.tp} sl={a.sl} time={a.time_stops} />
                    <span className="text-[10px] font-mono text-gray-600 shrink-0 whitespace-nowrap">
                      <span className="text-emerald-500">{a.tp} TP</span>
                      {a.time_stops > 0 && <span className="text-amber-500"> · {a.time_stops} TIME</span>}
                      <span className="text-red-500"> · {a.sl} SL</span>
                      {a.miss > 0 && <span> · {a.miss} miss</span>}
                    </span>
                  </div>
                )}

                {s.notes && <p className="text-[10.5px] text-gray-500 mt-1 leading-snug">{s.notes}</p>}
              </div>
            )
          })}
          <p className="text-[10px] text-gray-600 border-t border-gray-800/60 pt-2 mt-1 leading-relaxed">
            Señales computadas con precios exactos, CERO órdenes. Outcomes los resuelve /post-close
            (fuente: <span className="text-gray-500">v_shadow_accumulated</span> — la misma que lee Market Intelligence).
            P&L en $/acción. Promoción a live = decisión del usuario tras validación.
          </p>
        </div>
      )}
    </div>
  )
}
