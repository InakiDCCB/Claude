---
name: ref-supabase
description: Pointer al proyecto Supabase del sistema Trading — project_id y tablas relevantes
metadata:
  type: reference
---

**Project ID:** `rdenehqcxgvffyvlwvba` — usar en cualquier llamada `mcp__claude_ai_Supabase__*`.

**Tablas clave:**

| Tabla | Propósito |
|---|---|
| `trades` | Ledger de paper trades (entry, exit, P&L, `strategy` tag distingue `fvg_v1` de los demás) |
| `analysis_log` | Señales y lectura de indicadores por ciclo (JSONB `indicators`) |
| `session_state` | JSONB con el estado intra-día por símbolo (VWAP, EMAs, ATR, y desde v2.8 `yesterday_profile` / `naked_pocs` / `developing` con `volume_by_bin`) |
| `session_memory` | Resumen post-close por sesión (regime, P&L, win rate, observations) |
| `volume_profiles` | (v2.8, 2026-05-28) Snapshot por `(date, symbol)` con VPOC/VAH/VAL + day_high/low + session_close. Naked POC = SQL self-join contra `posterior.day_low/day_high` |
| `champion_strategy` | Config activa del agente (single row `key='current'`) — source of truth de parámetros |
| `alpaca_state` | Snapshot del account Alpaca, syncado cada minuto por Vercel cron |

Schema completo en `supabase/schema.sql` del repo Trading. Migraciones se aplican vía `mcp__claude_ai_Supabase__apply_migration` y se replican al archivo de schema para mantener source-of-truth.

**Dashboard:** `https://dashboard-two-pi-65.vercel.app/` — lee todas las tablas vía anon key.
