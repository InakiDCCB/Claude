'use client'

import { useState, useTransition } from 'react'
import { toggleAgentStatus } from '@/app/actions'
import type { AgentStatus } from '@/lib/supabase'

const STATUS_CFG = {
  running: {
    dot:      'bg-emerald-400',
    ping:     true,
    label:    'Activo',
    text:     'text-emerald-400',
    bar:      'bg-emerald-500',
    btn:      'bg-red-500/10 text-red-400 hover:bg-red-500/20 border-red-500/20',
    btnLabel: 'Detener',
  },
  idle: {
    dot:      'bg-gray-600',
    ping:     false,
    label:    'Inactivo',
    text:     'text-gray-500',
    bar:      'bg-gray-600',
    btn:      'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border-emerald-500/20',
    btnLabel: 'Iniciar',
  },
  error: {
    dot:      'bg-red-400',
    ping:     false,
    label:    'Error',
    text:     'text-red-400',
    bar:      'bg-red-500',
    btn:      'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border-emerald-500/20',
    btnLabel: 'Reiniciar',
  },
} as const

function AgentCard({ agent }: { agent: AgentStatus }) {
  const [status, setStatus] = useState(agent.status)
  const [, start] = useTransition()
  const cfg = STATUS_CFG[status]

  const meta          = agent.metadata
  const progress      = meta != null && typeof meta['progress'] === 'number' ? (meta['progress'] as number) : null
  const progressLabel = meta != null && typeof meta['progress_label'] === 'string' ? (meta['progress_label'] as string) : null

  function toggle() {
    const next: AgentStatus['status'] = status === 'running' ? 'idle' : 'running'
    setStatus(next)
    start(() => toggleAgentStatus(agent.id, next))
  }

  return (
    <div className="bg-gray-900/50 border border-gray-800/60 rounded-xl p-4 flex flex-col gap-3 hover:border-gray-700/60 transition-colors">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="relative flex-shrink-0">
            <div className={`w-2.5 h-2.5 rounded-full ${cfg.dot}`} />
            {cfg.ping && (
              <div className={`absolute inset-0 w-2.5 h-2.5 rounded-full ${cfg.dot} animate-ping opacity-60`} />
            )}
          </div>
          <span className={`text-xs font-medium ${cfg.text}`}>{cfg.label}</span>
        </div>
        <button
          onClick={toggle}
          className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${cfg.btn}`}
        >
          {cfg.btnLabel}
        </button>
      </div>

      <div className="flex-1">
        <p className="text-sm font-medium text-gray-100 leading-tight">{agent.name}</p>
        {agent.description && (
          <p className="text-xs text-gray-500 mt-1 leading-snug">{agent.description}</p>
        )}
      </div>

      {progress !== null && (
        <div>
          <div className="flex justify-between items-center mb-1">
            <span className="text-[10px] text-gray-600">{progressLabel ?? 'Progreso'}</span>
            <span className="text-[10px] font-mono text-gray-500">{progress}%</span>
          </div>
          <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${cfg.bar}`}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      <p className="text-[10px] text-gray-700 font-mono">
        {new Date(agent.updated_at).toLocaleString('es-ES', {
          timeZone: 'America/New_York',
          month: 'short',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
        })}{' '}ET
      </p>
    </div>
  )
}

export default function AgentGrid({ agents }: { agents: AgentStatus[] }) {
  if (!agents.length) {
    return <p className="text-sm text-gray-600">No hay agentes registrados.</p>
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {agents.map(a => (
        <AgentCard key={a.id} agent={a} />
      ))}
    </div>
  )
}
