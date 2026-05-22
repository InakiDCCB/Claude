import { NextRequest, NextResponse } from 'next/server'
import { createSupabaseAdmin } from '../../../../lib/supabase'
import { checkSecret } from '../../../../lib/auth'

export const revalidate = 0

// GET /api/db/heartbeat?name=pulse-v2&status=idle&description=Market+closed&metadata={}&secret=TOKEN
export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams
  const denied = checkSecret(p.get('secret'))
  if (denied) return denied

  const name = p.get('name')
  if (!name) return NextResponse.json({ error: 'name required' }, { status: 400 })

  const status      = p.get('status')      ?? 'idle'
  const description = p.get('description') ?? ''
  const metaRaw     = p.get('metadata')
  const metadata    = metaRaw ? JSON.parse(decodeURIComponent(metaRaw)) : null

  const { error } = await createSupabaseAdmin()
    .from('agent_status')
    .upsert(
      { name, status, description, updated_at: new Date().toISOString(), metadata },
      { onConflict: 'name' }
    )

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ ok: true })
}
