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

export async function syncAlpacaState(): Promise<SyncResult> {
  const [accountRes, positionsRes] = await Promise.all([
    fetch(`${ALPACA_BASE}/account`,   { headers: alpacaHeaders(), cache: 'no-store' }),
    fetch(`${ALPACA_BASE}/positions`, { headers: alpacaHeaders(), cache: 'no-store' }),
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

  const synced_at   = new Date().toISOString()
  const equity      = Number(account.equity)       || null
  const cash        = Number(account.cash)         || null
  const buying_power = Number(account.buying_power) || null
  const day_pl      = (Number(account.equity) - Number(account.last_equity)) || null
  const unrealized_pl = positions.reduce((s, p) => s + p.pl, 0)

  const { error } = await createSupabaseAdmin()
    .from('alpaca_state')
    .upsert(
      { key: 'current', synced_at, equity, cash, buying_power, day_pl, unrealized_pl, positions },
      { onConflict: 'key' }
    )

  if (error) return { ok: false, error: error.message }
  return { ok: true, synced_at, equity, day_pl, unrealized_pl, positions }
}
