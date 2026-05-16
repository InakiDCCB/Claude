import type { ChampionConfig, Trade } from '@/lib/supabase'

export function IncomingSlot() {
  return (
    <div className="rounded-xl border border-dashed border-gray-800 bg-gray-950/40 p-5 flex flex-col items-center justify-center gap-3 min-h-[220px]">
      <div className="w-10 h-10 rounded-full border-2 border-dashed border-gray-700 flex items-center justify-center">
        <svg className="w-4 h-4 text-gray-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path d="M12 5v14M5 12h14" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <div className="text-center">
        <p className="text-[11px] font-semibold text-gray-600 uppercase tracking-widest">Próximo campeón</p>
        <p className="text-[10px] text-gray-700 mt-1 font-mono">Incoming</p>
      </div>
    </div>
  )
}

function Row({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-[3px]">
      <span className="text-[11px] text-gray-500 shrink-0">{label}</span>
      <span className={`text-[11px] text-gray-200 text-right ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  )
}

function Tag({ label, active = true }: { label: string; active?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium
      ${active ? 'bg-emerald-900/50 text-emerald-400' : 'bg-gray-800 text-gray-500'}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-emerald-400' : 'bg-gray-600'}`} />
      {label}
    </span>
  )
}

function safeStr(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'number') return String(v)
  if (typeof v === 'string') return v
  if (Array.isArray(v)) return (v as unknown[]).map(String).join(', ')
  return JSON.stringify(v)
}

function safeNum(v: unknown, decimals = 2): string {
  if (v == null) return '—'
  const n = Number(v)
  return isNaN(n) ? '—' : n.toFixed(decimals)
}

function safeStringArray(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is string => typeof x === 'string')
}

function safeRecord(v: unknown): Record<string, unknown> {
  if (v != null && typeof v === 'object' && !Array.isArray(v)) {
    return v as Record<string, unknown>
  }
  return {}
}

export default function ChampionCard({ champion, trades: tradeLedger = [], isBestPerformer = false }: { champion: ChampionConfig | null; trades?: Trade[]; isBestPerformer?: boolean }) {
  if (!champion) return null

  const c       = champion.config
  const perf    = safeRecord(c.performance)
  const rules   = safeRecord(c.rules)
  const sizing  = safeRecord(c.position_sizing)

  const perfTrades = Number(perf.trades  ?? 0)
  const wins       = Number(perf.wins    ?? 0)
  const losses     = Number(perf.losses  ?? 0)
  const hitRate    = perf.hit_rate != null
    ? Number(perf.hit_rate)
    : perfTrades > 0 ? wins / perfTrades : null

  // P&L real: suma neta de todos los trades cerrados en el ledger de Supabase
  const closedTrades = tradeLedger.filter(t => t.pnl != null)
  const realPnl      = closedTrades.reduce((s, t) => s + (t.pnl ?? 0), 0)
  const totalPnl     = closedTrades.length > 0 ? realPnl : Number(perf.total_pnl ?? 0)

  const hasPerf  = perfTrades > 0 || closedTrades.length > 0
  const pnlColor = totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'

  const name      = safeStr(c.name      ?? c.strategy  ?? 'Estrategia')
  const version   = c.version != null   ? `v${safeStr(c.version)}`  : ''
  const assets    = safeStr(c.assets    ?? c.symbol    ?? '—')
  const timeframe = safeStr(c.timeframe ?? '—')
  const notes     = typeof c.notes === 'string' ? c.notes : ''

  const entryLong  = safeStringArray(rules.entry_long)
  const avoidRules = safeStringArray(rules.avoid)

  const riskPerTrade   = sizing.risk_per_trade_usd   != null ? safeNum(sizing.risk_per_trade_usd, 0)   : ''
  const maxDailyLoss   = sizing.max_daily_loss_usd   != null ? safeNum(sizing.max_daily_loss_usd, 0)   : ''
  const stopLossLabel  = typeof rules.stop_loss  === 'string' ? rules.stop_loss  : ''
  const takeProfitLbl  = typeof rules.take_profit === 'string' ? rules.take_profit : ''

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
              Estrategia Activa
            </p>
            {isBestPerformer && (
              <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-amber-900/40 text-amber-400 border border-amber-800/40 font-semibold">
                ★ Mejor rendimiento
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-white font-semibold">{name}</span>
            {version && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 font-mono">
                {version}
              </span>
            )}
            <span className="text-[10px] text-gray-600 font-mono">{assets}</span>
          </div>
        </div>

        {hasPerf ? (
          <div className="shrink-0 text-right">
            <p className={`text-lg font-mono font-semibold ${pnlColor}`}>
              {totalPnl >= 0 ? '+' : ''}${safeNum(totalPnl)}
            </p>
            <p className="text-[10px] text-gray-500">
              {hitRate != null ? `${(hitRate * 100).toFixed(0)}% hit` : '—'} · {closedTrades.length > 0 ? closedTrades.length : perfTrades}T
            </p>
          </div>
        ) : (
          <div className="shrink-0 text-right">
            <p className="text-[11px] text-gray-600">Sin trades aún</p>
            <p className="text-[10px] text-gray-700">Aprendiendo…</p>
          </div>
        )}
      </div>

      {/* Params */}
      <div className="space-y-0.5 mb-3">
        <Row label="Timeframe"  value={timeframe} />
        <Row label="Trades"     value={`${wins}W / ${losses}L`} />
        {riskPerTrade  && <Row label="Riesgo/trade"   value={`$${riskPerTrade}`} />}
        {maxDailyLoss  && <Row label="Max pérdida día" value={`$${maxDailyLoss}`} />}
        {stopLossLabel && <Row label="Stop loss"       value={stopLossLabel} mono={false} />}
        {takeProfitLbl && <Row label="Take profit"     value={takeProfitLbl} mono={false} />}
      </div>

      {/* Entry rules */}
      {entryLong.length > 0 && (
        <div className="mb-2">
          <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider mb-1.5">
            Condiciones entrada
          </p>
          <div className="flex flex-wrap gap-1">
            {entryLong.map((r, i) => <Tag key={i} label={r} />)}
          </div>
        </div>
      )}

      {/* Avoid rules */}
      {avoidRules.length > 0 && (
        <div className="mt-2">
          <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider mb-1.5">
            Evitar
          </p>
          <div className="flex flex-wrap gap-1">
            {avoidRules.map((r, i) => <Tag key={i} label={r} active={false} />)}
          </div>
        </div>
      )}

      {/* Notes */}
      {notes && (
        <p className="mt-3 text-[11px] text-gray-600 leading-relaxed border-t border-gray-800/60 pt-3">
          {notes}
        </p>
      )}
    </div>
  )
}
