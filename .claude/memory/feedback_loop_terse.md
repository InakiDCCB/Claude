---
name: feedback-loop-terse
description: Respuestas ultra-terse durante el trading loop — una línea por ciclo, expandir solo en eventos
metadata:
  type: feedback
---

Durante el trading loop, **respuestas ultra-terse** — cada token cuenta. Reforzado dos veces ("siguen siendo demasiado largas" tras una primera reducción).

**Why:** El loop fira cada ~5 min durante 6h+. Respuestas verbosas queman el contexto sin aportar nada cuando no hay nada nuevo. El usuario lee desde el dashboard ([[project-dashboard]]) en tiempo real — la conversación es solo para confirmar progreso y reportar eventos.

**How to apply:**

- **Default por ciclo: UNA línea**
  `HH:MM ET — QQQ $X — régimen — acción (o "sin acción")` (universo QQQ-only desde 2026-06-04)
- **NO tablas** salvo que dispare un setup o cambie posición.
- **NO notas/commentary** salvo entry/exit/alerta.
- **NO narración antes de tool calls.**
- Escrituras a `session_state` y heartbeats: silenciosas (sin preámbulo).
- `ScheduleWakeup` se llama sin commentary — solo la llamada.
- **Expandir solo en:** signals, fills, errores, cambios de régimen, o preguntas del usuario.

**Reglas operativas que no son de verbosity pero suelen olvidarse aquí:**
- Aun con posición abierta, **seguir evaluando nuevas entradas** en los otros símbolos (cap 70% exposure / max 2 posiciones por protocolo v2.8). Monitorear posición no excluye el scan completo de setups.
- Loop cadencia ~5 min, ajustable a 90s si algún símbolo está en zona de alerta (±0.30% del VWAP sin full setup, ver CLAUDE.md step 14).

Relacionado: [[feedback-decision-style]] (mismo principio en decisiones — solo preguntar cuando hay tradeoff real).
