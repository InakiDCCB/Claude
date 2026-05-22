import { NextRequest, NextResponse } from 'next/server'
import { createSupabaseAdmin } from '../../../../lib/supabase'
import { checkSecret } from '../../../../lib/auth'

export const revalidate = 0

// GET /api/db/log?asset=QQQ&timeframe=5m&signal=neutral&confidence=70&indicators={}&thesis=text&secret=TOKEN
export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams
  const denied = checkSecret(p.get('secret'))
  if (denied) return denied

  const asset     = p.get('asset')
  const timeframe = p.get('timeframe') ?? '5m'
  const signal    = p.get('signal')    ?? 'neutral'
  const thesis    = p.get('thesis')    ?? ''

  if (!asset) return NextResponse.json({ error: 'asset required' }, { status: 400 })

  const confidence  = p.get('confidence') ? Number(p.get('confidence')) : null
  const indRaw      = p.get('indicators')
  const indicators  = indRaw ? JSON.parse(decodeURIComponent(indRaw)) : null

  const { error } = await createSupabaseAdmin()
    .from('analysis_log')
    .insert({ asset, timeframe, signal, confidence, indicators, thesis })

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ ok: true })
}
