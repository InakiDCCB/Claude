---
name: feedback-eod-close-sgov
description: Cierre escalonado por ganancia + parking en SGOV con ~95% del cash overnight
metadata:
  type: feedback
---

## Cierre escalonado por ganancia (intra-día)

Para cada posición abierta, evaluar cada ciclo en la ventana de tarde:

| Hora ET | Regla |
|---|---|
| ≥15:00 | Si el trade lleva **≥+0.7%** sobre entry → cerrar a market |
| ≥15:30 | Si el trade lleva **≥+0.4%** sobre entry → cerrar a market |
| 15:55 | Cerrar **TODO** lo que quede (`exit_type='TIME'`) — ver [[feedback-forced-close]] |

Las reglas son acumulativas: a las 15:30 ambos thresholds (+0.7% pre-15:00 y +0.4% pre-15:30) son evaluables, se cierra si cualquiera se cumple.

## SGOV parking (overnight)

**Es la ÚNICA orden que se coloca DESPUÉS del cierre total de posiciones.** Antes de cualquier compra SGOV, confirmar `get_all_positions() == []` y sin órdenes de trading pendientes.

**Operativa (15:56–15:59 ET, antes del cierre del mercado):**
1. `get_account_info` → `cash`
2. `get_stock_latest_trade(SGOV)` → price
3. `qty = floor(cash × 0.95 / price)`
4. `place_stock_order(SGOV, buy, qty, type=market, time_in_force=day)`
5. Loggear en `trades` con `strategy='sgov_parking'`.

**Apertura siguiente sesión (9:50 ET, pre-análisis):**
- Primer paso del pre-análisis = `place_stock_order(SGOV, sell, all, type=market)` para liberar cash antes de que arranque el loop a las 10:00.

## Why

- Cash idle no rinde nada. SGOV (iShares 0-3 Month Treasury Bond ETF) genera yield ~5% anual ≈ $14/día sobre $100k equity. Cubre el costo de oportunidad de mantener cash overnight.
- SGOV es virtualmente sin riesgo (treasuries cortos), no se ve afectado por gaps de equities.
- Cumple el universo ético — ver [[project-universe-constraints]].
- Cierre escalonado captura ganancias parciales antes del último 30 min volátil y evita drawdown intraday.
- Olvidarlo cuesta yield: el 2026-05-28 se olvidó la compra y la orden quedó queued para next-day open, perdiendo overnight yield.

## How to apply

- En passive observation (15:45–16:00), agregar checks de cierre escalonado además del forced 15:55.
- Programar wakeups específicos a 15:00, 15:30 y 15:55 ET para asegurar evaluaciones puntuales.
- Si por alguna razón la ventana SGOV se pasó (>16:00) y la orden queda queued para next-open, **cancelarla** y rehacer el flujo en la ventana correcta al día siguiente. No dejar SGOV queued.
- SGOV NO entra en el universo de trading activo. Es solo cash parking — no aplicar filtros Pulse, no evaluar setups sobre él.
