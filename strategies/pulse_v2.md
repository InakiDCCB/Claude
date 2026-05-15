# Pulse v2.2

**Activa desde:** 2026-05-15 (v2.0) · **Actualizada:** 2026-05-15 (v2.2)  
**Reemplaza:** Pulse v1.x (VWAP pullback único, inicio 9:30 ET)  
**Activos:** QQQ, TSLA, RIVN

---

## Por qué cambió

La sesión 2026-05-14 reveló tres fallos estructurales de v1.x:

1. **Apertura caótica (9:30–10:00 ET):** La única operación del día fue una entrada a los 9 minutos de apertura — sin régimen definido, sin VWAP estable — que alcanzó SL en 100 segundos. La apertura tiene volumen institucional extremo y precio errático. No hay suficiente información para tomar decisiones de entrada.

2. **Sin modo tendencia:** En días de tendencia fuerte (QQQ +$7, TSLA +$7) el precio nunca regresa a VWAP. v1.x simplemente no opera — correcto, pero deja valor sobre la mesa. Tres setups perdidos por ~$40-60 en ganancia potencial.

3. **Feed lag de 15 min en barras de 5-min:** Las señales se detectaban cuando ya habían corrido $2-3. Inaceptable para intraday.

---

## Arquitectura del sistema

```
10:00 ET
   └─ Detección de régimen
         ├─ TREND  → Modo ORB
         └─ RANGE  → Modo VWAP Pullback
```

### Detección de régimen (10:00 ET)

Evaluar QQQ y TSLA con barras de 5-min desde apertura:

| Condición | Régimen |
|-----------|---------|
| Precio > 0.8% sobre VWAP **y** movimiento desde open > 1.5% | **TREND** |
| Cualquier otra combinación | **RANGE** |

Si los dos activos no coinciden en régimen, prevalece **RANGE** (más conservador).

---

## Modo RANGE — VWAP Pullback

Igual al núcleo de v1.2, con feed actualizado.

**Condiciones de entrada (todas deben cumplirse):**

1. Precio pullback hasta ±0.15% del VWAP (5-min SIP como nivel de referencia)
2. Volumen del pullback decreciente barra a barra
3. **2 barras consecutivas verdes en 1-min IEX** cerrando por encima de la anterior (confirmación de bounce en tiempo real)
4. RSI (14 períodos, 5-min) entre 45 y 65
5. Hora entre 10:00 y 15:00 ET

**Flush de pánico — caso especial:**
- Si el pullback incluyó UNA sola barra de volumen extremo (>2x barra previa) seguida de recuperación con volumen decreciente: la señal es válida.
- Rechazar solo si hay **2 o más barras consecutivas** de alto volumen en la caída (venta sostenida institucional, no pánico puntual).

**Parámetros de la orden:**

| Parámetro | Valor |
|-----------|-------|
| Stop Loss | 0.3% bajo precio de entrada |
| Take Profit | 0.6% sobre precio de entrada (ratio 2:1) |
| Tamaño | Calculado para arriesgar máx. $50/trade |

---

## Modo TREND — Opening Range Breakout (ORB)

Activado cuando la detección de régimen a las 10:00 ET clasifica el día como tendencia.

**Construcción del rango:**
- Barra de apertura: 9:30–9:45 ET (3 barras de 5-min)
- `ORB_HIGH` = máximo de las 3 barras
- `ORB_LOW` = mínimo de las 3 barras

**Condiciones de entrada long (breakout alcista):**

1. Precio cierra una barra de 5-min **por encima de ORB_HIGH**
2. Volumen de la barra de breakout > promedio de volumen del ORB
3. Banda de Bollinger superior BB(20,2) en 5-min está expandiéndose (ancho actual > ancho promedio últimas 5 barras)
4. Hora entre 9:45 y 11:00 ET (ventana ORB)

**Entrada:** Open de la siguiente barra de 5-min tras confirmación  
**Stop:** Bajo el ORB_HIGH (el nivel roto se convierte en soporte)  
**Target:** ORB_HIGH + (ORB_HIGH − ORB_LOW) × 1.5 (proyección de 1.5x el rango)

> Breakout bajista (short) no se opera — activos preferidos tienen sesgo long y el sistema es paper trading long-only por simplicidad.

---

## Fases de la sesión

| Fase | Horario ET | Acción |
|------|-----------|--------|
| Apertura caótica | 9:30–10:00 | Sin operaciones. Datos para régimen. |
| Detección de régimen | 10:00 | Clasificar TREND / RANGE. |
| Trading activo | 10:00–15:30 | Entradas y gestión de bracket. |
| Observación pasiva | 15:30–16:00 | Sin nuevas entradas. Gestionar posiciones abiertas. Registrar observaciones en `analysis_log`. |
| Análisis post-cierre | ≥16:00 | Ver sección abajo. |

---

## Gestión de riesgo (ambos modos)

| Regla | Valor |
|-------|-------|
| Máx. posiciones simultáneas | 2 |
| Máx. pérdida diaria | $500 |
| Ventana de entrada (RANGE) | 10:00–15:30 ET |
| Ventana ORB (TREND) | 9:45–11:00 ET |
| Sin entradas fase pasiva | No abrir después de 15:30 ET |
| Cierre forzado | Posiciones abiertas a las 15:55 ET → salida market (`exit_type = 'TIME'`) |

Si la pérdida diaria alcanza $500, el sistema se detiene hasta el día siguiente.

---

## Indicadores de contexto (EMA / SMA)

