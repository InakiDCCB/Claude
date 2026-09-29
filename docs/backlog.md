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
| **A.2** GitHub / Vercel / Dashboard | Ramas, workflows, secrets, builds, env vars, consistencia métricas | ✅ CERRADO 07-03 — conector Vercel re-autenticado y verificado (team `inakidccb-2430s-projects`; get_project/get_deployment OK; deploy `d719f61` READY en producción). Nota: `list_projects` viene vacío (acceso por-proyecto) — usar IDs de `.vercel/project.json` |
| **A.3** Integridad general | Sincronización dashboard ↔ Supabase ↔ engine ↔ memorias | ✅ HECHO 07-01 → `docs/audit_integrity_2026-07-01.md` (match exacto trades↔memoria; equity −$1.14 = 0.001%) |
| **B.1** Optimización de ciclos | cycle_s, consultas lentas, paralelización. **Prerrequisito de 4.1** | ✅ Diagnóstico + **O1/O2 APLICADOS (cycle_prompt v3.0.6, 07-01)** → `docs/audit_cycles_2026-07-01.md`. Re-medir cadencia tras 3-5 sesiones y re-evaluar gate 4.1 con números |
| **C.1** Auditoría sistema Shadow | WR/PF/expectancy/DD por estrategia × horario × vol × liquidez; comparativa | ✅ HECHO 07-01 → `docs/audit_shadow_2026-07-01.md` (spec en `docs/specs/C1_shadow_audit.md`); re-auditar en S6 n≥25 o celda ≥5 ses |
| **C.2** Integración `/situational` | Qué conservar/sintetizar/descartar; relación con rendimiento | ✅ HECHO 07-02 (**v2**: AUTOMÁTICO en post-close 4d — `situational_snapshot()` teoriza D+1 con reglas fijas; precursores `sit:*`/`sitr:*` miden precisión por regla vs cierre siguiente; skill manual = ad-hoc no evaluado). Spec `docs/specs/C2_C3_C4_knowledge_integration.md` |
| **C.3** Comandos semanales | fetch_data / analysis_30d / final_portfolio → cadencia + integración /post-close | ✅ HECHO 07-02 — siguen semanales; resultados persisten como `strategy_performance` scope='backtest' 30d (post-close 4e) |
| **C.4** Fuente única de conocimiento | Unificar histórico + shadow + situacional + semanal + mercado en Market Intelligence | ✅ HECHO 07-02 — `v_shadow_accumulated` (nueva) + mapa de 6 vistas; dashboard/memoria/agente leen las MISMAS |
| **D.1** Veredicto S1/S4/S5 | Ventana expiró sin veredicto; acumular | S1/S4: SUPERADO por promoción directa 07-03 (claves shadow congeladas; evaluación ahora = ranking sobre `trades`). ⛔ S5 GAPF sigue acumulando (n=1) |
| **D.2** Promoción 4.1 → 4.2 → 4.3 | RSI2 LIVE → SWP/GAPF LIVE → SWPS LIVE | 🟢 **4.1+4.2 ADOPTADA 07-03 (v3.1.0, decisión usuario): S1 RSI2 + S4 SWP LIVE + multi-posición**, porteada fresh sobre v3.0.6. En validación 5 sesiones paper (reconciliación sin incidente). S5 GAPF sigue shadow; 4.3 SWPS gated (n≥10 con edge + bajista) |
| **D.3** Ranking dinámico | Tiers, champion_strategy, prioridades | ⛔ Evidencia (nunca con muestra insuficiente) |
| **E.1** Research SMC | BOS/CHoCH determinista (SMC estándar, killzones como dato) | ✅ CERRADO DEFINITIVO 07-16: backtest (E.1: estructura ≤1.13, confluencia ≤1.21) + veredicto live — **OB n=50 36.0% −$0.53/sh y OBNB n=27 37.0% −$0.39/sh RECHAZADAS** (el filtro sin-BOS no rescató). Cero supervivientes SMC. No re-abrir sin idea nueva |
| **E.2** FVG multi-fill | Mantener / revertir / alternativa | ⛔ Evidencia (usuario: esperar; señal mixta 06-26 vs 06-30) |
| **F.1** Limpieza memorias | Trim "En validación" + fvg experiment en /load-memory | ✅ HECHO 07-01 |
| **F.2** Mejoras técnicas | `trades.strategy_id NOT NULL`; DataTabs filtro/agrupación por estrategia | ✅ HECHO 07-01 — NOT NULL aplicado (migración `f2a_...`); DataTabs con selector + chips por estrategia (pendiente deploy a main) |
| **G** Gated por evidencia | Promociones, champion, automatización MI, ajustes ranking, FVG | Guardrails permanentes — no son tareas |
| **H · Golden Ticket** | Ingeniería inversa de principios Renaissance: fábrica de señales débiles + protocolo anti-overfit (FDR/walk-forward) + ensamble → pipeline shadow existente | 🟢 GT-0/1/2 HECHOS + **6 SHADOWS ACTIVOS**: gt_rsi2d + gt_3down (L1, 07-03 AM) + **gt_washout (OOS PF 1.60) + gt_closelow (PF 1.26, solape 16%) + ob_nobos (filtro E.1)** (07-03 PM, `docs/gt_batch2_2026-07-03.md`). Lotes 2/2b/2c intradía CORRIDOS y muertos (anti-hallazgo masivo). Claves canónicas 10. ⛔ GT-3 ensamble hasta ≥3 validadas no-solapadas. NO más lotes sin idea nueva |

