# Spec B.1 — Optimización de Ciclos del Trading Engine

**Activada:** 2026-07-01 · **Épica:** B (Rendimiento) · **Tipo:** diagnóstico read-only + propuestas
**Prerrequisito de:** Fase 4.1 (gate: ciclos < 5 min)

## Objetivo
Diagnosticar con evidencia por qué hay ciclos que exceden el presupuesto de 5 minutos (ventana entre
velas), identificar las causas dominantes y proponer optimizaciones — **sin modificar el spec del loop
en esta fase** (cualquier cambio a cycle_prompt.md es propuesta separada aprobada por el usuario).

## Contexto
- Instrumentación `cycle_s`/`cycle_type` viva desde v3.0.4 (06-18); muestra: 5 sesiones, 65 ciclos.
- 1ª medición (06-22): ~130s promedio se declaró "suelo estructural" (~50s harness + proceso).
- Dato nuevo: el promedio por sesión CRECE (52→121→195→229→190s) — el suelo no explica la tendencia.
- Un ciclo > 300s pierde la vela siguiente → señales RSI2/SWP evaluadas tarde o perdidas.

## Preguntas a responder (con datos)
1. ¿Qué `cycle_type` domina el tiempo? (full vs light vs skip)
2. ¿El ciclo se degrada DENTRO de la sesión (acumulación de contexto del agente) o entre sesiones?
3. ¿Qué causó cada outlier > 300s? (posición activa, recovery, compactación, tool calls extra)
4. ¿La cadencia real de wakes respeta el diseño (sello 5-min + 10s)? ¿Cuántos huecos > 360s?

## Criterios de aceptación
1. Cada pregunta respondida con números (o declarada irresoluble con los datos actuales).
2. Outliers > 300s explicados individualmente.
3. Propuestas de optimización priorizadas con impacto estimado y riesgo — NINGUNA aplicada sin OK.
4. Veredicto explícito del gate 4.1 ("ciclos < 5min"): cumplido / no cumplido / condicionado.
5. Entregable: `docs/audit_cycles_2026-07-01.md` commiteado.

## Fuera de alcance
Cambios a cycle_prompt.md, re-arquitectura de agentes (multi-agente ya DESCARTADO 06-22 con evidencia).
