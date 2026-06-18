# Fase 4 — Promoción Shadow → Live (Diseño Técnico)

**Estado: PROPUESTA. Nada aplicado a `cycle_prompt.md` ni al loop.** Requiere aprobación.
Fecha: 2026-06-17.

## 1. Objetivo

Que S1 RSI2, S4 SWP, S5 GAPF (long) y S6 SWP-short empiecen a **enviar órdenes reales** a Alpaca
paper, cada trade etiquetado con su `strategy_id`. Así acumulan *n real* y el ranking de Fase 3 se
activa y arbitra prioridad. Los LIVE actuales (S2 FVG, S3 VWAPPB) se mantienen.

## 2. Decisiones del usuario (2026-06-17)
1. **Varias posiciones concurrentes**, con tracking estricto de qty por estrategia.
2. Promoción **incremental** (S1 → S4/S5 → S6).
3. Construir la **mecánica short ahora** (S6).
4. **Sizing 8%** equity para TODOS los sistemas (FVG/VWAPPB suben de 0.05 a 0.08).

## 3. ⚠️ Restricción crítica: long/short se netean en QQQ

Alpaca mantiene UNA posición neta por símbolo. Un long de S1 + un short de S6 en QQQ se combinan
→ rompe los OCO y la atribución. **Regla dura:**

> **Exclusión mutua de dirección sobre QQQ.** Los sistemas LONG apilan entre sí. El SHORT (S6)
> solo abre si `num_long_positions == 0`; ningún LONG abre si hay un short abierto. La dirección
> activa la fija la primera posición del momento; se libera al cerrarse todas.

## 4. Tracking de posiciones por estrategia

El bróter no sabe qué shares son de qué estrategia → lo trackeamos nosotros vía **el OCO de cada
estrategia** (cada OCO es una orden separada con su qty; al dispararse, el `oco_id` identifica la
estrategia que cerró).

**Cambio de estado:** `session_state.position` (objeto único) → `session_state.positions` (lista):
```json
"positions": [
  {"strategy_id":"rsi2_v3","dir":"long","qty":10,"entry":721.4,"tp":...,"sl":...,"oco_id":"...","opened_ET":"10:35"},
  {"strategy_id":"swp_v3", "dir":"long","qty":8, ...}
]
```
**Reglas de slot:** cada estrategia tiene **≤1 posición abierta a la vez** (su propio slot);
varias estrategias DISTINTAS coexisten. "Varias posiciones" = varias estrategias, no varias de la
misma. (FVG sigue siendo secuencial dentro de su slot — v3.0.2.)

**Atribución de qty (invariante):** `sum(positions[].qty con dir=long) == Alpaca net qty` (longs);
si difiere → STEP 3 reconcilia. Para short, `Alpaca net qty == −sum(qty)` con dir=short.

## 5. Sizing 8% + caps compartidos

- `shares = floor(equity × 0.08 / price)` para TODOS los sistemas (skip si < 2 o si rompe el cap).
- **Cap de exposición ≤ 70% equity** ahora es la **suma** de todas las posiciones abiertas:
  antes de colocar una entrada nueva, `Σ(qty×price abiertas) + entrada_nueva ≤ 0.70×equity`,
  si no → skip (log `exposure_cap`).
- **Pérdida diaria ≤ −$500**: suma del pnl realizado del día de TODOS los sistemas → hard stop
  (sin entradas nuevas de ningún sistema el resto del día).
- **C4 por sistema** (2 SL seguidos → ese sistema off hasta mañana) — sin cambio.

## 6. Mecánica de ejecución

### 6.1 Long (P1 — S1/S4/S5): reutiliza la máquina actual
Idéntico a FVG/VWAPPB: limit en la señal → al fill, OCO (TP arriba/SL abajo) con los 4 params
obligatorios → fila en `trades` con `strategy_id`. Triggers de señal = los que ya están en STEP 6b
(RSI2<15, sweep+reclaim, gap+EMA9). Solo cambia: pasa de "loggear" a "colocar + OCO + trade row".

