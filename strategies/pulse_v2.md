# Pulse v2.8

**Activa desde:** 2026-05-15 (v2.0) · **Actualizada:** 2026-05-28 (v2.8)  
**Reemplaza:** Pulse v1.x (VWAP pullback único, inicio 9:30 ET)  
**Activos:** **QQQ ONLY** — sin excepciones. (Tablas de sesiones T1-T6 abajo son registro histórico de cuando el universo incluía otros símbolos.)

> **Parámetros vigentes (sizing, SL/TP, cap riesgo, filtros) son los de `champion_strategy.config` en Supabase — single source of truth.** Las cifras de v2.4 en secciones inferiores se mantienen como referencia histórica del diseño.

---

## Por qué cambió

La sesión 2026-05-14 reveló tres fallos estructurales de v1.x:

1. **Apertura caótica (9:30–10:00 ET):** La única operación del día fue una entrada a los 9 minutos de apertura — sin régimen definido, sin VWAP estable — que alcanzó SL en 100 segundos. La apertura tiene volumen institucional extremo y precio errático. No hay suficiente información para tomar decisiones de entrada.

2. **Sin modo tendencia:** En días de tendencia fuerte (QQQ +$7) el precio nunca regresa a VWAP. v1.x simplemente no opera — correcto, pero deja valor sobre la mesa. Tres setups perdidos por ~$40-60 en ganancia potencial.

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

Evaluar QQQ con barras de 5-min desde apertura:

| Condición | Régimen |
|-----------|---------|
| Precio > 0.8% sobre VWAP **y** movimiento desde open > 1.5% | **TREND** |
| Cualquier otra combinación | **RANGE** |

**Régimen TREND DOWN — restricción de entradas long (v2.3 — P1):**

Cuando el régimen sea TREND DOWN (precio y VWAP en caída desde apertura), las señales EMA21 tempranas son falsas. No entrar long hasta que se cumplan **ambas** condiciones:
1. Precio **≥ 1.5% por encima del low de sesión** en el momento de evaluación
2. **3 barras consecutivas de 5-min** cerradas por encima de EMA 21

Si solo se cumple una, observar pero no operar. En TREND DOWN, la EMA21 actúa como resistencia dinámica hasta que el reversal se confirma con estructura.

---

## Volume Profile — indicador primario (v2.8)

VP es **hard filter primario** para los 3 setups del árbol v2.7 (VWAP Pullback, Volume Absorption, ORB Breakout). **Excluido en FVG** — ver sección "Aislamiento explícito".

**Definiciones:**

| Concepto | Definición |
|---|---|
| Bin | Cubo de precio. `bin_size = max(0.01, round(yesterday_close × 0.0005, 2))` — fijo todo el día. |
| VPOC | Precio del bin con mayor volumen acumulado (midpoint del bin). Imán institucional. |
| VAH / VAL | Bordes superior/inferior del Value Area — bins consecutivos alrededor del VPOC que acumulan el **70% del volumen total**. |
| Yesterday profile | VPOC/VAH/VAL del RTH 9:30–16:00 ET de la sesión previa. Fijo desde pre-market. |
| Developing profile | VPOC/VAH/VAL acumulado del RTH 9:30 ET hasta el ciclo actual. Se actualiza cada ciclo. |
| Naked POC | VPOC de una de las **5 sesiones previas** que el precio aún no ha vuelto a tocar (no intersect con OHLC posteriores). Magneto pendiente. |

**Fuente:** `mcp__alpaca__get_stock_trades(symbol, start, end, feed="sip")` — tick por tick, ventana RTH only.

**Algoritmo Value Area (TPO 70%):**
```
1. VPOC_bin = argmax(volume_by_bin)
2. covered = volume_by_bin[VPOC_bin]; lo = hi = VPOC_bin
3. while covered < 0.70 × total_volume:
     up_pair   = volume_by_bin.get(hi+1, 0) + volume_by_bin.get(hi+2, 0)
     down_pair = volume_by_bin.get(lo-1, 0) + volume_by_bin.get(lo-2, 0)
     if up_pair >= down_pair: hi += 2; covered += up_pair
     else:                    lo -= 2; covered += down_pair
4. VAH = (hi + 1) × bin_size; VAL = lo × bin_size; VPOC_price = (VPOC_bin + 0.5) × bin_size
```

