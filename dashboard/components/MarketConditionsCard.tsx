'use client'

import type { MarketCondition } from '@/lib/supabase'

const BADGE: Record<string, string> = {
  high: 'bg-sky-500/15 text-sky-300',
  low:  'bg-gray-700/40 text-gray-400',
}

export default function MarketConditionsCard({ conditions }: { conditions: MarketCondition[] }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
      <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest mb-3">
        Condiciones de mercado · QQQ
      </p>
      {conditions.length === 0 ? (
        <p className="text-sm text-gray-600">Sin sesiones clasificadas todavía.</p>
      ) : (
        <div className="space-y-1.5">
          {conditions.map(c => (
            <div key={c.session_date} className="flex items-center gap-2 text-[11px]">
              <span className="font-mono text-gray-500 w-10 shrink-0">{c.session_date.slice(5)}</span>
              <div className="flex items-center gap-1 flex-wrap">
                {c.liquidity && <span className={`px-1.5 py-px rounded text-[9px] ${BADGE[c.liquidity]}`}>liq {c.liquidity}</span>}
                {c.volatility && <span className={`px-1.5 py-px rounded text-[9px] ${BADGE[c.volatility]}`}>vol {c.volatility}</span>}
                {c.regime && <span className="px-1.5 py-px rounded text-[9px] bg-gray-700/40 text-gray-400">{c.regime}</span>}
              </div>
              <span className="font-mono text-gray-600 ml-auto shrink-0">
                rvol {c.rvol30 != null ? c.rvol30.toFixed(2) : '—'}
              </span>
            </div>
          ))}
          <p className="text-[10px] text-gray-600 border-t border-gray-800/60 pt-2 mt-2 leading-relaxed">
            Liquidez = rvol30 ≷ 0.85 · Volatilidad = rango vs mediana · régimen por xvwap60.
            El ranking se evalúa también por condición.
          </p>
        </div>
      )}
    </div>
  )
}
