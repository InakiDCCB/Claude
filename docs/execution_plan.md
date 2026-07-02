# Plan de Ejecución Ordenado — Laboratorio de Trading

> Runbook secuencial (complementa `docs/backlog.md`, que está por épica). Orden = por dependencia y
> disponibilidad, no por número de épica. Regla: lo accionable-ya y de alto apalancamiento primero;
> los diseños que desbloquean otras cosas después; lo gated-por-evidencia se alimenta solo.
> **Metodología por tarea:** entender estado → plan → validar → ejecutar; los cambios estructurales
> se documentan (spec en `docs/specs/`) ANTES de tocar; toda decisión respaldada por evidencia.

## ✅ Hecho (sesión 2026-07-01)

| # | Tarea | Entregable |
|---|---|---|
| 0.1 | F.1 Limpieza de memorias | MEMORY.md compacto + registro movido a research |
| 0.2 | Backlog maestro + decisiones E.1 | `docs/backlog.md` |
| 0.3 | A.1 Auditoría Supabase + fixes P0/P1 | `docs/audit_supabase_2026-07-01.md` · migración `audit_a1_fixes_p0_p1` (advisors: 0) |
| 0.4 | C.1 Auditoría Shadow + fixes P-C1a/b | `docs/audit_shadow_2026-07-01.md` · claves canónicas + backfill MI |
| 0.5 | B.1 Ciclos + O1/O2 | `docs/audit_cycles_2026-07-01.md` · `cycle_prompt.md` v3.0.6 |
| 0.6 | Fase 3.1 Market Intelligence | motor SQL + dashboard + memoria (sesiones previas) |

---

## 🟢 Cola accionable YA (sin gate de datos — orden recomendado)

> ✅ #1 A.3 y #2 F.2 completados 2026-07-01 (`docs/audit_integrity_2026-07-01.md`; migración
> `f2a_trades_strategy_id_not_null`; DataTabs con filtro+chips).
> ✅ #3 C.2+C.3+C.4 completados 2026-07-02 (spec + migración `c234_knowledge_integration`:
> `v_shadow_accumulated` + classify/patterns/hypotheses v2 con precursor situacional; /situational
> QQQ-only; /post-close paso 4e viernes). La cola accionable sin gate de datos queda VACÍA —
> lo restante espera evidencia (D/E.2/G), re-medición (gate 4.1) o acción del usuario (Vercel).

### 1. A.3 — Integridad general (verificación cruzada) — ✅ HECHO
- **Qué:** confirmar que dashboard ↔ Supabase ↔ engine (session_state) ↔ memorias cuentan lo mismo
  (P&L, nº trades, ranking, gates del último día).
- **Método:** queries read-only de reconciliación (trades vs alpaca_state vs session_memory;
  v_strategy_ranking vs strategy_performance; MEMORY.md "En validación" vs datos reales). Documentar
  discrepancias en `docs/audit_integrity_<fecha>.md`. **Sin cambios**, solo verificación + hallazgos.
- **Entregable:** informe corto; si hay drift, propuestas gated por OK.

### 2. F.2 — Mejoras técnicas (2 sub-tareas independientes) — ✅ HECHO
- **2a · `trades.strategy_id NOT NULL`** — A.1 lo validó seguro (0 nulls). **Método:** migración
  `ALTER TABLE trades ALTER COLUMN strategy_id SET NOT NULL` (el trigger ya lo rellena). Verificar
  con un INSERT de prueba en transacción abortada.
- **2b · DataTabs filtro/agrupación por estrategia** — **Método:** editar `dashboard/components/DataTabs.tsx`
  (selector de estrategia + group-by); `tsc --noEmit` + `npm run build`; commit rama; fast-forward a
  main (deploy, requiere OK explícito).

