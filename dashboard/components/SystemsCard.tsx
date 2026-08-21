'use client'

import type { StrategyRanking, StrategyRegistry, ShadowAccum, ShadowSignal } from '@/lib/supabase'

// strategy_id canónico -> código `sys` que usa shadow_signals / v_shadow_accumulated
const ID_TO_SYS: Record<string, string> = {
  rsi2_v3: 'RSI2', fvg_v3: 'FVG',
  gt_closelow_v2: 'GTCLV2',
}

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

// Barra segmentada TP / SL / TIME — proporción de outcomes resueltos (solo shadow)
function OutcomeBar({ tp, sl, time }: { tp: number; sl: number; time: number }) {
  const total = tp + sl + time
  if (total === 0) return null
  const seg = (n: number) => `${(n / total) * 100}%`
  return (
    <div className="flex h-1.5 w-full rounded-full overflow-hidden bg-gray-800 max-w-[160px]">
      {tp   > 0 && <div className="bg-emerald-500" style={{ width: seg(tp) }} title={`TP ${tp}`} />}
      {time > 0 && <div className="bg-amber-400"   style={{ width: seg(time) }} title={`TIME ${time}`} />}
      {sl   > 0 && <div className="bg-red-500"     style={{ width: seg(sl) }} title={`SL ${sl}`} />}
    </div>
  )
}

type Row = {
  strategy_id: string
  name:        string
  status:      'live' | 'shadow' | 'archived' | 'research'
  direction:   'long' | 'short'
  notes:       string | null
  ranking:     StrategyRanking | null
  accum:       ShadowAccum | null
  pendingSignals: number
}

