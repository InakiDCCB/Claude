# Diagnóstico de Ciclos del Trading Engine — 2026-07-01 (Épica B.1)

> Spec: `docs/specs/B1_cycle_optimization.md`. Muestra: 5 sesiones instrumentadas (06-22, 06-24,
> 06-29, 06-30, 07-01), 65 ciclos con `cycle_s` (v3.0.4). Read-only; propuestas al final, nada aplicado.

## 1. ¿Qué domina el tiempo? — el TIPO de ciclo, no la sesión

| cycle_type | n | avg | p50 | max |
|---|---|---|---|---|
| gap_recovery | 3 | **535s** | 381 | 1002 |
| fill | 12 | 179s | 158 | 383 |
| scan | 21 | 148s | 117 | 300 |
| shadow | 28 | 128s | **83** | 781 |
| normal | 1 | 30s | 30 | 30 |

**Revisión del "suelo estructural ~130s" (06-22):** el suelo real es más bajo — p50 del ciclo shadow
= 83s, ciclo normal = 30s. Los ~130s promedio eran mezcla de carga, no piso del harness.

## 2. ¿Degradación por acumulación de contexto? — NO demostrada

Por tramo de sesión: ciclos 01-05 avg 213s (inflados por recoveries/arranque), 06-10 = 117s,
11-15 = 128s, 16+ = 189s. **No monotónico** → la hipótesis "el contexto acumulado ralentiza el ciclo"
no se sostiene con estos datos. La subida entre sesiones (52→121→195→229→190s) la explica la MEZCLA
de actividad: 06-22 fue día quieto (shadow/scan ligeros); 06-30 tuvo 7 fills FVG + 2 recoveries.

## 3. Outliers > 300s — 6 de 65 (9%), todos explicados

| Fecha | s | Tipo | Causa |
|---|---|---|---|
| 06-30 11:02 | 1002 | gap_recovery | Cold start + recovery + abort FVG |
| 06-29 10:15 | 781 | shadow | **Ciclo multi-trabajo**: gates 10:00 + S6 shadow + retroactivo |
| 06-30 13:21 | 383 | fill | **Multi-trabajo**: fill FVG + OCO + fix desprotegida + S6 eval |
| 06-30 12:54 | 381 | gap_recovery | Recovery 61 barras + S6 resolución + FVG stale |
| 06-24 10:07 | 369 | shadow | **Multi-trabajo**: gates 10:00 + SWP retroactivo (lat 666s) |
| 06-29 12:34 | 351 | shadow | S6 eval compleja |

**Patrón claro:** el presupuesto se rompe cuando UN ciclo hace VARIOS trabajos (gates + shadow + fill
+ recovery), no por lentitud del trabajo individual. Los gap_recovery son inevitables y raros (3).

## 4. Cadencia real de wakes — NO MEDIBLE con la instrumentación actual

Deltas entre logs: p50 380-1318s vs 300s de diseño. PERO `analysis_log` se salta el INSERT en ciclos
de 1 línea (ahorro de tokens, por diseño) y el heartbeat (`agent_status`) es un UPSERT de 1 fila sin
historia → **imposible distinguir "ciclo silencioso" de "loop muerto"** desde la DB. Los loop-gaps
reales existen (documentados 06-16/17/22) pero su magnitud no es cuantificable hoy. → Propuesta O1.

## 5. Veredicto gate Fase 4.1 ("ciclos < 5 min"): **CONDICIONADO**

- El ciclo típico CUMPLE holgado (p50 83-158s según tipo; 91% de ciclos < 300s).
- El riesgo son los ciclos multi-trabajo — y Fase 4.1 (multi-posición) los MULTIPLICA (más fills
  concurrentes = más ciclos fill+gestión+shadow). Recomendación: aplicar O1+O2 antes de adoptar 4.1
  y re-medir 3 sesiones.

## 6. Propuestas de optimización (priorizadas — NINGUNA aplicada sin OK)

- **O1 · Instrumentar cadencia (primero — evidencia antes que optimización):** añadir al UPDATE de
  STEP 9 (que ya corre cada ciclo, batched) un append barato `state.cycle_log += [hhmmss]` →
  cadencia real medible sin filas ni llamadas extra. Riesgo nulo. ~1 línea de spec.
- **O2 · Descargar el shadow en ciclos con acción:** si el ciclo ya hizo fill/gates/recovery, diferir
  el cómputo shadow al ciclo siguiente (las señales shadow se loggean, no se operan; el outcome lo
  resuelve el bar-sim de /post-close igual). Elimina la cola multi-trabajo (4 de 6 outliers).
  Riesgo: timestamp de log 5 min tarde (la señal conserva su ts de barra). Cambio de spec pequeño.
- **O3 · Recovery acotado (baja prioridad):** n=3 y en parte inevitables; optimizar solo si crece.
- **NO re-abrir:** split multi-agente (descartado 06-22 con evidencia — el cómputo shadow es ~3s del
  ciclo; el problema es la SECUENCIA de trabajos en un turno, no el cómputo).

**Siguiente paso propuesto:** aplicar O1 (solo instrumentación) ya; con 3-5 sesiones de cadencia real,
decidir O2 con números. Ambos requieren tocar `cycle_prompt.md` (v3.0.5) → OK del usuario.
