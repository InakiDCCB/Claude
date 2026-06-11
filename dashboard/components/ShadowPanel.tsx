'use client'

import type { ShadowSignal } from '@/lib/supabase'

const SYS_LABEL: Record<string, string> = {
  RSI2: 'S1 · RSI2-dip',
  SWP: 'S4 · Sweep&Reclaim',
  GAPF: 'S5 · GapFill',
}

const TARGET_HIT: Record<string, string> = {
  RSI2: '~76%',
  SWP: '~70%',
  GAPF: '~50%',
}

export default function ShadowPanel({ signals }: { signals: ShadowSignal[] }) {
  const days = [...new Set(signals.map(s => s.session_date))].sort()
  const bySys = new Map<string, ShadowSignal[]>()
  for (const s of signals) {
    const k = s.sys ?? '?'
    bySys.set(k, [...(bySys.get(k) ?? []), s])
  }

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
          Shadow validation · sistemas nuevos
        </p>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-900/40 text-indigo-300 border border-indigo-800/40 font-semibold">
          día {Math.min(days.length, 5)}/5
        </span>
      </div>

      {signals.length === 0 ? (
        <p className="text-sm text-gray-600">
          Sin señales shadow todavía — el loop las loggea desde la primera sesión v3.0; /post-close resuelve los outcomes.
        </p>
      ) : (
        <div className="space-y-3">
          {[...bySys.entries()].sort().map(([sys, list]) => {
            const lats = list.map(s => s.latency_s).filter((x): x is number => x != null)
            const latAvg = lats.length ? lats.reduce((a, b) => a + b, 0) / lats.length : null
            const latMax = lats.length ? Math.max(...lats) : null
            const latOk = latMax == null || latMax <= 30
            const last = list[0]
            return (
              <div key={sys} className="flex items-baseline justify-between gap-3 text-[12px]">
                <div className="min-w-0">
                  <span className="text-gray-200 font-medium">{SYS_LABEL[sys] ?? sys}</span>
                  <span className="text-gray-600 ml-2 text-[11px]">
                    target hit {TARGET_HIT[sys] ?? '—'}
                  </span>
                </div>
                <div className="shrink-0 font-mono text-[11px] text-gray-400">
                  {list.length} señal{list.length === 1 ? '' : 'es'}
                  {latAvg != null && (
                    <span className={latOk ? 'text-emerald-400' : 'text-red-400'}>
                      {' '}· lat {latAvg.toFixed(0)}s (max {latMax!.toFixed(0)}s)
                    </span>
                  )}
                  {last?.entry != null && (
                    <span className="text-gray-600"> · últ ${last.entry.toFixed(2)}</span>
                  )}
                </div>
              </div>
            )
          })}
          <p className="text-[10px] text-gray-600 border-t border-gray-800/60 pt-2">
            Outcomes (TP/SL/TIME/MISS) los resuelve /post-close y quedan en session_memory.observations.
            Latencia objetivo &lt;30s del sello 5-min. Veredicto en la sesión 5.
          </p>
        </div>
      )}
    </div>
  )
}