## Bloqueadores actuales

1. **Muestra insuficiente** — el gate de todo D/G. El loop corrió normal 06-29→07-01 (evidencia
   acumulando de nuevo); huecos 06-23/25/26 quedan como pérdida de muestra no recuperable in-cycle.
2. ~~Vercel OAuth~~ — RESUELTO 07-03 (conector operativo, A.2 cerrado).
3. **Ciclos** — B.1 necesita más sesiones instrumentadas; v3.1.0 añade trabajo a STEP 3 → re-medir cadencia contra el baseline 07-02 (mediana 5m05s).

## Entregables (del backlog original)

1. Auditoría Supabase ✦ 2. Auditoría GitHub/Vercel/Dashboard ✦ 3. Validación calidad de datos ✦
4. Optimización engine ✦ 5. Auditoría Shadow ✦ 6. `/situational` → aprendizaje ✦ 7. Semanales →
/post-close ✦ 8. MI enriquecido ✦ 9. Ranking validado ✦ 10. Promociones solo con evidencia ✦
11. Memorias sin redundancia ✦ 12. Dashboard sincronizado.

## Hipótesis verificadas — pendiente validación 3 sesiones

Backtest confirma la dirección; la spec NO cambia hasta completar las 3 sesiones. Fuente: `tools/lab/rsi2_abort_sweep.py` (10 años, n≈25k señales S1 RSI2).

| ID | Hipótesis | Evidencia backtest | Costo | Acción cuando se valide |
|---|---|---|---|---|
| **H1** | Excluir entradas RSI2 antes de 12:00 ET | PF 1.081→1.122 (+0.042), 9/11 años mejoran; peor año: −0.008 (flat) | −26.4% señales (6.775) | Añadir gate `seal_bar >= 149` en **STEP 6** (bloque S1 RSI2, antes de `place_stock_order`) de `cycle_prompt.md` |
| **H3** | Subir abort latencia 150s→300s | Cliff real a 420–480s (bar 7-8); bars 1-6 PF 1.03–1.08, sin degradación material | Ninguno (añade trades) | ✅ **IMPLEMENTADA v3.1.21 (2026-09-29)** — decisión usuario sin esperar las 3 sesiones: en live el abort de 150s mataba ~70% de las señales (100 aborts vs 42 trades, ciclo medio 220s). Confirmado también con el modelo de fill límite: colocar a ~5 min no degrada vs ~3 min. |
| **H-VWAP** | S1 solo si `close del bloque > VWAP` al sello | 10.7 años, TP0.5/SL1.0/ts15, límite al cierre ~3 min tarde, neto de fees: fill al toque +0.01→+0.42 bp/trade (LB +0.08, 9/11 años); fill con cola (1¢ through) −0.43→+0.02 bp. Única mejora robusta bajo ambos modelos. Live: perdedores en días débiles (mediana −0.25% desde apertura vs −0.07%). | −60% señales | **En logging paralelo desde v3.1.21** (`vwap_ok` en notes de `trades` + `s1_signals` en `analysis_log`). Tras ≥3 sesiones con señales: si P&L de `vwap_ok=1` > `vwap_ok=0`, añadir `entry > state.QQQ.vwap` como condición de la señal S1 en STEP 6. |

Sesiones completadas: H1 0/3 · H-VWAP 0/3 (empieza a contar la próxima sesión con señales RSI2). Revisión completa y scripts de validación: sesión 2026-09-29 (reporte "Revisión de Trades Aconcagua").

---
*Histórico de decisiones y sistemas: memoria `project_systems_history.md`. Roadmap operativo previo
(2026-06-18) superseded por este backlog: memoria `project_roadmap.md` apunta aquí.*
