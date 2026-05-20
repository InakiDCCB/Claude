import { NextRequest, NextResponse } from 'next/server'
import { alpacaHeaders, checkSecret } from '../_shared'

export const revalidate = 0

// GET /api/alpaca/bars?symbol=QQQ&timeframe=5Min&limit=100&secret=TOKEN
export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams
  const denied = checkSecret(p.get('secret'))
  if (denied) return denied

  const symbol    = p.get('symbol')
  const timeframe = p.get('timeframe') ?? '5Min'
  const limit     = p.get('limit')     ?? '100'

  if (!symbol) return NextResponse.json({ error: 'symbol required' }, { status: 400 })

  const url = `https://data.alpaca.markets/v2/stocks/${symbol}/bars?timeframe=${timeframe}&limit=${limit}&feed=sip&sort=asc`

  try {
    const res = await fetch(url, { headers: alpacaHeaders() })
    if (!res.ok) return NextResponse.json({ error: 'Alpaca error' }, { status: 502 })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ error: 'Network error' }, { status: 503 })
  }
}
