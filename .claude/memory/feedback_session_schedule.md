---
name: feedback-session-schedule
description: Horario de inicio de sesión de trading — pre-análisis 9:50 ET + loop 10:00 ET + passive 15:45 + forced close 15:55
metadata:
  type: feedback
---

La sesión de trading se inicia y cierra en fases fijas:

| Hora ET | Fase | Acción |
|---|---|---|
| 9:30–9:50 | Caótica | No trades. Recolectar datos para régimen. |
| 9:50 | Pre-análisis | Clasificar régimen tentativo (TREND/RANGE), seed VWAP/EMAs, [[ref-supabase]] `session_state`. Si quedó SGOV de la sesión anterior → vender todo aquí. |
| 10:00 | Loop activo | Arranca el ciclo Pulse v2.8 con `/loop`. Usa el estado del pre-análisis como seed. |
| 10:00–15:45 | Trading | Entradas + bracket management cada ~5 min. |
| 15:45 | Passive observation | No nuevos entries. Solo gestionar posiciones abiertas y log observations. |
| 15:55 | Forced close | Cerrar TODAS las posiciones a market (`exit_type='TIME'`). Ver [[feedback-forced-close]]. |
| 15:56–15:59 | SGOV parking | Comprar SGOV con cash disponible. Ver [[feedback-eod-close-sgov]]. |
| ≥16:00 | Post-close | Protocolo de 5 pasos definido en `strategies/pulse_v2.md`. |

**Why:** El pre-análisis evita arrancar ciego a las 10:00 — la apertura (9:30–10:00) es la fase más volátil y define el régimen del día. La extensión a 15:45 (antes 15:30) captura más oportunidades en la tarde sin sacrificar tiempo de gestión final.

**How to apply:**
- Cuando el usuario diga "arranca el ciclo" antes de las 10:00, hacer pre-análisis primero. Si ya son las 10:00+, ir directo al loop.
- Para el corte de activo usar **15:45 ET** (no 15:30). Entre 15:45–15:55: solo manage, no entries.
- Programar wakeup específico a 15:55 ET — no confiar en que un ciclo de 5 min coincida.
