import { NextRequest, NextResponse } from 'next/server'
import { BASE, alpacaHeaders, checkSecret } from '../../_shared'

export const revalidate = 0

// GET /api/alpaca/orders/[id]?secret=TOKEN
export async function GET(req: NextRequest, { params }: { params: { id: string } }) {
  const denied = checkSecret(req.nextUrl.searchParams.get('secret'))
  if (denied) return denied

  try {
    const res = await fetch(`${BASE}/orders/${params.id}`, { headers: alpacaHeaders() })
    if (!res.ok) return NextResponse.json({ error: 'Alpaca error' }, { status: 502 })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ error: 'Network error' }, { status: 503 })
  }
}
