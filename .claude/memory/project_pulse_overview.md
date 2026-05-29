---
name: project-pulse-overview
description: Sistema Pulse v2.8 — agente paper-trading autónomo con 4 setups; FVG es independiente del resto
metadata:
  type: project
---

Pulse v2.8 es un agente paper-trading autónomo basado en Claude Code + Alpaca + Supabase + dashboard Next.js. Operativa long-only en ventana 10:00–15:55 ET, ciclos de ~5 min. Cuatro setups en paralelo:

1. **RANGE — VWAP Pullback** (árbol v2.7)
2. **RANGE — Volume Absorption** (árbol v2.7)
3. **TREND — ORB Breakout** (árbol v2.7)
4. **FVG — Fair Value Gap** (independiente, tesis ICT)

Los 3 primeros comparten el árbol "v2.7" (filtros EMA21, RSI 45–65, VWAP zone, TREND DOWN restriction) y desde v2.8 además **Volume Profile como hard filter primario** (yesterday VA / developing VA / proximidad a VPOC o naked POC, según setup).

El cuarto setup (FVG, `strategy='fvg_v1'`) es **explícitamente independiente**: sizing propio (5% equity vs 10%), sin filtros EMA/RSI/VWAP, sin filtro VP, opera en paralelo con su propio SL/TP. Un mismo símbolo puede tener trade v2.7 y trade FVG simultáneamente.

**Specs canónicos** (en el repo Trading):
- `strategies/pulse_v2.md` — reglas, historial de versiones, propuestas
- `strategies/cycle_prompt.md` — loop ejecutable paso a paso (STEP 0–10)
- `CLAUDE.md` — resumen del flujo y contexto del proyecto
- Fuente de verdad de parámetros activos: tabla `champion_strategy.config` en Supabase

**Why:** mantener este overview en memoria evita re-leer ~470 líneas de `pulse_v2.md` para saber que existen 4 setups y que FVG es la excepción del árbol principal.

**How to apply:** al recibir cualquier pedido de cambio en filtros, indicadores o lógica de entrada, validar si afecta también a FVG y preguntar explícitamente. Al hablar de "los setups" o "v2.7 setups" sin más contexto, asumir los 3 no-FVG. Cuando el usuario diga "todos los setups", confirmar si FVG entra — por defecto NO entra.
