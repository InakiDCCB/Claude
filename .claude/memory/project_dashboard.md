---
name: project-dashboard
description: Dashboard Next.js en Vercel — monitoreo de agentes, trades, calendar NYSE, cron sync cada minuto
metadata:
  type: project
---

**URL producción:** https://dashboard-two-pi-65.vercel.app
**Vercel project:** `inakidccb-2430s-projects/dashboard` (id `prj_DYG3kXvQh2qCgt3i9b33H0IBaoYe`), Root Directory configurado como `dashboard`.
**Código:** subdirectorio `dashboard/` del repo Trading.
**Supabase:** [[ref-supabase]] (`rdenehqcxgvffyvlwvba`).

## Stack
Next.js 14.2.35 (App Router) · React 18 · Recharts 2.13 · `@supabase/supabase-js` 2.46 · Tailwind. Server components fetchean Supabase en paralelo; client components manejan interactividad.

## Layout (6 niveles)
1. **Portfolio · Cash · Market Value** → `AccountSummary` (lee `alpaca_state`)
2. **Hit Ratio · P&L · Avg P&L** → `HitRatioGauge` + `DollarPnL` + `StatCard`
3. **Top Performers · Live Positions** → `TopPerformers` + `LivePositions`
4. **Agent + Strategy + Market Calendar** → `AgentGrid` + `ChampionCard` + `MarketCalendarCard`
   - Grid `lg:grid-cols-3`: Agent+Strategy en `lg:col-span-2`, MarketCalendar en columna derecha (`lg:h-full`).
5. **Trades · P&L chart · Analysis Log** → `DataTabs`

## Componentes clave
- `TradingPanel.tsx` — root client; suscripciones Supabase Realtime (`trades-live`, `agents-live`); toasts.
- `MarketCalendarCard.tsx` (2026-05-27) — NYSE 2026 holidays + early closes hardcoded; client component con `useEffect` para hidratación.
- `MarketStatus.tsx` — reloj ET en vivo, countdown cierre, ping `/api/ping` cada 30s.
- `ChampionCard.tsx` — lee `champion_strategy`; muestra `additional_entries.fvg_v1` desde 2026-05-27.
- `DataTabs.tsx` — tabs (Trades · P&L · Analysis Log · CSV export) con live badge.

## Rutas API
| Ruta | Función | Auth |
|---|---|---|
| `GET /api/account` | Proxy Alpaca account + positions (legacy) | — |
| `GET /api/ping` | Health check `{ts}` | — |
| `GET /api/cron/sync` | Sync Alpaca → `alpaca_state` cada minuto | Bearer `CRON_SECRET` |
| `GET /api/db/sync-alpaca` | Sync Alpaca manual | `?secret=AGENT_SECRET` |
| `GET /api/db/heartbeat` | Upsert `agent_status` | `?secret` |
| `GET /api/db/log` | Insert `analysis_log` | `?secret` |
| `GET /api/db/trade` | Insert trade entry | `?secret` |
| `GET /api/db/trade-exit` | Update trade exit | `?secret` |
| `GET /api/db/read` | Read `session_memory` / trades-today | `?secret` |
| `GET /api/db/memory` | Insert `session_memory` | `?secret` |
| `GET /api/db/reconcile-trades` | Reconcilia trades faltantes desde Alpaca al cierre | `?secret` |

Todas las rutas `/api/db/*` usan `createSupabaseAdmin()` (service_role) — RLS está activo con `anon=SELECT only`. Schema completo y grants en `supabase/schema.sql`.

## Sync Alpaca → Supabase
**cron-job.org** job `7640778` llama cada minuto a `/api/cron/sync`. Mantiene `alpaca_state` (single row `key='current'`) con equity, cash, day_pl, unrealized_pl, positions[].

## Env vars (Vercel + `.env.local`)
`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `AGENT_SECRET`, `CRON_SECRET`.

## Deploy
GitHub-Vercel integration. Push a `main` → auto-deploy. Si build falla con "Couldn't find pages or app directory" → verificar Root Directory = `dashboard`.
