import type { Metadata } from 'next'
import { IBM_Plex_Sans, IBM_Plex_Mono } from 'next/font/google'
import './globals.css'

const plexSans = IBM_Plex_Sans({ subsets: ['latin'], weight: ['400', '500', '600'], variable: '--font-sans' })
const plexMono = IBM_Plex_Mono({ subsets: ['latin'], weight: ['400', '500', '600', '700'], variable: '--font-mono' })

export const metadata: Metadata = {
  title: 'Trading Dashboard',
  description: 'Paper trading monitor — Alpaca + Supabase',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className={`${plexSans.variable} ${plexMono.variable} font-sans bg-[var(--surface-0)] text-[var(--text-1)] min-h-screen antialiased`}>
        {children}
      </body>
    </html>
  )
}
