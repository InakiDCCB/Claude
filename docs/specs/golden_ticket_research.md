# Golden Ticket — Fase 0: Research (Renaissance / Medallion por ingeniería inversa)

**Creado:** 2026-07-02 · **Estado: RESEARCH COMPLETO — implementación NO iniciada (arranca próxima
sesión con OK del usuario)** · Directiva: "reabrir el laboratorio; buscar combinaciones de métricas,
indicadores y datos de todo tipo" con la máxima **maximizar la ganancia de trading**.

---

## 1. Qué se sabe DE VERDAD de Medallion (con fuentes públicas)

| Hecho | Dato |
|---|---|
| Retornos 1988-2018 | **~66% bruto / ~39% neto** anualizado (fees 5% mgmt + 44% performance) |
| Tamaño | Capado ~$10B, solo dinero de empleados desde 2005 |
| Horizonte | Corto: días u horas; miles de posiciones simultáneas |
| Win rate | **~50.75%** por señal (Bob Mercer): "puedes hacer miles de millones así" — con VOLUMEN |
| Técnicas documentadas | **HMM** (~8 "estados" ocultos del mercado: high-variance, good…), regresión kernel, **mean reversion** ("ganamos dinero de las REACCIONES de la gente a los movimientos de precio"), stat-arb |
| Datos | Décadas de datos tick limpiados obsesivamente (Straus desde los 80) — la ventaja PREVIA a los modelos |
| Apalancamiento | 12.5×-20× vía basket options con bancos |
| Ejecución | Modelado de impacto/costos tan importante como las señales |

**El contraejemplo que nadie cita:** los fondos PÚBLICOS de Renaissance (RIEF/RIDA) — mismos
científicos, misma infraestructura — han tenido años mediocres e incluso pérdidas fuertes (2020:
Medallion +76%, RIEF ~−20%). **Ni Renaissance replica a Medallion fuera de Medallion.** El edge no
es una fórmula: es capacidad×datos×costos×apalancamiento×secreto a un tamaño capado.

## 2. Los 6 principios TRANSFERIBLES (la ingeniería inversa honesta)

1. **Muchas señales débiles > una señal fuerte.** No existe el indicador dorado; existe el ENSAMBLE
   de decenas de micro-edges de 50.5-52%, cada uno insuficiente solo. → El lab hoy tiene 7 sistemas;
   Medallion tenía miles. La dirección correcta es una FÁBRICA de señales, no otra señal.
2. **Datos primero.** Su ventaja empezó siendo datos más limpios y profundos que nadie. → Nuestro
   cache: ~2 meses de 1-min IEX. GT-0 = expandir a años de histórico + features derivadas.
3. **Anti-overfit industrial.** Probaban TODO pero con n masivo y validación despiadada — el lab ya
   vivió el modo de fallo (risk-band FVG, E9RC): buscar combinaciones sin protocolo estadístico
   FABRICA oro falso. El protocolo (walk-forward anidado + corrección por multiple testing + OOS
   intocable) es el corazón de Golden Ticket, no un accesorio.
4. **Frecuencia × costos.** 50.75% paga solo con miles de trades y costos modelados al centavo. →
   Coincide con la palanca #1 del lab (frecuencia); el modelado de slippage/fills ya existe (playbook).
5. **Regímenes ocultos (HMM).** Formalizable sobre lo ya construido: `market_context` es un
   clasificador de estados hecho a mano; un HMM-lite sobre returns/vol/volumen es el upgrade natural.
6. **Portafolio y sizing por señal.** Miles de posiciones pequeñas, riesgo por señal mínimo. →
   Versión lab: sizing por score/correlación entre señales sobrevivientes (encaja con Fase 4.1).

## 3. Honestidad sobre el objetivo "igualar los rendimientos año con año"

