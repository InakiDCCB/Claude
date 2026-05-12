import { NextResponse } from 'next/server'

const HDR = (key: string, secret: string) => ({
  'APCA-API-KEY-ID': key,
  'APCA-API-SECRET-KEY': secret,
})

export async function GET() {
  const key    = process.env.ALPACA_API_KEY!
  const secret = process.env.ALPACA_SECRET_KEY!

  try {
    const [accountRes, positionsRes] = await Promise.all([
      fetch('https://paper-api.alpaca.markets/v2/account',   { headers: HDR(key, secret), next: { revalidate: 30 } }),
      fetch('https://paper-api.alpaca.markets/v2/positions', { headers: HDR(key, secret), next: { revalidate: 30 } }),
    ])

    if (!accountRes.ok) return NextResponse.json({ error: 'Alpaca error' }, { status: 502 })

    const account   = await accountRes.json()
    const positions = positionsRes.ok ? await positionsRes.json() : []

    return NextResponse.json({
      ...account,
      positions_count: Array.isArray(positions) ? positions.length : 0,
    })
  } catch {
    return NextResponse.json({ error: 'Network error' }, { status: 503 })
  }
}
