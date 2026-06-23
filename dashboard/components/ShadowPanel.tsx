'use client'

import type { ShadowSignal, StrategyRegistry } from '@/lib/supabase'

// strategy_id canónico -> código `sys` que usa shadow_signals
const ID_TO_SYS: Record<string, string> = {
  rsi2_v3: 'RSI2', swp_v3: 'SWP', gapf_v3: 'GAPF', swp_short_v3: 'SWPS', ob_v3: 'OB',
}

const STATUS_STYLE: Record<string, string> = {
  live:     'bg-emerald-500/15 text-emerald-400',
  shadow:   'bg-indigo-500/15 text-indigo-300',
  archived: 'bg-gray-700/40 text-gray-500',
  research: 'bg-gray-700/40 text-gray-500',
}

export default function ShadowPanel({ signals, registry }: { signals: ShadowSignal[]; registry: StrategyRegistry[] }) {
  const shadows = registry.filter(s => s.status === 'shadow')
    .sort((a, b) => a.strategy_id.localeCompare(b.strategy_id))
  const days = [...new Set(signals.map(s => s.session_date))].sort()

  // señales agrupadas por sys (ya vienen ordenadas created_at desc desde page.tsx)
  const bySys = new Map<string, ShadowSignal[]>()
  for (const s of signals) {
    const k = s.sys ?? '?'
    bySys.set(k, [...(bySys.get(k) ?? []), s])
  }

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
          Shadow validation · estrategias en validación
        </p>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-900/40 text-indigo-300 border border-indigo-800/40 font-semibold">
          día {Math.min(days.length, 5)}/5
        </span>
      </div>

      {shadows.length === 0 ? (
        <p className="text-sm text-gray-600">Sin estrategias en shadow.</p>
      ) : (
        <div className="space-y-0">
          {shadows.map(s => {
            const sys = ID_TO_SYS[s.strategy_id] ?? s.strategy_id
            const list = bySys.get(sys) ?? []
            const lats = list.map(x => x.latency_s).filter((x): x is number => x != null)
            const latAvg = lats.length ? lats.reduce((a, b) => a + b, 0) / lats.length : null
            const last = list[0]
            return (
              <div key={s.strategy_id} className="border-t border-gray-800/40 py-2 first:border-0 first:pt-0">
                <div className="flex items-baseline justify-between gap-3 text-[12px]">
                  <div className="min-w-0">
                    <span className="text-gray-200 font-medium">{s.name}</span>
                    {s.direction === 'short' && <span className="ml-1 text-[9px] text-red-400">SHORT</span>}
                    <span className={`ml-2 px-1.5 py-px rounded text-[9px] uppercase font-semibold ${STATUS_STYLE[s.status] ?? ''}`}>{s.status}</span>
                    {s.family && <span className="ml-2 text-[10px] text-gray-600">{s.family}</span>}
                  </div>
                  <div className="shrink-0 font-mono text-[11px] text-gray-400 text-right">
                    {list.length === 0
                      ? <span className="text-gray-600">sin señales aún</span>
                      : <>
                          {list.length} señal{list.length === 1 ? '' : 'es'}
                          {latAvg != null && <span className="text-gray-500"> · lat {latAvg.toFixed(0)}s</span>}
                          {last?.entry != null && <span className="text-gray-600"> · últ ${last.entry.toFixed(2)}</span>}
                        </>}
                  </div>
                </div>
                {s.notes && <p className="text-[10.5px] text-gray-500 mt-1 leading-snug">{s.notes}</p>}
              </div>
            )
          })}
          <p className="text-[10px] text-gray-600 border-t border-gray-800/60 pt-2 mt-1 leading-relaxed">
            Cada estrategia en <span className="text-indigo-300">shadow</span> loggea señales (entry/SL/TP) SIN órdenes.
            Outcomes (TP/SL/TIME) los resuelve /post-close. Promoción a live = decisión del usuario tras validación.
          </p>
        </div>
      )}
    </div>
  )
}
