import { NextRequest, NextResponse } from 'next/server'
import { createSupabase } from '../../../../lib/supabase'
import { checkSecret } from '../../alpaca/_shared'

export const revalidate = 0

// GET /api/db/trade-exit?order_id=X&exit_price=710.00&pnl=21.00&exit_type=TP&secret=TOKEN
export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams
  const denied = checkSecret(p.get('secret'))
  if (denied) return denied

  const order_id   = p.get('order_id')
  const exit_price = p.get('exit_price')
  const pnl        = p.get('pnl')
  const exit_type  = p.get('exit_type') ?? 'TP'

  if (!order_id || !exit_price || !pnl) {
    return NextResponse.json({ error: 'order_id, exit_price, pnl required' }, { status: 400 })
  }

  const { error } = await createSupabase()
    .from('trades')
    .update({ exit_price: Number(exit_price), pnl: Number(pnl), exit_type, status: 'filled' })
    .eq('order_id', order_id)

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ ok: true })
}
