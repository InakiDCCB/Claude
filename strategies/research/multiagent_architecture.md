# Arquitectura Multi-Agente — Diseño Técnico

**Estado: PROPUESTA. No implementado.** Requiere aprobación. Fecha: 2026-06-18.
PoC validado: MCP Alpaca global + acceso concurrente local OK (4 procesos, 0 fallos) + 2 sesiones CLI
simultáneas confirmadas por el usuario. El bloqueo original era cloud/remoto; en LOCAL funciona.

## 1. Objetivo y el trade-off central
Separar el loop monolítico en agentes especializados para: (a) **resolver la latencia** (el agente
live queda lean → ciclos rápidos), y (b) permitir **SMC shadow en vivo** sin cargar el live.

**El trade-off honesto: latencia ↓ pero tokens ↑.** Más agentes concurrentes = más razonamiento en
paralelo = más tokens. Este diseño hace ese costo EXPLÍCITO y da palancas para acotarlo (§3).
Restricción dura: **TODO local** (Alpaca MCP no funciona en nube).

## 2. Los 5 agentes

| Agente | Rol | Cadencia | ¿Órdenes? | Escribe | Modelo sugerido |
|---|---|---|---|---|---|
| **A1 Live** | trading real (FVG/VWAPPB + RSI2 si 4.1) | 5-min (~60/día) | ✅ ÚNICO | `session_state.positions`, `trades` | Sonnet (latencia/precisión) |
| **A2 Pre-market** | seeds + niveles + gates | 1×/día | ❌ | `session_state` (seeds) | Sonnet |
| **A3 Post-close** | niveles mañana + ranking + memoria | 1×/día | ❌ | `volume_profiles`, `strategy_*`, `session_memory` | Sonnet |
| **A4 Shadow actual** | S1/S4/S5/S6 shadow | 5-min, laxo | ❌ READ-ONLY | `analysis_log.shadow_signals` | **Haiku** |
| **A5 Shadow SMC/ICT** | OB + SMC nuevos shadow | 5-min, laxo | ❌ READ-ONLY | `analysis_log.shadow_signals` (sys=OB…) | **Haiku** |

## 3. ⚠️ Consumo de tokens (la preocupación) — análisis y palancas

**Magnitud (estimación gruesa, a MEDIR):** el live agent hoy ≈ 1–1.5M tokens/día (contexto re-leído
sin cache cada ~5 min × ~60 ciclos). Los 2 shadow a 5-min son el multiplicador. Sin optimizar:
**~3× durante mercado.** A2/A3 son marginales (1 run). **NO tengo cifras precisas** — el tracking de
tokens estaba 0/158 (ver [[cycle-latency-overrun]]); hay que MEDIR per-agente con el cost-tracking de
Claude Code durante el PoC de 2 agentes.

**Palancas para acotar (de mayor a menor impacto):**
- (a) **Haiku en A4/A5** — no son latency/accuracy-critical (solo loggean señales con precios). El veto
  a Haiku era por el LOOP LIVE (rompía latencia); NO aplica a shadow. Ahorro grande (Haiku ≈ 1/10–1/20 del costo).
- (b) **Cadencia laxa en A4/A5** — no necesitan despertar a sello+10s; sello+30–60s o cada 2 velas (10 min) si la señal lo tolera.
- (c) **Contexto lean por agente** — cada uno carga SOLO su spec, no el cycle_prompt entero. Multi-agente
  puede ser MÁS eficiente por ciclo (contexto menor) aunque haya más ciclos.
- (d) **Early-exit estricto** en A4/A5 (sin barra nueva sellada → skip 1 línea, sin razonar).
- (e) **OPCIÓN BATCH (la más barata):** A5 (SMC) puede correr como batch en `/post-close`
  (`smc_shadow.py`) en vez de in-cycle → coste **casi cero**, pero no real-time. Híbrido posible:
  empezar A5 en batch y promover a in-cycle solo si demuestra edge.

**Recomendación token-consciente:** A4/A5 en **Haiku + cadencia laxa + lean context** → acota el
multiplicador a ~1.3–1.8× en vez de 3×. Si aun así preocupa, A5 en batch (e).

## 4. Separación de estado (sin carreras)
- **A1 es el ÚNICO dueño** de `session_state.positions` y de `trades`. Nadie más los toca.
- A2/A3 escriben sus propias tablas (seeds, volume_profiles, strategy_*, session_memory) — sin solape con A1.
- A4/A5 SOLO hacen append a `analysis_log.shadow_signals`. Jamás positions/trades.
- **Indicadores compartidos** (VWAP/RSI/ATR/5-min): para no recomputar en cada agente (tokens), A1
  publica los indicadores en una tabla `live_indicators` (o en `session_state`) y A4/A5 los LEEN.
  Centralizar el cómputo en A1 ahorra tokens en los shadow.

## 5. Aislamiento de ejecución (seguridad — crítico) — 3 CAPAS
1. **Spec:** A4/A5 jamás incluyen `place_order`; son read-only por diseño.
2. **Tool permissions** (settings del agente shadow): denegar `mcp__alpaca__place_*`, `cancel_*`,
   `close_*`, `replace_*`, `exercise_*`. El agente físicamente no puede llamar esas tools.
3. **Key Read-only de Alpaca** (CONFIRMADO posible 06-18): Alpaca ofrece 3 niveles — Read&Write /
   **Read only** / No Access, + scopes custom (Trading=No Access, Data=Read). A4/A5 usan una key
   Read-only → físicamente NO pueden operar aunque el modelo alucine. ⚠️ La doc de read-only keys es
   del Broker API/BrokerDash; **verificar en el dashboard de paper** si el generador la ofrece. Si no,
   las capas 1+2 bastan. Fuente: docs.alpaca.markets/docs/credential-management.

## 6. Orquestación (manual, como hoy)
5 terminales locales, cada una con su rol:
- T1 `/pre-market` (A2) → cierra. T2 `@cycle_prompt.md` (A1, auto-wakeups). T3 shadow actual (A4).
  T4 SMC shadow (A5). T5 `/post-close` (A3) al cierre.
- Cada agente auto-programa sus wakeups (ScheduleWakeup), como hoy.
- Conveniencia: un `.ps1` de arranque que abra las terminales con su comando — opcional.

## 7. Plan incremental (validar 2 → 5, evidencia primero)
1. **2 agentes:** A1 (live actual, sin shadow) + A4 (mover S1/S4/S5/S6 shadow FUERA del live).
   Validar: (i) el `cycle_s` de A1 BAJA (instrumentación v3.0.4 lo mide), (ii) A4 loggea igual,
   (iii) sin carreras de estado, (iv) **MEDIR tokens totales** (Claude Code cost-tracking).
2. **+A5** (SMC shadow) — Haiku/cadencia laxa o batch.
3. **Separar A2/A3** (ya 1×/día, trivial).
Cada paso se valida antes del siguiente. Si el token-cost de un paso es inaceptable, se ajusta
(modelo/cadencia/batch) antes de seguir.

## 8. Decisiones para el usuario
- **Modelo A4/A5:** ¿Haiku (barato, recomendado) o Sonnet (consistente)?
- **A5 SMC:** ¿in-cycle (real-time, +tokens) o batch en post-close (casi cero, no real-time)?
- **Keys data-only** para shadow: ¿investigar/crear en Alpaca para el aislamiento de ejecución?
- **Arranque:** ¿`.ps1` que lance las 5 terminales, o manual?
