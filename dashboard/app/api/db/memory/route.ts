import { NextRequest, NextResponse } from 'next/server'
import { createSupabaseAdmin } from '../../../../lib/supabase'
import { checkSecret } from '../../../../lib/auth'

export const revalidate = 0

// GET /api/db/memory?regime=RANGE&assets=QQQ&total_pnl=63.69&win_rate=66.7&trade_count=6&observations={}&parameters={}&summary=text&secret=TOKEN
export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams
  const denied = checkSecret(p.get('secret'))
  if (denied) return denied

  const regime      = p.get('regime')
  const assetsRaw   = p.get('assets')
  const total_pnl   = p.get('total_pnl')
  const win_rate    = p.get('win_rate')
  const trade_count = p.get('trade_count')
  const summary     = p.get('summary') ?? ''

  if (!regime || !total_pnl) {
    return NextResponse.json({ error: 'regime and total_pnl required' }, { status: 400 })
  }

  const assets     = assetsRaw ? assetsRaw.split(',').map(s => s.trim()) : null
  const obsRaw     = p.get('observations')
  const paramsRaw  = p.get('parameters')
  const observations = obsRaw  ? JSON.parse(decodeURIComponent(obsRaw))  : null
  const parameters   = paramsRaw ? JSON.parse(decodeURIComponent(paramsRaw)) : null

  const today = new Date().toISOString().split('T')[0]

  const { error } = await createSupabaseAdmin()
    .from('session_memory')
    .insert({
      session_date: today,
      regime,
      assets,
      total_pnl:   Number(total_pnl),
      win_rate:    win_rate    ? Number(win_rate)    : null,
      trade_count: trade_count ? Number(trade_count) : null,
      observations,
      parameters,
      summary,
    })

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ ok: true })
}
