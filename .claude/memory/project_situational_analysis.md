---
name: project-situational-analysis
description: Skill /situational — análisis D-1 → D independiente del trading loop, solo informativo
metadata:
  type: project
---

Skill `/situational` agregado el 2026-06-01. **Independiente del loop Pulse** — no afecta entries/exits, solo emite tesis direccional.

**Why:** Usuario quería herramienta de análisis multi-día para detectar niveles probables de ser visitados hoy basado en estructura de ayer + desarrollo de hoy. Decisión: skill local manual, NO bloquea setups (informativo puro).

**How to apply:**
- Disparar manualmente con `/situational` cuando se quiera ver el sesgo D-1 → D.
- Útil pre-market (después de /pre-market), midday (12:00 ET), o pre-close (15:30 ET).
- Múltiples corridas/día son OK — cada una persiste un snapshot.

**Inputs:**
- `volume_profiles` (ayer) — requiere que post-close haya corrido o el slow path del pre-market.
- 5-min bars IEX del día actual.

**Output:**
- Tabla markdown con gap_type, range_structure, sesgo, targets, invalidación, confidence.
- Persiste en tabla `situational_analysis` (Supabase).

**Reglas de tesis (en orden de prioridad):**
1. Gap fill (gap outside rango ayer → mean reversion al rango)
2. Naked POC magnet (VPOC no tocado + cercano)
3. Higher-high exhaustion (HH + actual < midpoint)
4. Lower-low exhaustion (LL + actual > midpoint)
5. Inside day (rango actual <50% ayer → breakout próximo)
6. Expansion exhaustion (rango actual >1.5× ayer → mean revert VWAP)
7. Default neutral

**Schema `situational_analysis`:**
`session_date`, `symbol`, yesterday (close/high/low/vpoc/vah/val), today (open/high/low/current), `gap_type`, `range_structure`, `bias` (bullish/bearish/neutral/mixed), `confidence` (0-1), `target_levels` (jsonb), `invalidation`, `thesis`, `notes`.

**Restricciones permanentes:**
- NO modifica `session_state`.
- NO afecta `agent_status` ni el loop Pulse.
- Sin remoto, sin schedule cron — manual local-first ([[feedback-local-first]]).

Skill vive en `C:\Users\inaki\.claude\commands\situational.md` ([[ref-skills-repo]]).
