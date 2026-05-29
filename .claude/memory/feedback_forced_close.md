---
name: feedback-forced-close
description: Forced close 15:55 ET obligatorio + brackets DAY expiran al cierre; usar GTC solo si overnight autorizado
metadata:
  type: feedback
---

**Reglas críticas al cierre de sesión:**

1. **Forced close 15:55 ET — OBLIGATORIO.** Cerrar todas las posiciones a market (`exit_type='TIME'`). No esperar al 16:00.
2. **Programar wakeup específico para 15:55 ET** durante la passive observation. No confiar en que un ciclo de 5 min coincida.
3. **Brackets con `time_in_force: day` expiran al cierre del mercado (16:00 ET).** Si una posición debe quedar overnight (decisión explícita del usuario), usar `time_in_force: gtc` en SL/TP antes de las 16:00.
4. **Default: cerrar todo a 15:55 ET.** Posiciones overnight requieren autorización explícita del usuario. La única excepción es SGOV — ver [[feedback-eod-close-sgov]].

**Why:** El 2026-05-27 quedaron QQQ 4sh + RIVN 70sh abiertas overnight porque (a) no se programó forced close a 15:55 y (b) los brackets eran DAY orders que expiraron a las 16:00. Mercado cerrado bloquea correcciones. RIVN cayó $0.11/sh durante el último intercambio = −$7.70 unrealized evitable.

**How to apply:**
- Al entrar a passive observation a 15:45 ET, programar wakeup a 15:55 ET con prompt explícito "Cerrar todas las posiciones a market — forced close".
- Si el usuario pide mantener overnight, reemplazar SL/TP por órdenes `gtc` antes de las 16:00.
- Loggear `exit_type='TIME'` en Supabase para trades cerrados por forced close.

Relacionado: [[feedback-session-schedule]], [[feedback-eod-close-sgov]].