### 6.2 Short (P2 — S6): OCO inverso
- Entrada: `place_stock_order(QQQ, qty, "sell", ...)` (sell-to-open → abre corto).
- Al fill, **OCO inverso**: `side="buy"`, `stop_loss_stop_price=SL` (ARRIBA), `take_profit_limit_price=TP` (ABAJO).
  `tp = round(fill − 0.5×(sl − fill), 2)`; `sl = sweep_high + 0.05`. (Espejo de `backtest_short.py`.)
- `pnl = entry − exit`. Cierre = buy-to-cover.
- Pre-requisito: shorting habilitado en la cuenta paper (QQQ es líquido → borrow trivial; verificar).

## 7. Cambios en `cycle_prompt.md` (por STEP)

| STEP | Cambio |
|---|---|
| Reglas | `positions` (lista); exclusión mutua long/short; sizing 0.08; cap 70% como suma |
| STEP 3 Seguridad | Reconciliación **multi-posición**: por cada `positions[]`, verificar su OCO; net qty Alpaca = suma trackeada |
| STEP 6 | S1/S4/S5 pasan de 6b (shadow) a 6 (live) con colocación + OCO; rama short S6 (sell-to-open + OCO inverso) |
| STEP 6b | Queda solo lo que aún no se promueva (durante el incremental) |
| STEP 7-fill | OCO por estrategia + `INSERT trades ... strategy='rsi2_v3'|'swp_v3'|'gapf_v3'|'swp_short_v3'` |
| STEP 9 estado | `positions` como lista; check de cap/exclusión |

## 8. `strategy_registry`

Añadir las etiquetas live como alias para que el trigger de 3A auto-mapee, y cambiar `status`
shadow→live conforme se promueve cada uno:
```sql
update strategy_registry set aliases = array['rsi2_v3'], status='live' where strategy_id='rsi2_v3';
-- idem swp_v3, gapf_v3, swp_short_v3 en su turno
```

## 9. Secuencia incremental (cada paso = validar en paper antes del siguiente)

- **4.1 — S1 RSI2 live** (mayor muestra shadow, el más validado del playbook). 1 sistema long nuevo.
- **4.2 — S4 SWP + S5 GAPF live** (long). Aquí ya se prueba el apilado de varios longs concurrentes.
- **4.3 — S6 SWP-short live** (OCO inverso + exclusión mutua). El de mayor riesgo y menor evidencia
  (n=13) → aislado y vigilado; el ranking no le dará prioridad hasta acumular n.

## 10. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Multi-posición = más superficie de fallo en el loop (histórico: bug ejecución 06-12) | STEP 3 reconciliación robusta como primera acción; invariante de qty; validar incremental |
| Long+short netean | Regla de exclusión mutua (§3) — dura, verificada en STEP 6 antes de colocar |
| Cap 70% mal sumado → sobre-exposición | Check de suma antes de cada entrada |
| Atribución qty se desincroniza del bróker | Invariante `Σqty = net qty`; si falla → reconciliar/cerrar |
| Edge short débil (n=13) | Va live para medir, pero el ranking lo mantiene sin prioridad hasta tener n |

## 11. Criterios de validación (por incremento)

- Toda fila `trades` nueva tiene `strategy_id` correcto (trigger + alias).
- `Σ positions[].qty == Alpaca net qty` en todo momento.
- Nunca long y short abiertos a la vez sobre QQQ.
- Exposición agregada ≤ 70% en todo momento; loss diario hard-stop a −$500.
- N sesiones paper sin incidente de reconciliación antes de pasar al siguiente incremento.

## 12. Decisiones abiertas restantes
- **A.** ¿Cuántas sesiones paper sin incidente exiges por incremento antes de avanzar (p.ej. 3)?
- **B.** ¿Tope de nº de posiciones concurrentes (p.ej. máx 4) además del cap 70%, o solo el cap?
- **C.** Cuando el cap/loss bloquea y varias estrategias señalan a la vez, ¿prioriza el de **mayor
  score del ranking** (recomendado) o el primero en el tiempo?
