'use client'

import type { MarketContext, MarketPattern, MarketHypothesis, EmergingLabel, MarketIntel } from '@/lib/supabase'

// Color por etiqueta de contexto (taxonomía determinista; magnitude-only en gris).
const CTX_STYLE: Record<string, string> = {
  explosive:    'bg-red-500/15 text-red-300',
  directional:  'bg-emerald-500/15 text-emerald-300',
  range:        'bg-amber-500/15 text-amber-300',
  efficient:    'bg-sky-500/15 text-sky-300',
  mixed:        'bg-indigo-500/15 text-indigo-300',
  active:       'bg-gray-600/30 text-gray-300',
  slow:         'bg-gray-700/40 text-gray-400',
  unclassified: 'bg-gray-800/60 text-gray-600',
}

// nº de sesiones objetivo para que el motor "despierte" (gate de consolidación)
const WAKE_TARGET = 15

function CtxBadge({ label }: { label: string | null }) {
  const l = label ?? 'unclassified'
  return <span className={`px-1.5 py-px rounded text-[9px] uppercase font-semibold ${CTX_STYLE[l] ?? CTX_STYLE.unclassified}`}>{l}</span>
}

export default function MarketIntelligencePanel({
  intel, contexts, patterns, hypotheses, emerging,
}: {
  intel:      MarketIntel | null
  contexts:   MarketContext[]
  patterns:   MarketPattern[]
  hypotheses: MarketHypothesis[]
  emerging:   EmergingLabel[]
}) {
  const sessions   = intel?.sessions_classified ?? contexts.length
  const dormant    = (intel?.patterns_consolidated ?? 0) === 0 && (intel?.hypotheses_active ?? 0) === 0
  const csPatterns = patterns.filter(p => p.kind === 'context_strategy')
  const transitions = patterns.filter(p => p.kind === 'context_transition')
  const activeHyp  = hypotheses.filter(h => h.status === 'active' || h.status === 'observing' || h.status === 'consolidated')
  const discarded  = hypotheses.filter(h => h.status === 'discarded')
  // evolución reciente (cronológica ascendente para leer izquierda→derecha)
  const strip = [...contexts].sort((a, b) => a.session_date.localeCompare(b.session_date)).slice(-10)

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
          Market Intelligence · QQQ
        </p>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-800/60 text-gray-400 border border-gray-700/50 font-mono">
          {sessions}/{WAKE_TARGET} sesiones
        </span>
      </div>

      {/* Contexto actual + evolución reciente */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[11px] text-gray-500">Contexto:</span>
        <CtxBadge label={intel?.latest_context ?? null} />
        {intel?.dominant_recent && intel.dominant_recent !== intel.latest_context && (
          <span className="text-[10px] text-gray-600">· dominante reciente <span className="text-gray-400">{intel.dominant_recent}</span></span>
        )}
      </div>
      <div className="flex items-center gap-1 flex-wrap mb-3">
        {strip.map(c => (
          <span key={c.session_date} title={`${c.session_date} · ${c.context_label}`}>
            <CtxBadge label={c.context_label} />
          </span>
        ))}
      </div>

      {/* Hipótesis activas */}
      <Section title="Hipótesis activas">
        {activeHyp.length === 0
          ? <Empty>Ninguna — patrones aún en observación.</Empty>
          : activeHyp.map(h => (
            <div key={h.pattern_key} className="text-[11px] text-gray-300 leading-snug">
              <span className={`mr-1.5 px-1 py-px rounded text-[8px] uppercase ${h.status === 'active' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-gray-700/40 text-gray-400'}`}>{h.status}</span>
              {h.hypothesis}
              <span className="text-gray-600 font-mono"> · n={h.n_support}{h.n_contra > 0 ? `/−${h.n_contra}` : ''}</span>
            </div>
          ))}
      </Section>

      {/* Patrones detectados (context↔strategy) */}
      <Section title="Patrones detectados">
        {csPatterns.length === 0
          ? <Empty>Sin patrones todavía.</Empty>
          : csPatterns.slice(0, 6).map(p => (
            <div key={p.pattern_key} className="flex items-baseline gap-2 text-[11px]">
              <span className={`px-1 py-px rounded text-[8px] uppercase shrink-0 ${p.status === 'consolidated' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-gray-700/40 text-gray-500'}`}>{p.status}</span>
              <span className="text-gray-400 min-w-0">{p.description}</span>
            </div>
          ))}
        {transitions.length > 0 && (
          <p className="text-[10px] text-gray-600 mt-1">
            + {transitions.length} transición{transitions.length === 1 ? '' : 'es'} entre sesiones registradas.
          </p>
        )}
      </Section>

      {/* Comportamientos emergentes + descartadas */}
      {(emerging.length > 0 || discarded.length > 0) && (
        <Section title="Memoria acumulativa">
          {emerging.map(e => (
            <div key={e.candidate_label} className="text-[11px] text-gray-400">
              Nuevo: <span className="text-indigo-300">{e.candidate_label}</span>
              <span className="text-gray-600 font-mono"> · {e.n_sessions}× {e.recognized ? '(reconocido)' : '(observando)'}</span>
            </div>
          ))}
          {discarded.map(h => (
            <div key={h.pattern_key} className="text-[11px] text-gray-600 line-through decoration-gray-700">
              {h.hypothesis} <span className="no-underline">— {h.discarded_reason}</span>
            </div>
          ))}
        </Section>
      )}

      <p className="text-[10px] text-gray-600 border-t border-gray-800/60 pt-2 mt-3 leading-relaxed">
        {dormant
          ? <>Motor en <span className="text-gray-400">acumulación</span> — etiquetas de contexto deterministas desde métricas observables; patrones e hipótesis se activan al juntar ~{WAKE_TARGET} sesiones (gate min-N). </>
          : <>Patrones consolidados con evidencia repetible. </>}
        <span className="text-gray-500">Solo informa — nunca crea reglas ni toca el loop. Memoria acumulativa: nada se borra.</span>
      </p>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-gray-800/40 pt-2 mt-2 space-y-1">
      <p className="text-[9px] font-semibold text-gray-600 uppercase tracking-widest">{title}</p>
      {children}
    </div>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] text-gray-600">{children}</p>
}