**Persistencia:** `yesterday_profile`, `naked_pocs[]`, `bin_size` y `developing.{vpoc,vah,val,volume_by_bin}` viven en `session_state.state[symbol]` (JSONB). Pre-market siembra los tres primeros; cada ciclo actualiza `developing` incrementalmente y `last_tick_UTC`.

**Helper de evaluación:**
```
VP_lookup(symbol, price):
  in_yesterday_VA  = yesterday.VAL ≤ price ≤ yesterday.VAH
  in_developing_VA = developing.VAL ≤ price ≤ developing.VAH
  near_VPOC = (|price − yesterday.VPOC|   ≤ 0.001 × price)
           OR (|price − developing.VPOC|  ≤ 0.001 × price)
           OR (∃ npoc ∈ naked_pocs : |price − npoc| ≤ 0.001 × price)
  return { in_yesterday_VA, in_developing_VA, near_VPOC }
```

---

## Modo RANGE — VWAP Pullback

Igual al núcleo de v1.2, con feed actualizado.

**Condiciones de entrada (todas deben cumplirse):**

1. Precio pullback hasta ±0.15% del VWAP (5-min SIP como nivel de referencia)
2. Volumen del pullback decreciente barra a barra
3. **2 barras consecutivas verdes en 1-min IEX** cerrando por encima de la anterior (confirmación de bounce en tiempo real)
4. RSI (14 períodos, 5-min) entre 45 y 65
5. Hora entre 10:00 y 15:00 ET
6. **VP hard filter (v2.8):** el precio de evaluación del pullback está **dentro de [VAL, VAH] del perfil de ayer** O **dentro del developing Value Area de hoy**. Si está fuera de ambos VA, rechazar. *Tesis: pullbacks fuera de value son extensión que sigue corriendo antes de rebotar.*

**Flush de pánico — caso especial:**
- Si el pullback incluyó UNA sola barra de volumen extremo (>2x barra previa) seguida de recuperación con volumen decreciente: la señal es válida.
- Rechazar solo si hay **2 o más barras consecutivas** de alto volumen en la caída (venta sostenida institucional, no pánico puntual).

**Volume Absorption — señal adicional (v2.3 — P3):**
Entrada válida sin necesidad de pullback clásico cuando se cumplan todas:
1. Barra de 5-min con volumen **>3× el promedio de las 5 barras previas**
2. La barra cierra dentro de ±0.15% del VWAP o de un nivel de soporte identificado
3. La barra **no cierra en nuevo mínimo de sesión** (los vendedores no logran nuevo low)
4. EMA 21 por debajo del precio (hard filter normal aplica)
5. **VP hard filter (v2.8):** la barra de absorción cierra **dentro de ±0.10% de uno de**: VPOC de ayer, developing VPOC de hoy, o un **naked POC**. Si no, rechazar. *Tesis: la absorción institucional es fiable solo en nodos de alto volumen con interés estructural previo.*

Entrada: open de la barra siguiente. SL/TP: reglas P5 abajo.

**Parámetros de la orden (v2.4 — P5: TP Dinámico):**

| Parámetro | Valor |
|-----------|-------|
| Stop Loss | entry − 2×ATR(14, 1-min), calculado **post-fill** |
| TP1 | entry + 2×ATR → cerrar **50%** de la posición |
| TP2 | Próxima resistencia estructural (swing high, número redondo, session high) dentro de 5×ATR; si no hay nivel claro → entry + 4×ATR |
| Break-even | Al tocar TP1, mover SL a entry + $0.05 para proteger la ganancia |
| Tamaño | `floor(equity × 0.10 / entry_price)` — calculado antes de cada orden (P4) |

> **Aplicación práctica:** Identificar la resistencia estructural más cercana en barras de 5-min antes de colocar la orden. Si está entre 2×ATR y 5×ATR del entry, ese es el TP2. La ejecución usa bracket solo para TP1; el 50% restante se cierra manualmente al tocar TP2 o se deja con trailing SL.

---

## Modo TREND — Opening Range Breakout (ORB)

Activado cuando la detección de régimen a las 10:00 ET clasifica el día como tendencia.

**Construcción del rango:**
- Barra de apertura: 9:30–9:45 ET (3 barras de 5-min)
- `ORB_HIGH` = máximo de las 3 barras
- `ORB_LOW` = mínimo de las 3 barras

**Condiciones de entrada long (breakout alcista):**

