import { NextResponse } from 'next/server'

export const BASE = 'https://paper-api.alpaca.markets/v2'

export const alpacaHeaders = () => ({
  'APCA-API-KEY-ID':     process.env.ALPACA_API_KEY!,
  'APCA-API-SECRET-KEY': process.env.ALPACA_SECRET_KEY!,
  'Content-Type':        'application/json',
})

export function checkSecret(secret: string | null): NextResponse | null {
  if (secret !== process.env.AGENT_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }
  return null
}
