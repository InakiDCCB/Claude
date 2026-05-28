'use client'

import { useEffect, useState } from 'react'

type MarketEvent = {
  date: string         // ISO yyyy-mm-dd
  label: string
  type: 'holiday' | 'early_close'
  closeTime?: string   // for early closes, e.g. "13:00 ET"
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
  const target = new Date(dateStr + 'T00:00:00-05:00').getTime()
  const now    = Date.now()
  return Math.ceil((target - now) / (1000 * 60 * 60 * 24))
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00-05:00')
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'America/New_York' })
}

export default function MarketCalendarCard() {
  const [now, setNow] = useState<Date | null>(null)

  useEffect(() => {
    setNow(new Date())
    const t = setInterval(() => setNow(new Date()), 60_000)
    return () => clearInterval(t)
  }, [])

  if (!now) return null

  const today = now.toISOString().slice(0, 10)
  const upcoming = NYSE_2026
    .filter(e => e.date >= today)

  return (
    <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-4 h-full flex flex-col">
      <div className="flex items-baseline justify-between mb-3">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Market Calendar</h3>
        <span className="text-[10px] text-gray-600">NYSE 2026</span>
      </div>

      {upcoming.length === 0 ? (
        <p className="text-[11px] text-gray-500">No upcoming holidays this year.</p>
      ) : (
        <ul className="space-y-1.5 flex-1">
          {upcoming.map(e => {
            const dleft = daysUntil(e.date)
            const isToday = dleft === 0
            return (
              <li key={e.date} className="flex items-center justify-between gap-2 py-1 border-b border-gray-800/50 last:border-0">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                      e.type === 'holiday' ? 'bg-red-400' : 'bg-amber-400'
                    }`} />
                    <span className="text-[11px] text-gray-200 truncate">{e.label}</span>
                  </div>
                  {e.type === 'early_close' && (
                    <span className="text-[9px] text-amber-500/80 ml-3.5">
                      Closes {e.closeTime}
                    </span>
                  )}
                </div>
                <div className="text-right flex-shrink-0">
                  <div className="text-[10px] font-mono text-gray-400">{formatDate(e.date)}</div>
                  <div className={`text-[9px] font-mono ${
                    isToday ? 'text-emerald-400' : 'text-gray-600'
                  }`}>
                    {isToday ? 'TODAY' : `in ${dleft}d`}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}

      <div className="mt-3 pt-2 border-t border-gray-800/50 flex items-center gap-3 text-[9px] text-gray-600">
        <span className="flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-red-400" /> Closed
        </span>
        <span className="flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" /> Early close
        </span>
      </div>
    </div>
  )
}