1. Precio cierra una barra de 5-min **por encima de `max(ORB_HIGH, yesterday.VAH)`** (v2.8). Si `ORB_HIGH < yesterday.VAH`, el breakout efectivo requiere superar VAH — no basta ORB_HIGH. *Tesis: un break sobre ORB_HIGH pero dentro del value area de ayer es rotación intra-value, no ruptura.*
2. Volumen de la barra de breakout > promedio de volumen del ORB
3. Banda de Bollinger superior BB(20,2) en 5-min está expandiéndose (ancho actual > ancho promedio últimas 5 barras)
4. Hora entre 9:45 y 11:00 ET (ventana ORB)

**Entrada:** Open de la siguiente barra de 5-min tras confirmación  
**Stop:** Bajo el ORB_HIGH (el nivel roto se convierte en soporte)  
**Target:** ORB_HIGH + (ORB_HIGH − ORB_LOW) × 1.5 (proyección de 1.5x el rango)

> Breakout bajista (short) no se opera — activos preferidos tienen sesgo long y el sistema es paper trading long-only por simplicidad.

---

## Entradas adicionales — Setups independientes

Esta sección define vías de entrada que **operan en paralelo** al árbol RANGE/TREND principal. **No comparten filtros** con el modo activo (EMA, VWAP, RSI, chop, TREND DOWN) **ni los condicionan**. Tienen reglas propias completas y sizing dedicado.

### FVG (Fair Value Gap) — entrada adicional independiente

Setup standalone basado en ICT (Inner Circle Trader). Detecta gaps de liquidez no rellenados como zonas de entrada precisa con invalidación clara.

**Definición FVG alcista (3 velas consecutivas):**
- Vela 1: cualquier vela
- Vela 2: vela de impulso alcista (no se solapa con la 3 en el sentido del gap)
- Vela 3: vela alcista cuyo `low > high(vela 1)`
- Gap = rango `[high(vela 1), low(vela 3)]`
- Midpoint = `(high(vela 1) + low(vela 3)) / 2`

**Condiciones de entry (todas autocontenidas):**

| Parámetro | Valor |
|---|---|
| Detección | Scan últimas 15 barras de 1-min IEX (preferente) y 5-min SIP (secundario) |
| Entry trigger | Precio retorna al rango del gap y **toca el midpoint** |
| Confirmación | Cierre de la barra de entry dentro del gap con volumen ≥ avg últimas 5 barras |
| SL | `low(vela 1) − $0.02` |
| TP1 | 2:1 R/R sobre el SL → cerrar 50% |
| TP2 | Swing high previo a la formación del FVG **o** 3:1 R/R (lo que llegue primero) |
| Sizing | `floor(equity × 0.05 / entry_price)` — independiente del 8% de v2.7 |
| Validez | Expira si: (a) precio cierra por debajo de `low(vela 1)` sin retest, o (b) pasan 20 barras sin retest |
| Order placement | Market order primero; OCO/bracket post-fill (igual patrón que v2.7) |
| Tag DB | `strategy='fvg_v1'` |

**Aislamiento explícito — qué NO aplica:**
- ❌ EMA 9 hard filter (10:00–11:15 ET)
- ❌ EMA 21 hard filter (≥11:15 ET)
- ❌ Buffer de slippage ±$0.25
- ❌ Restricciones TREND DOWN (3 barras / 1.5% above low)
- ❌ Filtro chop ATR(14,5m)/precio < 0.15%
- ❌ Cap riesgo $25 por trade
- ❌ Sizing 8% del equity
- ❌ Ventana 10:00–15:00 (FVG opera todo el horario activo)
- ❌ RSI mínimo 45
- ❌ **Volume Profile hard filter (v2.8)** — FVG no se filtra por value area ni por proximidad a VPOC/naked POC. Su tesis (gaps de liquidez ICT) es ortogonal al concepto de zonas de aceptación.

**Lo que SÍ se respeta (reglas de riesgo globales, no de setup):**
- ✅ Cap exposure total ≤70% del equity (regla de portafolio)
- ✅ Universo ético (no defense, no MRNA/PFE)
- ✅ Forced close escalonado EOD (15:00 +0.7%, 15:30 +0.4%, 15:55 todo)
- ✅ SGOV parking overnight

**Coexistencia con v2.7:**
Un mismo símbolo puede tener simultáneamente un trade abierto por v2.7 y un trade abierto por FVG. Cada uno con su propio SL/TP. No se cancelan ni reemplazan entre sí.

**Estado en `session_state`:**
Al inicio de cada ciclo, mantener lista de FVGs activos:
```json
{
  "active_fvgs": [
    { "symbol": "QQQ", "formed_at": "11:35", "low_bound": 728.40, "high_bound": 728.65, "midpoint": 728.525, "sl_level": 728.38, "expires_at": "11:55" }
  ]
}
```
Limpiar expirados al inicio de cada ciclo. Eliminar al ejecutar entry.

