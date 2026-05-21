import { NextRequest, NextResponse } from 'next/server'
import { createSupabase } from '../../../../lib/supabase'
import { checkSecret, BASE, alpacaHeaders } from '../../alpaca/_shared'

export const revalidate = 0

// GET /api/db/sync-alpaca?secret=TOKEN
// Fetches current Alpaca account + positions and writes to alpaca_state table.
// Call from any external cron (e.g. cron-job.org) every minute during market hours.
export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams
  const denied = checkSecret(p.get('secret'))
  if (denied) return denied

  const [accountRes, positionsRes] = await Promise.all([
    fetch(`${BASE}/account`,   { headers: alpacaHeaders(), cache: 'no-store' }),
    fetch(`${BASE}/positions`, { headers: alpacaHeaders(), cache: 'no-store' }),
  ])

  if (!accountRes.ok) {
    return NextResponse.json({ error: `Alpaca account ${accountRes.status}` }, { status: 502 })
  }

  const account   = await accountRes.json()
  const positions = positionsRes.ok ? await positionsRes.json() : []

  const row = {
    key:           'current',
    synced_at:     new Date().toISOString(),
    equity:        Number(account.equity)          || null,
    cash:          Number(account.cash)            || null,
    buying_power:  Number(account.buying_power)    || null,
    day_pl:        Number(account.equity) - Number(account.last_equity) || null,
    unrealized_pl: Array.isArray(positions)
      ? positions.reduce((s: number, p: { unrealized_pl?: string }) => s + Number(p.unrealized_pl ?? 0), 0)
      : null,
    positions: Array.isArray(positions)
      ? positions.map((p: {
          symbol: string
          qty: string
          avg_entry_price: string
          current_price: string
          market_value: string
          unrealized_pl: string
          unrealized_plpc: string
        }) => ({
          symbol:       p.symbol,
          qty:          Number(p.qty),
          avg_entry:    Number(p.avg_entry_price),
          price:        Number(p.current_price),
          market_value: Number(p.market_value),
          pl:           Number(p.unrealized_pl),
          pl_pct:       Number(p.unrealized_plpc),
        }))
      : [],
  }

  const { error } = await createSupabase()
    .from('alpaca_state')
    .upsert(row, { onConflict: 'key' })

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  return NextResponse.json({
    ok:           true,
    synced_at:    row.synced_at,
    equity:       row.equity,
    day_pl:       row.day_pl,
    unrealized_pl: row.unrealized_pl,
    positions:    row.positions,
  })
}
