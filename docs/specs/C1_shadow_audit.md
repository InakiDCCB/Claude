# Spec C.1 — Auditoría Integral del Sistema Shadow

**Activada:** 2026-07-01 · **Épica:** C (Sistema de Aprendizaje) · **Tipo:** auditoría read-only

## Objetivo
Evaluar TODAS las estrategias shadow (S1 RSI2, S4 SWP, S5 GAPF, S6 SWPS, OB) con los datos reales
acumulados, compararlas entre sí y clasificar cada una en: mayor potencial / requiere más muestra /
candidata a promoción / requiere ajustes / permanecer en observación. **Sin promover nada** — la
promoción sigue el gate D.2 y la decide el usuario.

## Fuentes de datos (por prioridad)
1. `session_memory.observations-><sys>.signals[]` — per-signal (ts, out, pnl, lat) cuando existe.
2. `session_memory.observations-><sys>` — agregados por sesión {n, tp, sl, time, miss, pnl}.
3. `shadow_signals` (vista) — cobertura/latencia de señales loggeadas in-cycle.
4. `market_conditions` + `market_context` — cruce por liquidez / volatilidad / contexto.

## Método
- Parseo defensivo del JSONB (regex-guard; formas heterogéneas pre-06-22 se excluyen y se declaran).
- Métricas por estrategia: n, WR (TP/resueltas), PF y expectancy $/sh (solo donde hay pnl per-signal),
  descomposición TP/SL/TIME/MISS, latencia, evolución por sesión.
- Cruces: estrategia × liquidez, × volatilidad, × context_label, × hora ET.
- Calidad de entradas/salidas: tasa MISS, TIME-share, eventos anómalos documentados en notas.

## Criterios de aceptación
1. Cada una de las 5 estrategias tiene ficha con métricas + clasificación justificada.
2. Ninguna recomendación con n de celda < 5 sesiones se presenta como conclusión (solo "indicio").
3. Los datos contaminados (días con bugs documentados) se declaran, no se mezclan en silencio.
4. Entregable: `docs/audit_shadow_2026-07-01.md` commiteado; resumen ejecutivo en chat.

## Fuera de alcance
Promociones a live (D.2), cambios de spec del loop, ajustes de parámetros (requieren backtest aparte).
