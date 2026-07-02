# Auditoría Integral del Sistema Shadow — 2026-07-01 (Épica C.1)

> Spec: `docs/specs/C1_shadow_audit.md`. Fuentes: `session_memory.observations` (agregados + arrays
> per-signal), vista `shadow_signals`, `market_conditions` + `market_context`. Read-only.
> **Regla de honestidad:** celdas con < 5 sesiones = *indicio*, nunca conclusión. Nada se promueve aquí
> (gate D.2, decisión usuario).

## 1. Cuadro acumulado (todas las fuentes reconciliadas, 06-11 → 07-01)

| Sistema | Sesiones c/señal | n | TP/SL/TIME | WR resueltas | P&L acum $/sh | Referencia backtest |
|---|---|---|---|---|---|---|
| **S1 RSI2** | 10 | 51 | 33/13/5 | **64.7%** | **−0.34** | 76% ±10pp → en el borde BAJO del rango |
| **S4 SWP** | 4 | 6 | 4/2/0 | 67% | +0.29 | ≈70% → consistente pero n mínimo |
| **S5 GAPF** | 1 | 1 | 0/1/0 | 0% | −1.76 | ≈50% → SIN muestra (gate casi nunca on) |
| **S6 SWPS** | 4 | 17 | 11/6/0 | **64.7%** | **+0.96** | ≈70% → 5pp abajo, único P&L acum positivo |
| **OB (SMC)** | 6 | 22 | 8/14/0 | 36% | +0.17 | sin edge en backtest (PF ~0.9-1.0) → confirma |

Per-signal con pnl individual (solo 28 señales RSI2 + 2 SWP disponibles): RSI2 **PF 1.19**,
expectancy +$0.055/sh, avg win +0.58 vs avg SL −1.11 — la estructura TP 0.5×ATR / SL 1.0×ATR exige
WR ≥ ~70% para pagar; a 64.7% el PF colapsa de 1.74 (backtest) a 1.19.

## 2. Cruces por condición (indicios — ninguna celda llega a 5 sesiones)

- **RSI2 × liquidez** — el hallazgo más fuerte: liq **alta** 83% WR +$4.15 (3 ses, n=18) vs liq
  **baja** 50% WR −$4.96 (6 ses, n=24). ➜ Coincide EXACTAMENTE con la hipótesis-ejemplo de la
  directiva Fase 3.1 ("en alta liquidez RSI2 rinde superior"). Camino formal: el motor MI la
  promoverá sola cuando la celda cruce PATTERN_MIN=5 sesiones. **No adelantar el veredicto.**
- **RSI2 × contexto:** `range` 88% (1 ses, el 06-15) · `explosive` 60% · `active` 57%.
- **OB × días sin clasificar** (06-23/25/26, días bajistas sin loop): 18% WR −$2.69 vs **55-57%**
  en días clasificados (active/explosive). Refuerza "OB largo sufre en días bajistas" —
  ajuste candidato (filtro contextual), PERO es hipótesis → validar vía MI, no aplicar ya.
- **SWPS × contexto:** `active` 75% (1 ses) vs `explosive` 43% (1 ses) — demasiado pronto.
- **Horario** (solo 30 señales con ts): 10h fuerte (4/4 TP), 11h débil (33%), 14h el bucket más
  grande (n=10, 57%, pnl −). Nada accionable con estos n; se re-evalúa cuando el análisis de
  killzones (E.1, decisión: dato-primero) etiquete todas las señales.

## 3. Calidad de entradas/salidas y ejecución

- MISS de fill: 1/51 RSI2 (limit no alcanzado) — la mecánica de entrada replica bien el backtest.
- TIME-stop share RSI2: 5/51 (~10%), pnl mixto — consistente con time-stop 15min del spec.
- Latencia shadow (informativa, no afecta sim): RSI2 avg 248s (max 1931 = gap-recovery), SWPS avg
  580s (max 3360). El edge real de timing se medirá solo cuando haya órdenes reales.