### 3. C.2 — Diseño: `/situational` → Sistema de Aprendizaje
- **Qué:** integrar el bias diario de `situational_analysis` al conocimiento acumulado.
- **Método (diseño primero):** spec `docs/specs/C2_situational_integration.md` — qué conservar/
  sintetizar/descartar, cómo cruzarlo con `market_context`/rendimiento (¿nueva columna? ¿tag en
  market_context? ¿vista de correlación bias→outcome?). **Presentar propuesta → OK → implementar.**

### 4. C.3 — Diseño: comandos semanales → `/post-close`
- **Qué:** decidir cadencia de `fetch_data.py` / `analysis_30d.py` / `final_portfolio.py` y qué
  integrar al flujo diario sin duplicar.
- **Método:** spec `docs/specs/C3_weekly_integration.md` — auditar qué produce cada script, cuáles
  aportan diario vs semanal, dónde engancha en `/post-close`. Propuesta → OK → editar `post-close.md`.

### 5. C.4 — Diseño: fuente única de conocimiento
- **Qué:** unificar histórico + shadow + situacional + semanal + mercado sobre Market Intelligence.
- **Método:** spec `docs/specs/C4_unified_knowledge.md`, construido SOBRE `v_market_intelligence`
  (A.1 confirmó que la arquitectura lo soporta sin cambios estructurales). Depende de C.2 + C.3.

### 6. E.1 — Research SMC (decisiones ya tomadas: SMC estándar + killzones como dato)
- **6a · BOS/CHoCH determinista:** formalizar en `strategies/research/smc_shadow.py` (reusa el motor
  de OB); **backtest** sobre qqq_1min → si edge, pasa a shadow logging (nada a live sin 5 sesiones).
- **6b · Killzone tagging (dato-primero):** etiquetar cada señal shadow / `market_context` con su
  killzone ICT; dejar que MI mida si el edge se concentra (gate solo con evidencia ≥ min-N).
- **Método:** research offline, NO bloquea el operativo; documentar en `smc_study.md`.

### 7. A.2 — Cierre auditoría infra (parcial → bloqueado)
- GitHub + dashboard consistency: verificable ya. **Vercel: BLOQUEADO** hasta que re-autentiques el
  conector OAuth. **Método:** tras re-auth, `list_deployments` + env vars + último build → informe.

---

## 🔵 Gated por evidencia (se alimentan solos mientras el loop corra — NO forzar)

| # | Tarea | Disparador | Método al dispararse |
|---|---|---|---|
| G1 | Re-evaluar gate ciclos 4.1 | 3-5 sesiones con v3.0.6 (`cycle_log`) | Re-correr análisis B.1 con cadencia real |
| G2 | Re-auditar Shadow | S6 SWPS n≥25 **o** celda contexto×strat ≥5 ses | Re-correr C.1; MI genera 1ª hipótesis sola |
| G3 | D.1 Veredicto S1/S4/S5 | muestra limpia suficiente | Comparar vs backtest → recomendar (decide usuario) |
| G4 | D.2 Fase 4.1 → 4.2 → 4.3 | veredicto S1 + ciclos <5min + STEP 3 (encadenadas) | Adoptar rama v3.1.0 + registry live + 5 ses paper |
| G5 | D.3 Ranking / champion_strategy | algún sistema cruza tier | Activar champion (decide usuario) |
| G6 | E.2 FVG multi-fill | más sesiones (señal mixta 06-26 vs 06-30) | Revertir 1/día o mantener (decide usuario) |
| G7 | Market Intelligence despierta | ~15-20 sesiones clasificadas | Automático (hipótesis + recomendaciones) |

---

## 🙋 Requiere acción del usuario (no de Claude)
- **Re-auth conector Vercel (OAuth)** → desbloquea A.2 (#7).
- **Correr el loop en días de mercado** → es el combustible de TODO el bloque gated (G1-G7).
- **OKs de deploy a main** y de cambios de spec/migraciones (según metodología).

---
*Fuente de verdad de estado: `docs/backlog.md`. Este archivo = orden de ejecución.*
