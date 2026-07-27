# R1 — Sentimiento de mercado + Reflexión estructurada (2026-07-03)

Directiva del usuario: (1) medir el sentimiento/optimismo del mercado ("¿había exceso de
optimismo?" al analizar un shadow); (2) mecanismo Reflexion/Self-Refine adaptado a trading en
/post-close (¿por qué fallé? ¿por qué operé donde operé? ¿por qué no operé aquí o allá?).
Restricciones de diseño (del usuario, y núcleo del proyecto): **calidad de contexto > cantidad;
una herramienta mala BAJA el rendimiento; la arquitectura importa más que el LLM; el backtest
solo no basta (sobreajuste)**.

## Decisiones de diseño

1. **Sentimiento = CONTEXTO, jamás señal.** La familia vixcond (VIX alto/bajo/spike × sobreventa)
   murió en FDR (Lote 1) — el sentimiento como GATE de entrada es un anti-hallazgo conocido.
   Su uso legítimo: explicar en qué régimen rinde cada sistema (mismo tratamiento que killzones:
   dato primero, gate solo con evidencia min-N que hoy NO existe).
2. **Determinista, no vibes.** `strategies/research/sentiment_daily.py`: bucket
   euforia/optimismo/neutral/pesimismo/panico desde reglas FIJAS (VIX percentil 252d + racha de
   cierres + RSI2 diario + gap). El LLM solo corre el script. El canal cualitativo (titulares
   Alpaca get_news) queda OPCIONAL y pasa por el canal emergente existente (agent_note +
   candidate_label, gate ≥4 recurrencias) — cero vocabulario nuevo sin repetición.
3. **Medible por el motor existente, no decorativo.** Migración `r1_sentiment_patterns`:
   `refresh_market_patterns` cruza bucket × sistema → patterns `sn:<bucket>:<sid>` con los mismos
   gates min-N (5 sesiones/celda, consolidación a 8). "¿Exceso de optimismo cuando GTCL falla?"
   se responde con n, no con impresiones.
4. **Reflexión anclada a datos, taxonomía FIJA.** Autocritica libre del LLM = fábrica de
   intuiciones sin fundamento (violaría el núcleo). Adaptación:
   - P1 fallas → 6 modos cerrados (timing_tarde / regimen_adverso / ruido_stop / tesis_invalida /
     bug_mecanico / c4_correcto), cada uno con verificación definida en barras/latencias.
   - P2 cumplimiento → checklist objetivo (gate ON, pre-submit, OCO, sizing, prioridad);
     violaciones SIEMPRE al output (son bugs).
   - P3 no-operados → movimientos ≥0.5% sin posición, razón cerrada (sin_sistema /
     gate_bloqueo:<g> / c4_bloqueo / señal_perdida / reposo). `señal_perdida` = bug a investigar;
     `sin_sistema` recurrente = candidato a research.
   - **Máx 1 lesson/día**, formato verificable ("si X entonces Y (evidencia: hoy Z)");
     los viernes, lessons repetidas ≥3 sesiones se PROPONEN al usuario; el resto expira.
5. **Presupuesto de contexto: cero costo in-loop.** Todo corre en /post-close (sin presión de
   latencia). `observations.reflection` acotado (~15 líneas JSON). /load-memory lean NO carga
   reflections — emergen solo vía patrones/propuesta del viernes. Ninguna herramienta nueva
   toca el ciclo caliente.
6. **Contra el sobreajuste al backtest:** este mecanismo ES la evaluación forward — reflexión
   sobre operación real diaria + shadows en datos vivos + el A/B OB/OBNB. El backtest queda como
   filtro de entrada (FDR), no como juez final; los veredictos salen de la muestra viva.

## Piezas

| Pieza | Dónde |
|---|---|
| Sensor determinista | `strategies/research/sentiment_daily.py` (Yahoo VIX 1y + QQQ 6mo; 2 HTTP/día) |
| Escritura contexto | /post-close 4d: UPDATE `market_context.signature||sent` + tag `sent:<bucket>` |
| Cruce medible | migración `r1_sentiment_patterns` → patterns `sn:<bucket>:<sid>` |
| Reflexión | /post-close 4f (P1/P2/P3 + lesson) → `session_memory.observations.reflection` |
| Ciclo de lessons | viernes (con 4e): repetida ≥3 → propuesta al usuario; nunca auto-regla |

## Qué NO se construyó (y por qué)

- Sentimiento intradía / en pre-market: costo in-loop sin evidencia de valor; el diario basta
  para el cruce con shadows (que se resuelven al cierre).
- Índices externos (Fear&Greed, put/call, redes): scraping frágil o de pago; el bucket propio es
  reproducible y backfilleable (27y de VIX+QQQ en `data/` si algún día queremos historia).
- Score de sentimiento continuo: los buckets discretos alimentan celdas min-N; un continuo
  invita a sobreajuste con n chico.
- Auto-aplicación de lessons: toda promoción a regla pasa por el usuario (guardrail G).
