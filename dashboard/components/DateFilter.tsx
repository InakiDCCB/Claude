'use client'

import { useRouter } from 'next/navigation'
import { useTransition } from 'react'

export default function DateFilter({ from, to }: { from: string; to: string }) {
  const router = useRouter()
  const [pending, start] = useTransition()

  function update(key: 'from' | 'to', value: string) {
    const params = new URLSearchParams({ from, to, [key]: value })
    start(() => router.push(`/?${params}`))
  }

  return (
    <div className={`flex items-center gap-2 text-sm transition-opacity ${pending ? 'opacity-50' : ''}`}>
      <input
        type="date"
        defaultValue={from}
        onChange={e => update('from', e.target.value)}
        className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-gray-300 text-sm focus:outline-none focus:ring-1 focus:ring-gray-600"
      />
      <span className="text-gray-600">–</span>
      <input
        type="date"
        defaultValue={to}
        onChange={e => update('to', e.target.value)}
        className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-gray-300 text-sm focus:outline-none focus:ring-1 focus:ring-gray-600"
      />
      {pending && <span className="text-xs text-gray-600 animate-pulse">cargando…</span>}
    </div>
  )
}
