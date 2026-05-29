---
name: feedback-direct-cycles
description: Loop de trading = ciclos directos en conversación local; Alpaca MCP no funciona en cloud; restart CLI si MCP falla
metadata:
  type: feedback
---

El loop de trading corre como **ciclos directos en la conversación activa** desde una sesión local de Claude Code CLI. Claude llama directamente a `mcp__alpaca__*` cada ~5 min. No hay subprocess externo.

`start_agent.ps1` fue **eliminado del repositorio el 2026-05-26** — no recrearlo, no sugerirlo, no mencionarlo como alternativa.

**Why ciclos directos:**
- Continuidad de contexto entre ciclos → mejores decisiones.
- Menor consumo de tokens que un subprocess que tendría que rehidratar estado en cada arranque.
- Alpaca MCP requiere stdio local con credenciales en `.mcp.json`.

**Constraint cloud/CCR sandbox:**
- El sandbox de Claude Code Remote y el entorno web **no tienen acceso saliente a Alpaca** (`paper-api.alpaca.markets` / `data.alpaca.markets` bloqueados a nivel de allowlist).
- Tampoco a Supabase ni a APIs externas en general — bloqueo total de red, confirmado 2026-05-12 y 2026-05-21.
- Las rutas `/api/db/*` del dashboard Vercel SÍ son alcanzables desde la sesión local vía WebFetch — esa es la forma correcta de escribir a Supabase cuando el MCP de Supabase no es viable.
- Las routines CCR para trading están deshabilitadas — solo re-habilitables para tareas sin HTTP saliente.

**How to apply:**
- Para reducir consumo de tokens al arrancar el loop: usar `/model haiku` ([[user-inaki-profile]] aprobó este tradeoff).
- Si los tools `mcp__alpaca__*` no responden a mitad de loop, diagnóstico = MCP desconectado. Solución: reiniciar Claude Code CLI desde `C:\Users\inaki\Claude Code\Trading\Claude\` (donde está `.mcp.json`).
- Cuando el usuario diga "arranca el ciclo", hacerlo en la conversación misma. No proponer `start_agent.ps1` ni scripts externos.