Calculados sobre barras de 5-min SIP durante la sesión activa. **No son condiciones de entrada obligatorias en v2.1** — se registran en `analysis_log.indicators` como contexto y filtro de sesgo.

| Indicador | Período | Timeframe | Uso |
|-----------|---------|-----------|-----|
| EMA 5 | 5 | 5-min | Momentum inmediato |
| EMA 9 | 9 | 5-min | Señal rápida de tendencia |
| EMA 21 | 21 | 5-min | **Sesgo direccional** — precio > EMA 21 = sesgo long ✓ |
| EMA 34 | 34 | 5-min | Tendencia de media sesión |
| EMA 55 | 55 | 5-min | Tendencia establecida (Fibonacci) |
| SMA 100 | 100 | 1-hour | Soporte/resistencia mayor |
| SMA 200 | 200 | 1-hour | Tendencia primaria (bull/bear) |

**Aplicación práctica (v2.2):**
- **Ventana 10:00–11:15 ET** (EMA 21 aún sin suficientes barras — solo 14 barras desde apertura): usar **EMA 9** como proxy de sesgo direccional. **No entrar long si precio < EMA 9.**
- **Ventana 11:15 ET en adelante**: EMA 21 es condición de entrada **dura** — **no entrar long si precio < EMA 21** (rechazar, no reducir tamaño).
- En modo TREND (ORB): confirmar que precio > EMA 55 antes de entrar breakout.
- En análisis post-cierre: reportar posición relativa de SMA 100 y 200 para contexto de la sesión siguiente.

---

## Implementación — Loop de ciclos

Cada ciclo (~5 min) Claude ejecuta:

```
FASE TRADING ACTIVO (10:00–15:30 ET):
1. get_clock → verificar mercado abierto y fase
2. get_all_positions → gestionar posiciones abiertas (TP/SL alcanzado)
3. get_stock_bars (1-min IEX) → señales en tiempo real
4. [Si 10:00 ET y primer ciclo] → detección de régimen
5. Calcular VWAP acumulado + EMAs (5, 9, 21, 34, 55) desde 5-min SIP
6. Evaluar setups según modo activo + sesgo EMA 21
7. Si hay señal → place_stock_order (bracket)
8. Registrar ciclo en analysis_log (incluir EMAs) + heartbeat en agent_status
9. [Si algún activo está dentro de ±0.30% del VWAP pero sin setup completo] → reducir ScheduleWakeup a 90s (zona de alerta, setup inminente)

FASE OBSERVACIÓN PASIVA (15:30–16:00 ET):
1. get_clock → confirmar fase pasiva
2. get_all_positions → gestionar posiciones abiertas
3. [Si posición abierta a las 15:55 ET] → cerrar a market (exit_type = 'TIME')
4. Registrar observaciones de mercado en analysis_log (sin órdenes nuevas)

ANÁLISIS POST-CIERRE (≥16:00 ET):
Ver sección siguiente.
```

---

## Análisis post-cierre (≥16:00 ET)

Claude ejecuta automáticamente al cierre del mercado:

### 1. Resumen de trades del día
- Listar todos los trades del día desde `trades` con P&L real
- Calcular: win rate, ratio promedio R:R, P&L total, mayor ganancia y mayor pérdida

### 2. Revisión de setups válidos vs ejecutados
- Identificar señales que cumplieron condiciones pero **no se operaron** (missed setups)
- Identificar señales que se operaron pero **no deberían** (false signals)
- Calcular el P&L teórico de los setups perdidos

### 3. Análisis de errores y ajustes
Revisar cada trade contra el checklist de condiciones:
- ¿Volumen en pullback era decreciente?
- ¿RSI estaba en rango 40–65?
- ¿Precio dentro del ±0.15% VWAP?
- ¿Las 2 barras verdes cerraban claramente por encima?
- ¿EMA 21 apoyaba el sesgo?

### 4. Contexto de indicadores para la sesión siguiente
- Posición de precio vs SMA 100 y SMA 200 (1-hora)
- Tendencia de EMA 55 (¿expansión o contracción?)
- Niveles clave de soporte/resistencia para el día siguiente

### 5. Propuestas de ajuste al spec
Si se identifica un patrón recurrente (≥2 sesiones), proponer modificación concreta al spec con evidencia.

---

## Historial de sesiones

### 2026-05-15 — Pulse v2.0 → v2.2

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

---

## Registro histórico de versiones

| Versión | Fecha | Cambio principal |
|---------|-------|-----------------|
| v1.0 | 2026-05-13 | VWAP pullback básico, inicio 9:30 ET |
| v1.1 | 2026-05-13 | +2 barras verdes de confirmación |
| v1.2 | 2026-05-14 | +IEX 1-min para confirmación; refinamiento flush de pánico |
| v2.0 | 2026-05-15 | +Inicio 10:00 ET; +detección de régimen; +modo ORB/TREND; feed 1-min |
| v2.1 | 2026-05-15 | +Ventana extendida 10:00–15:30 ET; +fase observación pasiva 15:30–16:00; +análisis post-cierre; +EMAs 5/9/21/34/55 y SMAs 100/200 como indicadores de contexto; cierre forzado 15:55 |
| **v2.2** | **2026-05-15** | **+RSI mínimo 45 (antes 40); +EMA 21 hard filter para longs (antes soft/reduce tamaño); +EMA 9 proxy en 10:00–11:15 ET cuando EMA 21 inválida; +ciclo 90s en zona de alerta ±0.30% VWAP** |
