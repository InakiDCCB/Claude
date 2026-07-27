# Spec E.1 — SMC: Formalización determinista de BOS/CHoCH + killzones como dato

**Activada:** 2026-07-02 · **Épica:** E (Investigación) · **Tipo:** research offline (no toca el loop)
**Decisiones previas (07-01):** SMC estándar (sin reglas Casapia) · killzones = DATO, gate solo con evidencia.

## Objetivo
Cerrar el tercer fork de E.1: convertir Market Structure (BOS/CHoCH) — hasta ahora discrecional —
en reglas deterministas backtesteables, medir si hay edge en QQQ 1-min, y etiquetar cada señal con su
killzone para MEDIR (no filtrar) la concentración horaria del edge.

## Definiciones deterministas (v1 — SMC estándar)
- **Swing (fractal n):** reutiliza `swings()` de `smc_backtest.py` (causal: confirmado en idx+n).
- **Estado de estructura:** `bull` tras cerrar sobre el último swing high confirmado; `bear` tras
  cerrar bajo el último swing low confirmado.
- **BOS up** = ruptura de swing high con estado ya `bull` (continuación).
- **CHoCH up** = ruptura de swing high con estado `bear` (cambio de carácter — reversal).
- **Entrada LONG:** open de la barra siguiente a la ruptura (momentum). SL = último swing low
  confirmado − 0.05. TP = tp_r × riesgo. Variante **displacement**: cuerpo de la barra de ruptura
  > k × promedio de cuerpos (10 previas) — el "desplazamiento" ICT.
- **Killzone (DATO):** `open` 9:30-11:00 · `mid` 11:00-11:30 · `lunch` 11:30-13:30 · `pm` 13:30+.
  Se etiqueta y se cruza; NO se usa como gate en v1.

## Método
`strategies/research/smc_structure_backtest.py` (reusa Day/simulate/stats + swings). Grid:
n ∈ {2,3} × tp_r ∈ {1.5, 2.0} × kind ∈ {bos, choch, ambos} × displacement ∈ {off, 1.3×} (+C4 en las
mejores). Reporte: N/HIT%/PnL/PF/max-losses + cruce por killzone del mejor set.

## Criterios de aceptación
1. Detección 100% causal (nada usa barras futuras salvo la confirmación fractal estándar).
2. Veredicto por evidencia: PF y hit por variante; **shadow SOLO si aparece edge** (referencia: los
   sistemas vivos entraron con PF ≥ 1.65-1.9 en backtest); si no hay edge → anti-hallazgo documentado
   (como el espejo short naïve y el OB crudo).
3. Killzone reportada como distribución del edge (dato para MI/futuros gates con min-N).
4. Entregable: script + resultados en `docs/audit_smc_structure_2026-07-02.md` + actualización de
   `smc_study.md`/backlog. La decisión de añadirlo al shadow batch es del usuario.
