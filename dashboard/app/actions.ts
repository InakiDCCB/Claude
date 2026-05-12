'use server'

import { createClient } from '@supabase/supabase-js'
import { revalidatePath } from 'next/cache'

function sb() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}

export async function toggleAgentStatus(id: string, status: 'running' | 'idle' | 'error') {
  await sb()
    .from('agent_status')
    .update({ status, updated_at: new Date().toISOString() })
    .eq('id', id)
  revalidatePath('/')
}