- **Lección 07-01 (SWPS):** trades de duración ~2min pueden tocar TP intra-ciclo sin que el loop lo
  vea → el bar-sim de /post-close es la fuente canónica de outcomes. Ya documentado en memoria.
- Días contaminados declarados: 06-12 (bug UTC/ET, muestreo no aleatorio), 06-16 (C4 counterfactual
  cambia la muestra viva). El 64.7% de RSI2 los INCLUYE; el día limpio de referencia dio 87.5%.

## 4. Hallazgos de datos (alimentan C.4)

- **D1 · Claves heterogéneas en observations:** 06-18 y 07-01 usan variantes (`shadow_rsi2`,
  `shadow_swps`, `shadow_gapf`) en vez de las canónicas (`rsi2/swp/gapf/swps/ob`) →
  `refresh_market_patterns()` (MI) NO las ve. **Propuesta:** (a) fijar en `/post-close` paso 4 la
  obligación de claves canónicas; (b) backfill puntual de 06-18/07-01 a claves canónicas (UPDATE,
  requiere OK).
- **D2 · Sesiones sin `market_conditions`** (06-23/25/26, loop no corrió) → cruces imposibles esos
  días. **Propuesta:** retro-clasificación desde barras diarias de Alpaca (extensión de
  `upsert_market_condition` o script batch). Documentar, no construir aún.
- **D3 · Cobertura logged vs resueltas:** 73 señales RSI2 loggeadas in-cycle vs 51 resueltas — el
  delta son señales bloqueadas por C4/gates (correcto, pero conviene loggear el motivo estructurado).

## 5. Clasificación (criterio del backlog; evidencia insuficiente = se dice)

| Sistema | Clasificación | Justificación |
|---|---|---|
| **S6 SWPS** | **Mayor potencial** | Único P&L acum positivo (+0.96/sh); n=17 ya cruza el mínimo del gate D; WR 64.7% aún 5pp bajo el target 70% → **EXTENDER hasta n≥25-30** antes de veredicto de promoción |
| **S1 RSI2** | **Observación + más muestra limpia** | 64.7% con días contaminados dentro; PF 1.19 no paga aún; el indicio liq-alta (83%) es la pista a vigilar — dejar que MI la consolide |
| **S4 SWP** | **Más muestra** | 67% consistente con backtest pero n=6 no dice nada |
| **S5 GAPF** | **Observación pasiva** | n=1 en 15 sesiones — hambruna estructural del gate (requiere gap<−0.3%); no es fallo de la estrategia, no consumir esfuerzo |
| **OB** | **Requiere ajuste (hipótesis)** | 36% WR global pero P&L ~breakeven por asimetría; el corte bajista/no-bajista sugiere filtro contextual → formular como hipótesis MI, no tocar el batch |

**Promociones a Live hoy: NINGUNA** — ningún sistema satisface su gate (D.2). La recomendación
operativa es dejar correr el loop sin interrupciones: el cuello es muestra, no análisis.

## 6. Acciones propuestas (requieren OK)

1. **P-C1a:** fijar claves canónicas de observations en `post-close.md` (doc-only, barato).
2. **P-C1b:** backfill 06-18/07-01 → claves canónicas (UPDATE 2 filas; hace visible su historia a MI).
3. **P-C1c (diferida):** retro-clasificación de market_conditions para días sin loop.
4. Re-auditar al llegar S6 a n≥25 o cuando alguna celda condición×estrategia cruce 5 sesiones.

---

## RESULTADO (mismo día — P-C1a + P-C1b aprobados y APLICADOS)

- `post-close.md`: claves canónicas ahora OBLIGATORIAS (advertencia explícita con la lección C.1).
- Backfill aplicado (originales preservados, campo `src` marca el origen). Re-corrido el motor MI:
  13 patrones context×strategy actualizados; celdas antes invisibles ya presentes
  (`swps×slow` n=2, `gapf×slow` n=1, `rsi2×slow` n=3); **0 hipótesis** — gates min-N aguantan. ✔
- P-C1c queda diferida como estaba.