function TableRow({ r }: { r: Row }) {
  const s = r.ranking?.score ?? null
  const scoreColor = s == null ? 'text-gray-600' : s >= 65 ? 'text-emerald-400' : s >= 45 ? 'text-amber-400' : 'text-red-400'
  const wr  = r.accum?.wr_pct != null ? Number(r.accum.wr_pct) : null
  const pnl = r.accum?.pnl_sh != null ? Number(r.accum.pnl_sh) : null

  return (
    <>
      <tr className="border-t border-gray-800/60">
        <td className="py-1.5 pr-2">
          <span className="text-gray-200 font-medium">{r.name}</span>
          {r.direction === 'short' && <span className="ml-1 text-[9px] text-red-400">SHORT</span>}
          <span className={`ml-2 px-1.5 py-px rounded text-[9px] uppercase font-semibold ${STATUS_STYLE[r.status] ?? ''}`}>{r.status}</span>
        </td>
        <td className="py-1.5 px-2 text-right font-mono text-gray-400">{r.ranking?.n ?? '—'}</td>
        <td className="py-1.5 px-2 text-right font-mono text-gray-400">{r.ranking?.wr != null ? `${r.ranking.wr.toFixed(0)}%` : '—'}</td>
        <td className="py-1.5 px-2 text-right font-mono text-gray-400">{r.ranking?.pf != null ? r.ranking.pf.toFixed(2) : '—'}</td>
        <td className={`py-1.5 px-2 text-right font-mono ${r.ranking?.exp_lb != null && r.ranking.exp_lb >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
          {r.ranking?.exp_lb != null ? `${r.ranking.exp_lb >= 0 ? '+' : ''}${r.ranking.exp_lb.toFixed(2)}` : '—'}
        </td>
        <td className="py-1.5 px-2 text-center">
          {r.ranking && <span className={`px-1.5 py-px rounded text-[9px] border ${TIER_STYLE[r.ranking.tier] ?? ''}`}>{TIER_LABEL[r.ranking.tier] ?? r.ranking.tier}</span>}
        </td>
        <td className={`py-1.5 pl-2 text-right font-mono font-semibold ${scoreColor}`}>{s != null ? s.toFixed(1) : '—'}</td>
      </tr>

      {r.status === 'shadow' && (
        <tr className="border-t border-gray-800/20">
          <td colSpan={7} className="pb-2 pt-0.5">
            {r.accum ? (
              <div className="flex items-center gap-2 flex-wrap">
                <OutcomeBar tp={r.accum.tp} sl={r.accum.sl} time={r.accum.time_stops} />
                <span className="text-[10px] font-mono text-gray-600 whitespace-nowrap">
                  <span className="text-emerald-500">{r.accum.tp} TP</span>
                  {r.accum.time_stops > 0 && <span className="text-amber-500"> · {r.accum.time_stops} TIME</span>}
                  <span className="text-red-500"> · {r.accum.sl} SL</span>
                  {r.accum.miss > 0 && <span> · {r.accum.miss} miss</span>}
                  {wr != null && <span className={wr >= 55 ? 'text-emerald-400' : wr >= 45 ? 'text-amber-400' : 'text-red-400'}> · WR {wr.toFixed(0)}%</span>}
                  {pnl != null && <span className={pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}> · {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)} $/sh</span>}
                </span>
                {r.notes && <span className="text-[10px] text-gray-600 italic">— {r.notes}</span>}
              </div>
            ) : (
              <p className="text-[10.5px] text-gray-600">
                {r.pendingSignals > 0 ? `${r.pendingSignals} señal${r.pendingSignals === 1 ? '' : 'es'} · sin outcome aún` : 'sin señales aún'}
                {r.notes && <span> — {r.notes}</span>}
              </p>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

export default function SystemsCard({ ranking, registry, accum, signals }: {
  ranking:  StrategyRanking[]
  registry: StrategyRegistry[]
  accum:    ShadowAccum[]
  signals:  ShadowSignal[]
}) {
  const rankingById = new Map(ranking.map(r => [r.strategy_id, r]))
  const accumById   = new Map(accum.map(a => [a.strategy_id, a]))
  const signalsBySys = new Map<string, number>()
  for (const sig of signals) {
    const k = sig.sys ?? '?'
    signalsBySys.set(k, (signalsBySys.get(k) ?? 0) + 1)
  }

  const rows: Row[] = registry.map(reg => {
    const sys = ID_TO_SYS[reg.strategy_id] ?? reg.strategy_id
    return {
      strategy_id: reg.strategy_id,
      name:        reg.name,
      status:      reg.status,
      direction:   reg.direction,
      notes:       reg.notes,
      ranking:     rankingById.get(reg.strategy_id) ?? null,
      accum:       accumById.get(reg.strategy_id) ?? null,
      pendingSignals: signalsBySys.get(sys) ?? 0,
    }
  })

  const current  = rows.filter(r => r.status === 'live' || r.status === 'shadow')
    .sort((a, b) => (a.status === b.status ? a.strategy_id.localeCompare(b.strategy_id) : a.status === 'live' ? -1 : 1))
  const legacy   = rows.filter(r => r.status === 'archived' || r.status === 'research')
    .sort((a, b) => a.strategy_id.localeCompare(b.strategy_id))
  const established = ranking.filter(r => r.tier === 'established').length
  const totalShadowN = accum.reduce((s, a) => s + a.n, 0)

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
          Sistemas · QQQ
        </p>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-800 text-gray-400 border border-gray-700/50 font-semibold">
            {established} established
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-900/40 text-indigo-300 border border-indigo-800/40 font-semibold">
            {totalShadowN} señales shadow
          </span>
        </div>
      </div>

      {current.length === 0 ? (
        <p className="text-sm text-gray-600">Sin sistemas live/shadow registrados.</p>
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
              {current.map(r => <TableRow key={r.strategy_id} r={r} />)}
            </tbody>
          </table>

          {legacy.length > 0 && (
            <details className="mt-3 group">
              <summary className="text-[10px] text-gray-600 cursor-pointer hover:text-gray-400 select-none">
                + {legacy.length} legacy / archivadas (fuera del universo operativo actual)
              </summary>
              <table className="w-full text-[12px] mt-1 opacity-70">
                <tbody>
                  {legacy.map(r => <TableRow key={r.strategy_id} r={r} />)}
                </tbody>
              </table>
            </details>
          )}

          <p className="text-[10px] text-gray-600 border-t border-gray-800/60 pt-2 mt-3 leading-relaxed">
            Score = 0.45·calidad(PF + WR Wilson) + 0.25·exp_lb + 0.30·robustez − drawdown. Sólo se puntúa con n≥20.
            Shadow: señales computadas con precios exactos, CERO órdenes — outcomes resueltos por /post-close
            (fuente: v_shadow_accumulated). Promoción a live = decisión del usuario tras validación.
          </p>
        </>
      )}
    </div>
  )
}
