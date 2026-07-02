# E.1 — BOS/CHoCH formalizado + killzones como dato — 2026-07-02

> Spec: `docs/specs/E1_smc_bos_choch.md`. Script: `strategies/research/smc_structure_backtest.py`
> (reusa Day/simulate/stats/swings; detección 100% causal). Muestra: 39 sesiones (05-01 → 06-26),
> grid 24 variantes. Los 3 forks de E.1 quedan RESUELTOS.

## 1. Veredicto principal: BOS/CHoCH standalone = SIN EDGE (anti-hallazgo)

| Corte | N | HIT% | PnL/sh | PF |
|---|---|---|---|---|
| Mejor variante global (n2 tp2.0 bos+displacement) | 105 | 39.0 | +10.63 | **1.13** |
| Rango del grid completo (24 variantes) | 71-207 | 33-44 | −16.90 a +10.63 | **0.84-1.13** |

Listón de entrada de los sistemas vivos: PF ≥ 1.65-1.90 en backtest. **Ninguna variante se acerca.**
Consistente con el OB crudo (PF ~0.9-1.0): los conceptos SMC aislados no producen edge standalone en
QQQ 1-min. → **NO pasa a shadow.** Se suma a los anti-hallazgos (no re-probar sin premisa nueva).

## 2. Killzones como dato — el hallazgo que sí pagó

Cruce del set base (n2 tp2.0 ambos, 180 señales):

| Killzone | N | HIT% | PnL/sh | PF |
|---|---|---|---|---|
| **open** (9:30-11:00) | 53 | 41.5 | **+14.19** | **1.23** |
| mid (11:00-11:30) | 12 | 16.7 | −5.16 | 0.64 |
| lunch (11:30-13:30) | 59 | 35.6 | −10.58 | 0.80 |
| pm (13:30+) | 56 | 41.1 | +2.63 | 1.07 |

Corte fino: **CHoCH × open = 47.1% hit, +$18.72, PF 1.49 (n=34)** — la celda más interesante del
estudio. ⚠️ Tratamiento honesto: es un subset post-hoc (mismo riesgo de overfit que invalidó el
risk-band FVG en 32d) y sigue bajo el listón → **NO se propone como sistema**. Queda registrado como
dato: coincide con el indicio horario de C.1 (10h fuerte, 11h débil) — la estructura de QQQ paga en
la primera hora y muere en lunch. Si el usuario quisiera perseguirlo, el único camino válido es un
forward-test shadow explícito (decisión suya), no otro refinamiento in-sample.

Nota: 'first break' del día = 0 trades evaluables (ocurre antes de la ventana de entrada 10:00 —
declarado, no es bug).

## 3. Acciones tomadas (killzone = dato, en vivo)

- `smc_shadow.py`: cada señal OB del batch lleva ahora `kz` (open/mid/lunch/pm) → la distribución
  horaria del edge se acumula sesión a sesión en `shadow_signals` sin gate alguno.
- Cuando cualquier celda killzone × sistema cruce min-N con efecto, el camino formal es el de
  siempre: patrón → hipótesis → decisión usuario (consistente con `no-time-gates` relajada).

## 4. Estado de los 3 forks E.1 — CERRADOS

| Fork | Resolución |
|---|---|
| Casapia vs estándar | **SMC estándar** (decisión 07-01) — este estudio la ejecuta |
| Killzones | **Dato primero** (decisión 07-01) — medido en backtest + etiquetado en shadow vivo |
| BOS/CHoCH determinista | **Formalizado y backtesteado** — sin edge standalone (este doc) |

## 5. Siguiente experimento propuesto → EJECUTADO mismo día (addendum §6)

**Confluencia estructura×OB:** la tesis SMC real nunca fue "OB solo" ni "BOS solo", sino su
confluencia (entrada en OB solo cuando el estado de estructura es favorable, p.ej. OB post-CHoCH).
OB solo = PF ~0.95 · estructura sola = PF ~1.0 · ¿confluencia? — era la última pregunta abierta.

## 6. ADDENDUM — Confluencia OB × carácter (aprobado usuario, `smc_confluence_backtest.py`)

| Corte (39 sesiones) | N | HIT% | PnL/sh | PF |
|---|---|---|---|---|
| OB×CHoCH tp1.5 / tp2.0 / tp3.0 | 115/115/110 | 42/34/28 | −1.85 / +0.61 / +7.78 | 0.95 / 1.02 / **1.21** |
| **OB×BOS** (continuación) tp* | 8-10 | **0-25** | negativo | **0.00-0.50** |
| OB×first | 3 | — | — | n irrelevante |
| CHoCH×open / ×mid (tp2.0, dato killzone) | 22 / 8 | 36/38 | +2.02 / +0.71 | 1.24 / 1.26 |

**Veredicto: la confluencia NO rescata al stream — SMC se CIERRA.** El mejor corte honesto
(OB×CHoCH tp3.0, PF 1.21) sigue bajo el listón 1.65. Dos datos útiles quedan registrados:
1. **OB post-continuación (×BOS) es TÓXICO** (≤25% hit, PF ≤0.5, n=10): comprar el retroceso tras
   una continuación ya extendida = comprar agotamiento. Si el OB shadow vivo llegara a veredicto,
   este filtro negativo (excluir post-BOS, ~8% de señales) sería el único ajuste con base.
2. Killzone reconfirma: lo poco positivo vive en open/mid y muere en lunch/pm — consistente con §2 y C.1.

**Cierre del stream SMC (07-02):** FVG (S2, live) y sweep (S4/S6, shadow) ya estaban dentro del
sistema y SON los conceptos SMC que funcionan. Las formalizaciones nuevas — OB crudo (~0.95),
estructura sola (≤1.13), confluencia (≤1.21) — no pagan en QQQ 1-min. Único superviviente en
validación: **OB shadow batch** (n=22, en curso). NO re-abrir sin premisa nueva o mercado distinto.