**No es comprometible, y decírtelo es parte de mi trabajo:** nadie ha replicado Medallion en 35
años — ni Renaissance mismo en sus fondos públicos. Además el lab opera 1 instrumento (QQQ-only,
tu regla), sin apalancamiento 12×, con 2 meses de datos: el corazón matemático de Medallion (ley de
grandes números sobre MILES de edges independientes en MILES de instrumentos) no es alcanzable con
un solo subyacente. **Lo que SÍ es alcanzable y medible:** aplicar sus principios para multiplicar
la expectancy del lab. Hitos propuestos (en vez del 66%):
- **M1:** ≥3 señales nuevas OOS-positivas e independientes entre sí (protocolo GT-2 completo).
- **M2:** ensamble en shadow > QQQ buy&hold ajustado por riesgo en 30 sesiones.
- **M3:** expectancy neta positiva con costos modelados → candidato a live (gate usuario).
- Recién con M1-M3: hablar de targets de CAGR con drawdown controlado.

## 4. Arquitectura propuesta (para construir la PRÓXIMA sesión)

- **GT-0 · Fundación de datos:** extender `qqq_1min` a 2+ años (Alpaca SIP histórico — el lag de
  15 min solo aplica a real-time, el histórico es completo); features derivadas por barra/bloque:
  returns multi-horizonte, vol realizada, perfiles de volumen, gaps, estacionalidad intradía/semanal,
  autocorrelaciones. **Decisión usuario pendiente:** ¿datos externos (SPY/VIX/TLT) como FEATURES de
  contexto — sin operarlos, QQQ sigue siendo el único instrumento operable?
- **GT-1 · Fábrica de señales:** generador sistemático de hipótesis por plantillas (mean-reversion
  k-barras, momentum condicional, estacionalidad, vol-condicional, cross-features, reacciones a
  movimientos — el "reactions" de Medallion). Cada hipótesis = config declarativa, no código nuevo
  (extiende el Horizon Lab NL→IR→backtest ya existente).
- **GT-2 · Protocolo estadístico (el corazón):** split train/validación/OOS intocable + walk-forward
  anidado + corrección FDR (Benjamini-Hochberg) por cada lote de hipótesis probadas + mínimo n +
  estabilidad entre regímenes (market_context) + SOLO las sobrevivientes pasan a shadow. Registro de
  TODO lo probado (también lo que falla — anti-hallazgos automáticos).
- **GT-3 · Ensamble:** scoring/pesos de señales sobrevivientes, correlación entre señales (no sumar
  señales gemelas), sizing por convicción — reutiliza el Score/tiers de Fase 3.
- **GT-4 · Integración:** las señales GT ganadoras entran al MISMO pipeline probado: shadow →
  `v_shadow_accumulated` → ranking → gate D.2 → decisión usuario. Cero atajos a live.
- **GT-5 (aspiracional, tras M1):** HMM-lite de regímenes (upgrade de market_context) usado como
  feature condicional de las señales.

## 5. Decisiones abiertas para la próxima sesión (usuario)

1. ¿Datos externos como features de contexto (sin operarlos)? — recomendado SÍ, respeta QQQ-only.
2. Profundidad de histórico objetivo (2 años ≈ 200k barras 1-min — manejable con el motor actual).
3. Umbral de promoción GT→shadow (recomendado: mismo listón PF ≥1.5-1.65 en OOS walk-forward).
4. Presupuesto de sesiones para GT-0+GT-1 (estimado: 1-2 sesiones de research/build).

**Fuentes:** [Zuckerman — The Man Who Solved the Market (notas)](https://novelinvestor.com/notes/the-man-who-solved-the-market-by-gregory-zuckerman/) ·
[HMMs y regresión en Medallion](https://medium.com/@ilyakavalerov/the-man-who-solved-the-market-and-the-solution-was-hmms-and-regression-dd60cea5a6d7) ·
[Medallion fund returns — QuantifiedStrategies](https://www.quantifiedstrategies.com/medallion-fund-returns/) ·
[Renaissance Technologies — Wikipedia](https://en.wikipedia.org/wiki/Renaissance_Technologies) ·
[Growth of $100 in Medallion — Visual Capitalist](https://www.visualcapitalist.com/growth-of-100-invested-in-jim-simons-medallion-fund/)
