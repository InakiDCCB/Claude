import { NextRequest, NextResponse } from 'next/server'
import { createSupabaseAdmin } from '@/lib/supabase'
import { checkSecret } from '@/lib/auth'

export const revalidate = 0

const ALPACA_BASE = 'https://paper-api.alpaca.markets/v2'
const UNIVERSE   = new Set(['QQQ'])

type AlpacaOrder = {
  id: string
  symbol: string
  side: 'buy' | 'sell'
  status: string
  filled_qty: string
  filled_avg_price: string
  filled_at: string | null
  type: string
}

export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams
  const authError = checkSecret(p.get('secret'))
  if (authError) return authError

  const dateParam = p.get('date')
  const dateStr   = dateParam ?? new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' })
  const after     = `${dateStr}T13:30:00Z`
  const until     = `${dateStr}T20:05:00Z`

  const headers = {
    'APCA-API-KEY-ID':     process.env.ALPACA_API_KEY!,
    'APCA-API-SECRET-KEY': process.env.ALPACA_SECRET_KEY!,
  }

  const res = await fetch(
    `${ALPACA_BASE}/orders?status=closed&after=${after}&until=${until}&direction=asc&limit=100`,
    { headers, cache: 'no-store' }
  )
  if (!res.ok) return NextResponse.json({ error: `Alpaca ${res.status}` }, { status: 502 })

  const orders: AlpacaOrder[] = await res.json()
  const filled = orders.filter(o => o.status === 'filled' && UNIVERSE.has(o.symbol) && o.filled_at)
  const buys   = filled.filter(o => o.side === 'buy')
  const sells  = filled.filter(o => o.side === 'sell')

  if (sells.length === 0) return NextResponse.json({ ok: true, reconciled: 0, date: dateStr })

  const sb = createSupabaseAdmin()
  const { data: existing } = await sb
    .from('trades')
    .select('order_id')
    .gte('created_at', `${dateStr}T00:00:00Z`)
    .lte('created_at', `${dateStr}T23:59:59Z`)
  const existingIds = new Set((existing ?? []).map((r: { order_id: string | null }) => r.order_id).filter(Boolean))

  // If the buy order ID is already in Supabase, the agent logged it correctly — skip those sells
  const loggedBuyIds = new Set(buys.map(b => b.id).filter(id => existingIds.has(id)))

  const eodStart = new Date(`${dateStr}T19:55:00Z`).getTime()
  const eodEnd   = new Date(`${dateStr}T20:05:00Z`).getTime()
  const rows: Record<string, unknown>[] = []

  for (const sell of sells) {
    if (existingIds.has(sell.id)) continue

    const sellTime = new Date(sell.filled_at!).getTime()
    const matchBuy = buys
      .filter(b => b.symbol === sell.symbol && new Date(b.filled_at!).getTime() < sellTime)
      .sort((a, b) => new Date(b.filled_at!).getTime() - new Date(a.filled_at!).getTime())[0]

    if (!matchBuy) continue
    if (loggedBuyIds.has(matchBuy.id)) continue

    const entryPrice = Number(matchBuy.filled_avg_price)
    const exitPrice  = Number(sell.filled_avg_price)
    const qty        = Number(sell.filled_qty)
    const pnl        = Math.round((exitPrice - entryPrice) * qty * 100) / 100

    let exit_type: 'TP' | 'SL' | 'TIME' | 'MANUAL' = 'MANUAL'
    if (sell.type === 'limit') exit_type = 'TP'
    else if (sell.type === 'stop' || sell.type === 'stop_limit') exit_type = 'SL'
    else if (sellTime >= eodStart && sellTime <= eodEnd) exit_type = 'TIME'

    rows.push({
      asset:      sell.symbol,
      side:       'buy',
      quantity:   qty,
      price:      entryPrice,
      filled_at:  matchBuy.filled_at,
      exit_price: exitPrice,
      exit_type,
      pnl,
      status:     'filled',
      strategy:   'Pulse-v2.4',
      order_id:   sell.id,
      notes:      `reconciled; buy_order=${matchBuy.id}`,
    })
  }

  if (rows.length === 0) return NextResponse.json({ ok: true, reconciled: 0, date: dateStr })

  const { error } = await sb.from('trades').upsert(rows, { onConflict: 'order_id' })
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  return NextResponse.json({
    ok:         true,
    reconciled: rows.length,
    date:       dateStr,
    trades:     rows.map(r => ({ asset: r.asset, qty: r.quantity, pnl: r.pnl, exit_type: r.exit_type })),
  })
}