**Logging:**
- En `analysis_log.notes`: registrar "FVG detected: SYMBOL [low_bound]-[high_bound] at TIME" cuando se forma, independiente de observaciones del modo principal.
- En post-close: reportar P&L FVG **por separado** del P&L v2.7 para evaluar el setup en aislamiento.

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

| Regla                       | Valor                                                                     |
| --------------------------- | ------------------------------------------------------------------------- |
| Máx. posiciones simultáneas | 10                                                                        |
| Máx. pérdida diaria         | $500                                                                      |
| Ventana de entrada (RANGE)  | 10:00–15:30 ET                                                            |
| Ventana ORB (TREND)         | 9:45–11:00 ET                                                             |
| Sin entradas fase pasiva    | No abrir después de 15:30 ET                                              |
| Cierre forzado              | Posiciones abiertas a las 15:55 ET → salida market (`exit_type = 'TIME'`) |

Si la pérdida diaria alcanza $500, el sistema se detiene hasta el día siguiente.

### Re-entrada post-stop-hunt (v2.4 — P6)

Cuando un SL es barrido por un stop hunt, la re-entrada es válida bajo las siguientes condiciones:

1. El SL fue superado por **menos de $0.25** (sweep superficial, no ruptura estructural)
2. El precio revirtió en **≤ 2 barras** de 5-min y cerró de vuelta por encima del nivel clave
3. La barra de confirmación tiene volumen **≥ promedio de las 5 barras previas**
4. No han pasado más de **3 barras de 5-min** desde el sweep

Re-entrada: open de la barra siguiente a la confirmación. SL/TP: reglas P5 estándar.

> **Origen:** 2026-05-20 — T1 y T2 en QQQ barridos por $0.07–$0.18 con reversal inmediato. T3 re-entrada correcta en la barra siguiente capturó +$35.94 (2.40R). El patrón de sweep + reversal es sistemático en QQQ.

### Tamaño de posición (v2.3 — P4, obligatorio)

Antes de cada `place_stock_order` calcular:

```
shares = floor(equity × 0.10 / precio_entrada)
```

- Si `shares < 2` → skip the trade (R/R no justifica el coste de tiempo).
- No hay excepción. El tamaño debe calcularse en cada orden, no estimarse.

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

**Ajuste v2.3 — Buffer de slippage en hard filter (P2):**
Cuando el precio evaluado esté dentro de **±$0.25 del nivel EMA 21 (o EMA 9 en ventana temprana)**, exigir que el precio esté **por encima del nivel + $0.20** antes de enviar la orden. Esto protege contra slippage que viola el filtro en el fill.

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

Sesiones pre-2026-06-04 (cuando el universo aún incluía otros símbolos) archivadas en
`strategies/history/pulse_v2_session_archive.md` — kept como registro factual de cómo
evolucionaron las versiones v2.0 → v2.8. Sesiones post-2026-06-04 (universo QQQ-only)
se persisten en la tabla `session_memory` de Supabase.

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
| **v2.3** | **2026-05-19** | **+P1: en TREND DOWN exigir 3 barras sobre EMA21 + precio ≥1.5% del low antes de entrar long; +P2: buffer slippage +$0.20 cuando precio dentro ±$0.25 del hard filter; +P3: Volume Absorption como señal primaria (v >3×, en soporte/VWAP, sin nuevo mínimo); +P4: sizing obligatorio floor(equity×0.10/precio) verificado antes de cada orden** |
| **v2.4** | **2026-05-20** | **+P5: TP Dinámico — TP1=entry+2×ATR (cerrar 50%, mover SL a BE); TP2=próxima resistencia estructural o entry+4×ATR; +P6: re-entrada válida post-stop-hunt cuando sweep <$0.25 con reversal ≤2 barras y confirmación de volumen** |
| **v2.8** | **2026-05-28** | **+Volume Profile como hard filter primario (fuente: tick trades SIP, bin 0.05% del close de ayer): VWAP Pullback exige precio dentro de yesterday VA o developing VA; Volume Absorption exige cierre ±0.10% de VPOC/naked POC; ORB Breakout exige cierre sobre max(ORB_HIGH, yesterday VAH). FVG explícitamente EXENTO del filtro VP (tesis ICT ortogonal a value areas).** |
