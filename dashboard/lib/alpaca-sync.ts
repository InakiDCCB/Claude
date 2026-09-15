import { createSupabaseAdmin } from './supabase'

const ALPACA_BASE = 'https://paper-api.alpaca.markets/v2'

function alpacaHeaders() {
  return {
    'APCA-API-KEY-ID':     process.env.ALPACA_API_KEY!,
    'APCA-API-SECRET-KEY': process.env.ALPACA_SECRET_KEY!,
    'Content-Type':        'application/json',
  }
}

export type SyncResult = {
  ok:           boolean
  synced_at?:   string
  equity?:      number | null
  cash?:        number | null
  buying_power?: number | null
  day_pl?:      number | null
  unrealized_pl?: number | null
  positions?:   AlpacaSyncPosition[]
  error?:       string
}

export type AlpacaSyncPosition = {
  symbol:       string
  qty:          number
  avg_entry:    number
  price:        number
  market_value: number
  pl:           number
  pl_pct:       number
}

type AlpacaRawPosition = {
  symbol:           string
  qty:              string
  avg_entry_price:  string
  current_price:    string
  market_value:     string
  unrealized_pl:    string
  unrealized_plpc:  string
}

// Pure fetch — no Supabase write. Used by the dashboard (page.tsx) to read
// account+positions straight from Alpaca on every page load, instead of via
// the alpaca_state table (which depends on the external cron staying alive —
// it silently went stale for 11 days, 2026-09-04→09-15, before this split).
export async function fetchAlpacaState(): Promise<SyncResult> {
  const [accountRes, positionsRes] = await Promise.all([
    fetch(`${ALPACA_BASE}/account`,   { headers: alpacaHeaders(), next: { revalidate: 15 } }),
    fetch(`${ALPACA_BASE}/positions`, { headers: alpacaHeaders(), next: { revalidate: 15 } }),
  ])

  if (!accountRes.ok) return { ok: false, error: `Alpaca account ${accountRes.status}` }

  const account   = await accountRes.json()
  const rawPos: AlpacaRawPosition[] = positionsRes.ok ? await positionsRes.json() : []

  const positions: AlpacaSyncPosition[] = Array.isArray(rawPos)
    ? rawPos.map(p => ({
        symbol:       p.symbol,
        qty:          Number(p.qty),
        avg_entry:    Number(p.avg_entry_price),
        price:        Number(p.current_price),
        market_value: Number(p.market_value),
        pl:           Number(p.unrealized_pl),
        pl_pct:       Number(p.unrealized_plpc),
      }))
    : []

  const synced_at    = new Date().toISOString()
  const equity       = Number(account.equity)       || null
  const cash         = Number(account.cash)         || null
  const buying_power = Number(account.buying_power) || null
  const day_pl       = (Number(account.equity) - Number(account.last_equity)) || null
  const unrealized_pl = positions.reduce((s, p) => s + p.pl, 0)

  return { ok: true, synced_at, equity, cash, buying_power, day_pl, unrealized_pl, positions }
}

// Fetch + persist to alpaca_state (used by the cron + manual sync routes —
// kept for any consumer outside the dashboard and as a historical snapshot).
export async function syncAlpacaState(): Promise<SyncResult> {
  const result = await fetchAlpacaState()
  if (!result.ok) return result

  const { error } = await createSupabaseAdmin()
    .from('alpaca_state')
    .upsert(
      { key: 'current', synced_at: result.synced_at, equity: result.equity, cash: result.cash,
        buying_power: result.buying_power, day_pl: result.day_pl,
        unrealized_pl: result.unrealized_pl, positions: result.positions },
      { onConflict: 'key' }
    )

  if (error) return { ok: false, error: error.message }
  return result
}

export type DailyPnlPoint = { day: string; pnl: number; equity: number }

// Broker-truth daily P&L curve (Alpaca portfolio history), replacing the old
// approach of bucketing trades.pnl by day. That internal ledger carries ~$20
// of drift vs the real account (broker fees never logged in `trades`, plus a
// few pre-QQQ-only trades from May/June with hand-estimated exit prices) —
// this is the same "connect straight to Alpaca" fix as fetchAlpacaState,
// applied to the Performance panel's Net P&L / equity-curve chart.
export async function fetchAlpacaDailyPnl(): Promise<DailyPnlPoint[]> {
  const res = await fetch(
    `${ALPACA_BASE}/account/portfolio/history?timeframe=1D&period=1A`,
    { headers: alpacaHeaders(), next: { revalidate: 60 } }
  )
  if (!res.ok) return []

  const h = await res.json() as {
    timestamp?:   number[]
    equity?:      (number | null)[]
    profit_loss?: (number | null)[]
  }
  if (!Array.isArray(h.timestamp) || !Array.isArray(h.equity) || !Array.isArray(h.profit_loss)) return []

  const out: DailyPnlPoint[] = []
  for (let i = 0; i < h.timestamp.length; i++) {
    const eq = h.equity[i]
    const pl = h.profit_loss[i]
    // eq === 0 is Alpaca's pre-funding artifact on the account-creation instant
    // (equity briefly reads $0 before the initial deposit posts) — skip it, it
    // would otherwise show up as a single -$100,000 day.
    if (eq == null || eq === 0 || pl == null) continue
    const day = new Date(h.timestamp[i] * 1000).toLocaleDateString('en-CA', { timeZone: 'America/New_York' })
    out.push({ day, pnl: pl, equity: eq })
  }
  return out
}
