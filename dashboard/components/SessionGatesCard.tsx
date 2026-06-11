'use client'

import type { SessionStateRow } from '@/lib/supabase'

function GateTag({ label, on, detail }: { label: string; on: boolean | null; detail?: string }) {
  const cls =
    on === null
      ? 'bg-gray-800 text-gray-500'
      : on
        ? 'bg-emerald-900/50 text-emerald-400'
        : 'bg-red-900/30 text-red-400'
  const dot = on === null ? 'bg-gray-600' : on ? 'bg-emerald-400' : 'bg-red-500'
  return (
    <div className={`flex items-center gap-1.5 text-[11px] px-2 py-1 rounded font-medium ${cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
      <span>{label}</span>
      {detail && <span className="font-mono text-[10px] opacity-70">{detail}</span>}
    </div>
  )
}

function fmt(v: unknown, d = 2): string {
  const n = Number(v)
  return v == null || isNaN(n) ? '—' : n.toFixed(d)
}

export default function SessionGatesCard({ sessionState }: { sessionState: SessionStateRow | null }) {
  const st = sessionState?.state
  const g = st?.gates

  if (!st || !g) {
    return (
      <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest mb-2">
          Gates del día (v3.0)
        </p>
        <p className="text-sm text-gray-600">Sin sesión v3.0 hoy — se calculan a las 10:00/10:30 ET.</p>
      </div>
    )
  }

  const c4 = st.c4 ?? {}
  const fills = st.fvg?.fills_today ?? 0
  const pos = st.position

  const liveGates: { label: string; on: boolean | null; detail?: string }[] = [
    {
      label: 'S2 FVG',
      on: g.computed_10 ? (g.fvg_on ?? false) && fills < 1 : null,
      detail: g.rvol30 != null ? `rvol ${fmt(g.rvol30)}` : undefined,
    },
    {
      label: 'S3 VWAPPB',
      on: g.computed_1030 ? (g.vwappb_on ?? false) : null,
      detail: g.xvwap60 != null ? `xvwap ${g.xvwap60}` : undefined,
    },
    {
      label: 'S1 RSI2 (shadow)',
      on: g.computed_10 ? (g.rsi2_on ?? false) : null,
      detail: g.open_loc ?? undefined,
    },
    {
      label: 'S5 GAPF (shadow)',
      on: g.computed_10 ? (g.gapf_on ?? false) : null,
      detail: g.gap_pct != null ? `gap ${fmt(g.gap_pct)}%` : undefined,
    },
  ]

  const c4Entries = Object.entries(c4).filter(([, v]) => typeof v === 'number')

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
          Gates del día (v3.0) · {sessionState!.date}
        </p>
        <span className="text-[10px] text-gray-600 font-mono">
          QQQ {fmt(st.QQQ?.last_close)} · VWAP {fmt(st.QQQ?.vwap)}
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-3">
        {liveGates.map(t => (
          <GateTag key={t.label} label={t.label} on={t.on} detail={t.detail} />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-500 border-t border-gray-800/60 pt-3">
        <span>
          FVG fills hoy: <span className="font-mono text-gray-300">{fills}/1</span>
        </span>
        {c4Entries.length > 0 && (
          <span>
            C4:{' '}
            {c4Entries.map(([k, v]) => (
              <span key={k} className={`font-mono mr-1.5 ${Number(v) >= 2 ? 'text-red-400' : 'text-gray-300'}`}>
                {k} {String(v)}/2
              </span>
            ))}
          </span>
        )}
        <span>
          Posición:{' '}
          <span className="font-mono text-gray-300">
            {pos ? `${String((pos as Record<string, unknown>).sys ?? '?')} ${String((pos as Record<string, unknown>).qty ?? '')}sh` : 'flat'}
          </span>
        </span>
      </div>
    </div>
  )
}
