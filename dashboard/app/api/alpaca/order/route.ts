import { NextRequest, NextResponse } from 'next/server'
import { BASE, alpacaHeaders, checkSecret } from '../_shared'

export const revalidate = 0

// GET /api/alpaca/order?symbol=QQQ&qty=5&side=buy&type=market&tif=day&secret=TOKEN
export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams
  const denied = checkSecret(p.get('secret'))
  if (denied) return denied

  const symbol = p.get('symbol')
  const qty    = p.get('qty')
  const side   = p.get('side')
  const type   = p.get('type') ?? 'market'
  const tif    = p.get('tif')  ?? 'day'

  if (!symbol || !qty || !side) {
    return NextResponse.json({ error: 'symbol, qty, side required' }, { status: 400 })
  }

  const body = JSON.stringify({ symbol, qty, side, type, time_in_force: tif })

  try {
    const res = await fetch(`${BASE}/orders`, {
      method:  'POST',
      headers: alpacaHeaders(),
      body,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      return NextResponse.json({ error: 'Alpaca error', detail: err }, { status: 502 })
    }
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ error: 'Network error' }, { status: 503 })
  }
}
