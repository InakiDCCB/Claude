---
name: user-inaki-profile
description: Perfil del usuario Inaki — paper trader con sistema autónomo Pulse en Alpaca, hispanohablante, conocimiento técnico avanzado
metadata:
  type: user
---

Inaki opera una cuenta paper en Alpaca con un agente autónomo (Pulse) escrito como skill de Claude Code que él mismo orquesta desde una sesión local. Universo restringido a **QQQ únicamente** — sin excepciones. Ver [[project-universe-constraints]].

**Stack:** Alpaca MCP (market data + execution) + Supabase (ledger, estado, memoria) + Next.js en Vercel (dashboard). Ver [[ref-supabase]].

**Idioma:** español en conversación. Código y specs en su idioma original — ver [[feedback-language]].

**Nivel técnico:** profundo en trading avanzado — Volume Profile (VPOC, VAH/VAL, naked POCs), order flow, ICT/FVG, value areas, absorción institucional, stop hunts. No requiere explicaciones básicas de estos conceptos. También cómodo con Supabase, Next.js, GitHub, MCP, y la arquitectura de Claude Code.

**Pragmático con tradeoffs coste/precisión:** cuando un cambio justifica más calls a la API, más estado persistente, o una migración a cambio de mejor señal, lo aprueba sin fricción (ej. eligió tick trades SIP sobre bars 5-min para Volume Profile aunque añade payload y latencia).
