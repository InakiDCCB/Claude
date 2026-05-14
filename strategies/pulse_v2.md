# Pulse v2.0

**Activa desde:** 2026-05-15  
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
4. RSI (14 períodos, 5-min) entre 40 y 65
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

## Gestión de riesgo (ambos modos)

| Regla | Valor |
|-------|-------|
| Máx. posiciones simultáneas | 2 |
| Máx. pérdida diaria | $500 |
| Ventana de entrada (RANGE) | 10:00–15:00 ET |
| Ventana ORB (TREND) | 9:45–11:00 ET |
| Sin entradas los últimos 30 min | Cierre 15:30 ET — no abrir posiciones después de 15:00 ET |

Si la pérdida diaria alcanza $500, el sistema se detiene hasta el día siguiente.

---

## Implementación — Loop de ciclos

Cada ciclo (~5 min) Claude ejecuta:

```
1. get_clock → verificar mercado abierto
2. get_all_positions → gestionar posiciones abiertas (TP/SL alcanzado)
3. get_stock_bars (1-min IEX) → señales en tiempo real
4. [Si 10:00 ET y primer ciclo] → detección de régimen
5. Evaluar setups según modo activo
6. Si hay señal → place_stock_order (bracket)
7. Registrar ciclo en analysis_log + heartbeat en agent_status
```

---

## Registro histórico de versiones

| Versión | Fecha | Cambio principal |
|---------|-------|-----------------|
| v1.0 | 2026-05-13 | VWAP pullback básico, inicio 9:30 ET |
| v1.1 | 2026-05-13 | +2 barras verdes de confirmación |
| v1.2 | 2026-05-14 | +IEX 1-min para confirmación; refinamiento flush de pánico |
| **v2.0** | **2026-05-15** | **+Inicio 10:00 ET; +detección de régimen; +modo ORB/TREND; feed 1-min** |
