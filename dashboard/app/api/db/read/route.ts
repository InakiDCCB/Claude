import { NextRequest, NextResponse } from 'next/server'
import { createSupabase } from '../../../../lib/supabase'
import { checkSecret } from '../../alpaca/_shared'

export const revalidate = 0

// GET /api/db/read?table=session_memory&limit=3&secret=TOKEN
// GET /api/db/read?table=trades-today&secret=TOKEN
// GET /api/db/read?table=agent_status&name=pulse-v2&secret=TOKEN
export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams
  const denied = checkSecret(p.get('secret'))
  if (denied) return denied

  const table = p.get('table')
  const limit = Number(p.get('limit') ?? '50')
  const db    = createSupabase()

  try {
    if (table === 'session_memory') {
      const { data, error } = await db
        .from('session_memory')
        .select('session_date,regime,total_pnl,win_rate,observations,parameters,summary')
        .order('session_date', { ascending: false })
        .limit(limit)
      if (error) return NextResponse.json({ error: error.message }, { status: 500 })
      return NextResponse.json(data)
    }

    if (table === 'trades-today') {
      const today = new Date().toISOString().split('T')[0]
      const { data, error } = await db
        .from('trades')
        .select('id,asset,side,quantity,price,exit_price,pnl,status,order_id,notes,created_at')
        .gte('created_at', `${today}T00:00:00Z`)
        .order('created_at', { ascending: true })
      if (error) return NextResponse.json({ error: error.message }, { status: 500 })
      return NextResponse.json(data)
    }

    if (table === 'agent_status') {
      const name = p.get('name')
      let q = db.from('agent_status').select('*')
      if (name) q = q.eq('name', name)
      const { data, error } = await q.limit(limit)
      if (error) return NextResponse.json({ error: error.message }, { status: 500 })
      return NextResponse.json(data)
    }

    return NextResponse.json({ error: 'unknown table' }, { status: 400 })
  } catch {
    return NextResponse.json({ error: 'Server error' }, { status: 500 })
  }
}
