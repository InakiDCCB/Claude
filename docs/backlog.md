# Backlog Maestro — Laboratorio de Trading Cuantitativo

> Fuente de verdad de la planificación (directiva usuario 2026-07-01). Las specs técnicas por épica
> (criterios de aceptación, hitos, métricas) se escriben en `docs/specs/` **cuando cada épica se
> activa** — no por adelantado (decisión usuario 07-01: evita specs que envejecen).
> Metodología: planificación completa antes de ejecutar; toda decisión respaldada por evidencia;
> mejoras arquitectónicas se documentan y proponen ANTES de implementarse.

> **Orden de ejecución** (secuencia por dependencia + método por tarea): `docs/execution_plan.md`.

## Decisiones registradas (2026-07-01)

| Fork | Decisión |
|---|---|
| Orden de arranque | F.1 (memorias) + A.1 (auditoría Supabase) primero; C.1 después |
| Formato specs | Índice maestro (este doc) + spec por épica al activarse, en `docs/specs/` |
| E.1 base SMC | **SMC estándar** (conceptos públicos ICT/SMC, formalizables); reglas Casapia se contrastan encima si algún día se consiguen |
| E.1 killzones | **Dato primero**: etiquetar señal/sesión con killzone y dejar que Market Intelligence mida concentración de edge; gate solo con evidencia ≥ min-N |

## Estado por épica

| Épica | Contenido | Estado / disparador |
|---|---|---|
| **A.1** Auditoría Supabase | Esquema, calidad de datos, rendimiento, preparación aprendizaje | 🔄 EN CURSO (07-01) → `docs/audit_supabase_2026-07-01.md` |
| **A.2** GitHub / Vercel / Dashboard | Ramas, workflows, secrets, builds, env vars, consistencia métricas | Parcial. **Bloqueado Vercel**: conector OAuth conecta pero scope vacío (0 teams) → re-auth del usuario |
| **A.3** Integridad general | Sincronización dashboard ↔ Supabase ↔ engine ↔ memorias | ✅ HECHO 07-01 → `docs/audit_integrity_2026-07-01.md` (match exacto trades↔memoria; equity −$1.14 = 0.001%) |
| **B.1** Optimización de ciclos | cycle_s, consultas lentas, paralelización. **Prerrequisito de 4.1** | ✅ Diagnóstico + **O1/O2 APLICADOS (cycle_prompt v3.0.6, 07-01)** → `docs/audit_cycles_2026-07-01.md`. Re-medir cadencia tras 3-5 sesiones y re-evaluar gate 4.1 con números |
| **C.1** Auditoría sistema Shadow | WR/PF/expectancy/DD por estrategia × horario × vol × liquidez; comparativa | ✅ HECHO 07-01 → `docs/audit_shadow_2026-07-01.md` (spec en `docs/specs/C1_shadow_audit.md`); re-auditar en S6 n≥25 o celda ≥5 ses |
| **C.2** Integración `/situational` | Qué conservar/sintetizar/descartar; relación con rendimiento | ✅ HECHO 07-02 (**v2**: AUTOMÁTICO en post-close 4d — `situational_snapshot()` teoriza D+1 con reglas fijas; precursores `sit:*`/`sitr:*` miden precisión por regla vs cierre siguiente; skill manual = ad-hoc no evaluado). Spec `docs/specs/C2_C3_C4_knowledge_integration.md` |
| **C.3** Comandos semanales | fetch_data / analysis_30d / final_portfolio → cadencia + integración /post-close | ✅ HECHO 07-02 — siguen semanales; resultados persisten como `strategy_performance` scope='backtest' 30d (post-close 4e) |
| **C.4** Fuente única de conocimiento | Unificar histórico + shadow + situacional + semanal + mercado en Market Intelligence | ✅ HECHO 07-02 — `v_shadow_accumulated` (nueva) + mapa de 6 vistas; dashboard/memoria/agente leen las MISMAS |
| **D.1** Veredicto S1/S4/S5 | Ventana expiró sin veredicto; acumular | ⛔ Evidencia (loop corriendo) |
| **D.2** Promoción 4.1 → 4.2 → 4.3 | RSI2 LIVE → SWP/GAPF LIVE → SWPS LIVE | ⛔ Gates: veredicto S1 + ciclos <5min + STEP 3 (4.1); encadenadas |
| **D.3** Ranking dinámico | Tiers, champion_strategy, prioridades | ⛔ Evidencia (nunca con muestra insuficiente) |
| **E.1** Research SMC | BOS/CHoCH determinista (SMC estándar, killzones como dato) | ✅ HECHO 07-02 + confluencia (addendum §6) → **stream SMC CERRADO**: estructura ≤1.13, confluencia ≤1.21 (listón 1.65). Hallazgos: OB post-BOS tóxico (filtro negativo candidato); edge horario en open. `kz` en OB shadow vivo. Superviviente único: OB shadow (n=22, en curso) |
| **E.2** FVG multi-fill | Mantener / revertir / alternativa | ⛔ Evidencia (usuario: esperar; señal mixta 06-26 vs 06-30) |
| **F.1** Limpieza memorias | Trim "En validación" + fvg experiment en /load-memory | ✅ HECHO 07-01 |
| **F.2** Mejoras técnicas | `trades.strategy_id NOT NULL`; DataTabs filtro/agrupación por estrategia | ✅ HECHO 07-01 — NOT NULL aplicado (migración `f2a_...`); DataTabs con selector + chips por estrategia (pendiente deploy a main) |
| **G** Gated por evidencia | Promociones, champion, automatización MI, ajustes ranking, FVG | Guardrails permanentes — no son tareas |
| **H · Golden Ticket** | Ingeniería inversa de principios Renaissance: fábrica de señales débiles + protocolo anti-overfit (FDR/walk-forward) + ensamble → pipeline shadow existente | 🔬 Research HECHO 07-02 → `docs/specs/golden_ticket_research.md`. **Implementación NO iniciada** (decisión usuario: próxima sesión). 4 decisiones abiertas en §5. Hitos M1-M3 en vez de "igualar 66%" (no comprometible — ver §3) |

## Bloqueadores actuales

1. **Muestra insuficiente** — el gate de todo D/G. El loop corrió normal 06-29→07-01 (evidencia
   acumulando de nuevo); huecos 06-23/25/26 quedan como pérdida de muestra no recuperable in-cycle.
2. **Vercel OAuth** — conector con scope vacío; re-auth del usuario para cerrar A.2.
3. **Ciclos** — B.1 necesita más sesiones instrumentadas (cycle_s) para optimizar con evidencia.

## Entregables (del backlog original)

1. Auditoría Supabase ✦ 2. Auditoría GitHub/Vercel/Dashboard ✦ 3. Validación calidad de datos ✦
4. Optimización engine ✦ 5. Auditoría Shadow ✦ 6. `/situational` → aprendizaje ✦ 7. Semanales →
/post-close ✦ 8. MI enriquecido ✦ 9. Ranking validado ✦ 10. Promociones solo con evidencia ✦
11. Memorias sin redundancia ✦ 12. Dashboard sincronizado.

---
*Histórico de decisiones y sistemas: memoria `project_systems_history.md`. Roadmap operativo previo
(2026-06-18) superseded por este backlog: memoria `project_roadmap.md` apunta aquí.*
