---
name: feedback-trade-consolidation
description: 1 trade = 1 compra (no 1 venta); exit_price = promedio ponderado FIFO; no registrar hasta cierre 100%
metadata:
  type: feedback
---

Un **trade** en la tabla `trades` de [[ref-supabase]] = una **compra** (buy_to_open). Las ventas parciales que cierran esa compra NO son trades separados — son fragmentos del exit de un mismo trade.

**Reglas de consolidación FIFO:**

1. **Matching FIFO**: cada venta consume qty del lote de compra abierto más antiguo del mismo símbolo. Una sola venta puede cerrar parte de un lote y parte del siguiente.
2. **exit_price = promedio ponderado por qty** de todas las ventas que cierran el lote: `Σ(qty_sold_i × price_i) / Σ(qty_sold_i)`.
3. **pnl = realizado total del lote** (suma de pnl por fragmento).
4. **exit_type = predominante por qty** (el que cierra más acciones). En empate, el del último fragmento.
5. **NO registrar el trade hasta cierre 100% del lote.** Si queda qty open (overnight o intraday), el trade no se inserta. Cuando se cierre el resto en futura sesión, recién entonces se inserta la fila final.

**Why:**
- El usuario quiere ver "trades" como decisiones de entrada, no como mecánica de Alpaca. Una compra de 100sh saliendo en 4 tramos = 1 decisión, no 4.
- Registrar antes del cierre total infla el conteo y distorsiona el avg P&L por trade.
- El método anterior (1 fila por sell) llevó a double-counting el 2026-05-27 (14 filas reportadas → +$32.44, FIFO real +$39.13 con 4 trades).

**How to apply:**
- Al final de la sesión, **antes** de insertar trades, leer todas las órdenes filled del día con `mcp__alpaca__get_orders(status=closed)`.
- Matching FIFO por símbolo: ordenar buys y sells cronológicamente, consumir buys con sells.
- Para cada buy 100% cerrado: insertar 1 fila con avg ponderado.
- Lotes con qty residual open: NO insertar.
- En `notes` listar los fragmentos de exit: `'FIFO consolidated: 340@14.82 TP1, 169@14.75 SL_BE, ...'`

**Schema mapping:**
- `price` = entry price del buy
- `quantity` = qty del buy original (no del sell)
- `exit_price` = promedio ponderado de ventas
- `pnl` = realizado total del lote
- `exit_type` = predominante
- `notes` = breakdown FIFO
