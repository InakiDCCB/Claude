import type { ChampionConfig } from '@/lib/supabase'

function pct(v: number, decimals = 2) {
  const sign = v > 0 ? '+' : ''
  return `${sign}${(v * 100).toFixed(decimals)}%`
}

function Tag({ on, label }: { on: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium
      ${on ? 'bg-emerald-900/50 text-emerald-400' : 'bg-gray-800 text-gray-500'}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${on ? 'bg-emerald-400' : 'bg-gray-600'}`} />
      {label}
    </span>
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

export default function ChampionCard({ champion }: { champion: ChampionConfig | null }) {
  if (!champion) return null

  const { config } = champion
  const { entry, exit: exitCfg, position, performance } = config

  const hasPerf  = performance.trades > 0 && performance.win_rate != null && performance.avg_pnl != null
  const pnlColor = hasPerf && (performance.avg_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'
  const missing  = Math.max(0, 100 - performance.trades)

  // Friendly version of the ID: strip timestamp noise after the base
  const displayId = config.id.length > 28
    ? `…${config.id.slice(-20)}`
    : config.id

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest mb-1">
            Estrategia Activa
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-white font-semibold">{config.strategy}</span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 font-mono">
              {config.symbol}
            </span>
            <span className="text-[10px] text-gray-600 font-mono truncate">
              {displayId}
            </span>
          </div>
        </div>

        {/* Performance badge */}
        {hasPerf ? (
          <div className="shrink-0 text-right">
            <p className={`text-lg font-mono font-semibold ${pnlColor}`}>
              {(performance.avg_pnl ?? 0) >= 0 ? '+' : ''}${(performance.avg_pnl ?? 0).toFixed(2)}
            </p>
            <p className="text-[10px] text-gray-500">
              {((performance.win_rate ?? 0) * 100).toFixed(0)}% win · {performance.trades}T
            </p>
          </div>
        ) : (
          <div className="shrink-0 text-right">
            <p className="text-[11px] text-gray-600">Sin performance</p>
            <p className="text-[10px] text-gray-700">{missing} trades más</p>
          </div>
        )}
      </div>

      {/* Params grid */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-0 text-sm">
        {/* Entry column */}
        <div>
          <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider mb-1">
            Entrada
          </p>
          <Row label="ORB mínimo"   value={pct(entry.orb_threshold_pct)} />
          <Row label="Velas ORB"    value={`${entry.orb_bars} × 5 min`} />
          <Row label="Gap QQQ"      value={`≥ ${pct(entry.qqq_gap_min_pct, 1)}`} />
          <Row label="Señal desde"  value={config.signal_asset} mono={false} />
          <div className="flex gap-1.5 mt-1.5">
            <Tag on={entry.use_regime}     label="Régimen" />
            <Tag on={entry.use_exhaustion} label="Agotamiento" />
          </div>
        </div>

        {/* Exit column */}
        <div>
          <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider mb-1">
            Salida
          </p>
          <Row label="Take Profit"   value="Máximo del ORB" mono={false} />
          <Row label="Stop Loss"     value={`Entrada − $${exitCfg.sl_value.toFixed(2)}`} />
          <Row label="Time stop"     value={`${exitCfg.time_stop_et} ET`} />
          <Row label="Tamaño máx."   value={`${position.max_shares} acc.`} />
        </div>
      </div>

      {/* How it works */}
      <p className="mt-4 text-[11px] text-gray-600 leading-relaxed border-t border-gray-800/60 pt-3">
        Espera que TQQQ rompa al alza en los primeros {entry.orb_bars * 5} min (≥&nbsp;{pct(entry.orb_threshold_pct)})
        con QQQ sin gap negativo.
        Si el régimen de mercado es momentum y no hay señal de agotamiento,
        entra al VWAP del ORB con TP en el máximo y SL a ${exitCfg.sl_value.toFixed(2)} de distancia.
        Cierra todo a las {exitCfg.time_stop_et} ET si no se alcanzó antes.
      </p>
    </div>
  )
}
