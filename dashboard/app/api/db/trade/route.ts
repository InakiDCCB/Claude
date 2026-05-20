import { NextRequest, NextResponse } from 'next/server'
import { createSupabase } from '../../../../lib/supabase'
import { checkSecret } from '../../alpaca/_shared'

export const revalidate = 0

// GET /api/db/trade?asset=QQQ&side=buy&qty=14&price=708.50&order_id=X&strategy=Pulse-v2.4&notes=text&secret=TOKEN
export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams
  const denied = checkSecret(p.get('secret'))
  if (denied) return denied

  const asset    = p.get('asset')
  const side     = p.get('side')
  const qty      = p.get('qty')
  const price    = p.get('price')

  if (!asset || !side || !qty || !price) {
    return NextResponse.json({ error: 'asset, side, qty, price required' }, { status: 400 })
  }

  const order_id  = p.get('order_id')  ?? null
  const strategy  = p.get('strategy')  ?? 'Pulse-v2.4'
  const notes     = p.get('notes')     ?? null

  const { data, error } = await createSupabase()
    .from('trades')
    .insert({
      asset,
      side,
      quantity: Number(qty),
      price:    Number(price),
      filled_at: new Date().toISOString(),
      order_id,
      status:   'filled',
      strategy,
      notes,
    })
    .select('id')
    .single()

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ ok: true, id: data?.id })
}
