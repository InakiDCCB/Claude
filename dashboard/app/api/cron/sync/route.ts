import { NextRequest, NextResponse } from 'next/server'
import { syncAlpacaState } from '../../../../lib/alpaca-sync'

export const revalidate = 0

// Called by Vercel Cron every minute (configured in vercel.json).
// Vercel injects Authorization: Bearer CRON_SECRET automatically.
export async function GET(req: NextRequest) {
  const auth = req.headers.get('authorization')
  if (auth !== `Bearer ${process.env.CRON_SECRET}`) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const result = await syncAlpacaState()
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 502 })
  return NextResponse.json(result)
}
