# Pulse v2.x — Session Archive

> Archivo histórico de sesiones del agente Pulse antes de la reducción del universo a **QQQ-only** (2026-06-04).
> Mantiene registro factual de trades y observaciones que guiaron las versiones v2.0 → v2.8 cuando el universo incluía QQQ, TSLA y RIVN.
> Para sesiones futuras (post-2026-06-04, universo QQQ-only) usar `session_memory` table en Supabase.

---

## 2026-05-20 — Pulse v2.3 → v2.4

| Campo | Valor |
|-------|-------|
| Régimen | RANGE (QQQ y TSLA recuperación desde lows de sesión) |
| Trades | 6 |
| Win rate | 50% (3/6) |
| P&L total | **+$63.69** |
| R:R promedio (ganadores) | 1.70:1 |
| Mayor ganancia | TSLA TP +$38.88 (T4) |
| Mayor pérdida | QQQ SL −$28.00 (T1) |

**Trades:**

| # | Activo | Qty | Entrada | Salida | Tipo | P&L | Notas |
|---|--------|-----|---------|--------|------|-----|-------|
| T1 | QQQ | 14 | $708.50 | $706.50 | SL | −$28.00 | Stop hunt — sweep $706.51, reversal inmediato a $709+. |
| T2 | QQQ | 14 | $709.12 | $708.13 | SL | −$13.86 | Segundo stop hunt — low $707.82, rebote inmediato. |
| T3 | QQQ | 14 | $709.97 | $712.54 | TP | +$35.94 | Re-entrada P6 post-hunt. Breakout session high. 2.40R. |
| T4 | TSLA | 24 | $412.50 | $414.12 | TP | +$38.88 | EMA21 bounce. 5 barras sobre EMA21 post stop-hunt 11:41. 1.69R. |
| T5 | TSLA | 24 | $413.46 | $414.97 | TP | +$36.34 | EMA21 bounce. Entry 0.51 tarde → RR comprimido a ~1:1. |
| T6 | TSLA | 24 | $413.81 | $413.58 | SL | −$5.61 | SL calculado pre-fill → buffer $0.21 vs 2×ATR=$0.58. Paró en 1 min. |

**Observaciones clave:**
- Stop hunt pattern QQQ: T1 y T2 barridos por $0.07–$0.18. El sweep + reversal ≤2 barras = señal de re-entrada válida (T3).
- T6 confirma la regla SL post-fill: el SL debe calcularse **después** del fill real, nunca con precio estimado.
- TP fijo dejó valor: T5 con TP dinámico 4×ATR habría capturado $415.18 (session high $415.12).
- Análisis Situacional: hoy H=$415.12 < lunes H=$420.64 → **predicción jueves: low de hoy $406.49 será visitado**.

**Propuestas generadas → implementadas en v2.4:** P5 TP Dinámico (TP1=2×ATR 50%, TP2=estructura/4×ATR, break-even tras TP1), P6 re-entrada post-stop-hunt.

---

## 2026-05-19 — Pulse v2.2 → v2.3

| Campo | Valor |
|-------|-------|
| Régimen | TREND DOWN (detectado 10:10 ET, QQQ rompió $700 con v=6,830) |
| Trades | 3 |
| Win rate | 66.7% (2/3) |
| P&L total | **−$1.01** |
| R:R promedio (ganadores) | 1.76:1 |
| Mayor ganancia | QQQ TP +$1.02 |
| Mayor pérdida | QQQ SL −$3.02 |

**Trades:**

| # | Activo | Qty | Entrada | Salida | Tipo | P&L | Notas |
|---|--------|-----|---------|--------|------|-----|-------|
| 1 | QQQ | 10 | $698.83 | $698.53 | SL | −$3.02 | EMA21 cross 11:34 ET en TREND DOWN. Fill $0.58 adverse ($0.03 debajo de EMA21). SL 41s después. |
| 2 | QQQ | 1 | $701.49 | $702.51 | TP | +$1.02 | Breakout continuation sobre session high $700.46. Hold 8m30s. |
| 3 | QQQ | 1 | $704.01 | $705.00 | TP | +$0.99 | EMA9 pullback retest 12:58 ET. R/R 1.94:1. |

**Error crítico de sizing:** Trades 2–3 con 1 share en lugar de 10. Con 10% consistente P&L = **+$17.08**.

**Missed setup:** 12:50 ET volume absorption (v=5,719 = 3× promedio, en soporte $702.84). R/R 4.7:1. No ejecutado por esperar confirmación de precio.

**Observaciones clave:**
- TREND DOWN: EMA21 actuó como resistencia en 3 intentos consecutivos (11:19 rechazado, 11:34 SL, 11:54 sell-off). Reversal real confirmado a las 12:15 ET con 3 barras sobre EMA21.
- Buffer de slippage necesario: precio a $0.03 del hard filter es demasiado marginal para market order.
- Volume Absorption identificado como señal superior al EMA pullback en condiciones de reversal.

**Propuestas generadas → implementadas en v2.3:** P1 restricción TREND DOWN, P2 buffer slippage, P3 Volume Absorption, P4 sizing obligatorio.

---

## 2026-05-15 — Pulse v2.0 → v2.2

| Campo | Valor |
|-------|-------|
| Régimen | RANGE |
| Trades | 3 |
| Win rate | 66.7% (2/3) |
| P&L total | **+$181.06** |
| Net R | +4.42R |
| R:R promedio (ganadores) | 2.65:1 |
| Mayor ganancia | RIVN TP +$112.50 |
| Mayor pérdida | TSLA SL −$43.91 |

**Trades:**

| # | Activo | Qty | Entrada | Salida | Tipo | P&L | Notas |
|---|--------|-----|---------|--------|------|-----|-------|
| 1 | TSLA | 39 | $427.93 | $426.81 | SL | −$43.91 | VWAP pullback 10:43 ET. Setup válido, stop normal. |
| 2 | QQQ | 23 | $709.72 | $714.61 | TP | +$112.47 | VWAP pullback ~10:05 ET. TP limpio. |
| 3 | RIVN | 1250 | $13.91 | $14.00 | TP | +$112.50 | Flush-pánico 14:28 ET (×16 vol). Sub-penny rounding aplicado. |

**Setups perdidos:** QQQ ~14:35 ET (ciclo ocupado confirmando RIVN TP). P&L potencial ~$25.

**Observaciones clave:**
- Primera sesión con flush-pánico correctamente identificado y ejecutado (RIVN).
- Bug `status='pending'` en Supabase detectado y corregido → documentado en CLAUDE.md: actualizar a `'filled'` antes de aplicar exits.
- EMA 21 inválida antes de 11:15 ET (solo 14 barras): los primeros 2 trades operaron sin ese filtro → origen de propuestas v2.2.A y v2.2.B.
- Sub-penny rounding (Alpaca rechaza precios con más de 2 decimales) → regla permanente.

**Propuestas generadas → implementadas en v2.2:** RSI 40→45, EMA 21 hard filter, EMA 9 proxy early session, ciclo 90s en zona de alerta.
