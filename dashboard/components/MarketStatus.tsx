'use client'

import { useEffect, useState } from 'react'

function isMarketOpen(): boolean {
  const et = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' }))
  const day = et.getDay()
  if (day === 0 || day === 6) return false
  const mins = et.getHours() * 60 + et.getMinutes()
  return mins >= 570 && mins < 960 // 9:30–16:00
}

function etClock(): string {
  return new Date().toLocaleTimeString('en-US', {
    timeZone: 'America/New_York',
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export default function MarketStatus() {
  const [open, setOpen]       = useState(false)
  const [time, setTime]       = useState('')
  const [latency, setLatency] = useState<number | null>(null)

  useEffect(() => {
    setOpen(isMarketOpen())
    setTime(etClock())

    const tick = setInterval(() => {
      setOpen(isMarketOpen())
      setTime(etClock())
    }, 1000)

    async function ping() {
      const t0 = performance.now()
      try {
        await fetch('/api/ping', { cache: 'no-store' })
        setLatency(Math.round(performance.now() - t0))
      } catch {
        setLatency(null)
      }
    }
    ping()
    const pingInterval = setInterval(ping, 30_000)

    return () => { clearInterval(tick); clearInterval(pingInterval) }
  }, [])

  return (
    <div className="flex items-center gap-2 flex-wrap justify-end">
      <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
        open
          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
          : 'bg-gray-800 text-gray-500 border-gray-700/40'
      }`}>
        <div className={`w-1.5 h-1.5 rounded-full ${open ? 'bg-emerald-400 animate-pulse' : 'bg-gray-600'}`} />
        {open ? 'Mercado abierto' : 'Mercado cerrado'}
      </div>

      {time && (
        <span className="text-xs text-gray-500 font-mono">
          {open ? 'Apertura' : 'Cierre'} {time}
        </span>
      )}

      {latency !== null && (
        <span className={`text-xs px-2 py-0.5 rounded font-mono border ${
          latency < 100
            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
            : latency < 300
            ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
            : 'bg-red-500/10 text-red-400 border-red-500/20'
        }`}>
          API {latency}ms
        </span>
      )}
    </div>
  )
}
