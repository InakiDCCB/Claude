'use client'

import type { StrategyRanking } from '@/lib/supabase'

const TIER_STYLE: Record<string, string> = {
  established:       'bg-emerald-900/40 text-emerald-300 border-emerald-800/40',
  provisional:       'bg-amber-900/40 text-amber-300 border-amber-800/40',
  insufficient_data: 'bg-gray-800 text-gray-500 border-gray-700/50',
}
const TIER_LABEL: Record<string, string> = {
  established:       'established',
  provisional:       'provisional',
  insufficient_data: 'sin muestra',
}
const STATUS_STYLE: Record<string, string> = {
  live:     'bg-emerald-500/15 text-emerald-400',
  shadow:   'bg-indigo-500/15 text-indigo-300',
  archived: 'bg-gray-700/40 text-gray-500',
  research: 'bg-gray-700/40 text-gray-500',
}

function Row({ r }: { r: StrategyRanking }) {
  const s = r.score
  const scoreColor = s == null ? 'text-gray-600' : s >= 65 ? 'text-emerald-400' : s >= 45 ? 'text-amber-400' : 'text-red-400'
  return (
    <tr className="border-t border-gray-800/60">
      <td className="py-1.5 pr-2">
        <span className="text-gray-200 font-medium">{r.strategy_id}</span>
        {r.direction === 'short' && <span className="ml-1 text-[9px] text-red-400">SHORT</span>}
        <span className={`ml-2 px-1.5 py-px rounded text-[9px] uppercase font-semibold ${STATUS_STYLE[r.status] ?? ''}`}>{r.status}</span>
      </td>
      <td className="py-1.5 px-2 text-right font-mono text-gray-400">{r.n}</td>
      <td className="py-1.5 px-2 text-right font-mono text-gray-400">{r.wr != null ? `${r.wr.toFixed(0)}%` : '—'}</td>
      <td className="py-1.5 px-2 text-right font-mono text-gray-400">{r.pf != null ? r.pf.toFixed(2) : '—'}</td>
      <td className={`py-1.5 px-2 text-right font-mono ${r.exp_lb != null && r.exp_lb >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
        {r.exp_lb != null ? `${r.exp_lb >= 0 ? '+' : ''}${r.exp_lb.toFixed(2)}` : '—'}
      </td>
      <td className="py-1.5 px-2 text-center">
        <span className={`px-1.5 py-px rounded text-[9px] border ${TIER_STYLE[r.tier] ?? ''}`}>{TIER_LABEL[r.tier] ?? r.tier}</span>
      </td>
      <td className={`py-1.5 pl-2 text-right font-mono font-semibold ${scoreColor}`}>{s != null ? s.toFixed(1) : '—'}</td>
    </tr>
  )
}

export default function StrategyRankingCard({ ranking }: { ranking: StrategyRanking[] }) {
  const current = ranking.filter(r => r.status === 'live' || r.status === 'shadow')
  const legacy  = ranking.filter(r => r.status === 'archived' || r.status === 'research')
  const established = ranking.filter(r => r.tier === 'established').length

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
          Ranking de estrategias · QQQ
        </p>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-800 text-gray-400 border border-gray-700/50 font-semibold">
          {established} established
        </span>
      </div>

      {ranking.length === 0 ? (
        <p className="text-sm text-gray-600">
          Sin snapshot todavía — /post-close recalcula el ranking cada sesión (refresh_strategy_performance).
        </p>
      ) : (
        <>
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-[9px] uppercase tracking-wider text-gray-600">
                <th className="text-left font-medium pb-1">Estrategia</th>
                <th className="text-right font-medium pb-1 px-2">n</th>
                <th className="text-right font-medium pb-1 px-2">WR</th>
                <th className="text-right font-medium pb-1 px-2">PF</th>
                <th className="text-right font-medium pb-1 px-2">exp_lb</th>
                <th className="text-center font-medium pb-1 px-2">tier</th>
                <th className="text-right font-medium pb-1 pl-2">score</th>
              </tr>
            </thead>
            <tbody>
              {current.length > 0
                ? current.map(r => <Row key={r.strategy_id} r={r} />)
                : <tr><td colSpan={7} className="py-2 text-gray-600 text-[11px]">Sin sistemas live/shadow en el snapshot.</td></tr>}
            </tbody>
          </table>

          {legacy.length > 0 && (
            <details className="mt-3 group">
              <summary className="text-[10px] text-gray-600 cursor-pointer hover:text-gray-400 select-none">
                + {legacy.length} legacy / archivadas (fuera del universo operativo actual)
              </summary>
              <table className="w-full text-[12px] mt-1 opacity-70">
                <tbody>
                  {legacy.map(r => <Row key={r.strategy_id} r={r} />)}
                </tbody>
              </table>
            </details>
          )}

          <p className="text-[10px] text-gray-600 border-t border-gray-800/60 pt-2 mt-3 leading-relaxed">
            Score = 0.45·calidad(PF + WR Wilson) + 0.25·exp_lb + 0.30·robustez − drawdown.
            Sólo se puntúa con n≥20; <span className="text-gray-500">sin muestra</span> = aún no concluible.
            exp_lb = expectancy lower-bound ($/acción). DEPLOY≥65 · PAPER≥45 · KILLED&lt;45.
          </p>
        </>
      )}
    </div>
  )
}
