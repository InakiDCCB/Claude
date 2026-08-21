'use client'

import { useEffect, useState } from 'react'
import type { AgentStatus } from '@/lib/supabase'

const STATUS_DOT: Record<AgentStatus['status'], string> = {
  running:      'bg-emerald-400',
  idle:         'bg-gray-600',
  error:        'bg-red-400',
  disconnected: 'bg-orange-400',
}

type MarketEvent = {
  date: string
  label: string
  type: 'holiday' | 'early_close'
  closeTime?: string
}

// NYSE 2026 calendar — full closures and 1:00 PM ET early closes
const NYSE_2026: MarketEvent[] = [
  { date: '2026-01-01', label: "New Year's Day",          type: 'holiday' },
  { date: '2026-01-19', label: 'Martin Luther King Jr. Day', type: 'holiday' },
  { date: '2026-02-16', label: "Presidents' Day",         type: 'holiday' },
  { date: '2026-04-03', label: 'Good Friday',             type: 'holiday' },
  { date: '2026-05-25', label: 'Memorial Day',            type: 'holiday' },
  { date: '2026-06-19', label: 'Juneteenth',              type: 'holiday' },
  { date: '2026-07-03', label: 'Independence Day (obs.)', type: 'holiday' },
  { date: '2026-09-07', label: 'Labor Day',               type: 'holiday' },
  { date: '2026-11-26', label: 'Thanksgiving Day',        type: 'holiday' },
  { date: '2026-11-27', label: 'Day after Thanksgiving',  type: 'early_close', closeTime: '13:00 ET' },
  { date: '2026-12-24', label: 'Christmas Eve',           type: 'early_close', closeTime: '13:00 ET' },
  { date: '2026-12-25', label: 'Christmas Day',           type: 'holiday' },
]

function daysUntil(dateStr: string): number {
  return Math.ceil((new Date(dateStr + 'T00:00:00-05:00').getTime() - Date.now()) / (1000 * 60 * 60 * 24))
}

export default function InfraFooter({ agents }: { agents: AgentStatus[] }) {
  const [today, setToday] = useState<string | null>(null)
  useEffect(() => { setToday(new Date().toISOString().slice(0, 10)) }, [])

  const nextEvents = today ? NYSE_2026.filter(e => e.date >= today).slice(0, 2) : []

  return (
    <div className="border-t border-gray-800/60 pt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px]">
      {agents.length > 0 && (
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-gray-700 uppercase tracking-widest text-[9px]">Agentes</span>
          {agents.map(a => (
            <span key={a.id} className="flex items-center gap-1.5 text-gray-500" title={a.description ?? undefined}>
              <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[a.status] ?? STATUS_DOT.idle}`} />
              {a.name}
            </span>
          ))}
        </div>
      )}

      {nextEvents.length > 0 && (
        <div className="flex items-center gap-3 flex-wrap ml-auto">
          <span className="text-gray-700 uppercase tracking-widest text-[9px]">Calendario NYSE</span>
          {nextEvents.map(e => {
            const d = daysUntil(e.date)
            return (
              <span key={e.date} className="text-gray-500">
                <span className={e.type === 'holiday' ? 'text-red-400/80' : 'text-amber-400/80'}>●</span>{' '}
                {e.label} · {d === 0 ? 'hoy' : `en ${d}d`}
              </span>
            )
          })}
        </div>
      )}
    </div>
  )
}
