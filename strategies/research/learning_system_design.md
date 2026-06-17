# Sistema de Aprendizaje Continuo — Diseño Técnico (Fase 3)

**Estado: PROPUESTA. Nada de este documento está aplicado a la DB ni al loop.**
Fecha: 2026-06-17. Requiere aprobación antes de implementar (ver §13 Decisiones abiertas).

## 1. Objetivo y principios

Mejorar continuamente la **expectativa matemática ajustada por robustez y consistencia**
del sistema QQQ-only, usando exclusivamente resultados reales de paper trading.

Principios de diseño (de tus instrucciones):
- **QQQ únicamente.** El histórico legacy (TSLA/RIVN) se conserva pero queda fuera del ranking.
- **Basado en evidencia.** Nada de conclusiones con muestra insuficiente → guard de muestra mínima
  matemático (lower-bound de expectancy con shrinkage, no la media cruda).
- **Nunca eliminar.** Las estrategias con mal desempeño se **degradan en prioridad**, conservando
  todo su historial para reevaluación.
- **Adaptación controlada.** El sistema reordena prioridad y emite recomendaciones; NO crea reglas
  nuevas, NO cambia parámetros críticos, NO promueve a órdenes reales sin tu visto bueno.
- **Reutiliza la infra existente.** Las condiciones de mercado salen de gates ya calculados
  (`rvol30`, `xvwap60`, `ATR`, `gap_pct`); el cómputo vive en `/post-close`; la matemática pesada
  va en SQL (determinista, barata, sin riesgo de error del LLM).

## 2. Hallazgos de auditoría que resuelve

| Hallazgo Fase 2 | Cómo lo resuelve este diseño |
|---|---|
| **DQ1** taxonomía caótica (14 etiquetas/55 trades) | `strategy_registry` con IDs canónicos + `trades.strategy_id` + backfill por alias |
| **DC1** `champion_strategy` obsoleto | El ranking deriva el campeón automáticamente cada post-close |
| **DC2** métricas mezclan QQQ + legacy ($62 de $75 es legacy) | Ranking filtra `asset='QQQ'`; legacy → `archived`, visible aparte |
| **DQ2** validación shadow fina (GAPF/S6 = 0; RSI2 lat alta) | `shadow_trades` unifica shadow+live en el mismo modelo; tiers por muestra mínima |

## 3. Arquitectura de datos (DDL PROPUESTO — no aplicado)

Todo aditivo: no altera tablas calientes del loop salvo **una columna nullable** en `trades`.

### 3.1 `strategy_registry` — IDs canónicos
```sql
create table strategy_registry (
  strategy_id  text primary key,            -- 'fvg','vwappb','rsi2','swp','gapf','swp_short'
  name         text not null,
  family       text,                         -- 'fvg','mean_reversion','vwap','sweep','gap'
  direction    text not null default 'long' check (direction in ('long','short')),
  status       text not null check (status in ('live','shadow','archived','research')),
  spec_version text,                          -- p.ej. 'v3.0.3'
  since        date,
  aliases      text[] default '{}',           -- etiquetas raw históricas que mapean aquí
  notes        text,
  updated_at   timestamptz default now()
);
```

### 3.2 `trades.strategy_id` — normalización (conserva el raw)
```sql
alter table trades add column strategy_id text references strategy_registry(strategy_id);
-- backfill por alias (§4). La columna text `strategy` original se CONSERVA (provenance).
-- Going-forward: el loop escribe strategy_id canónico (nota mínima en cycle_prompt, Fase 5).
```

### 3.3 `shadow_trades` — resultados simulados resueltos (unifica shadow+live)
```sql
create table shadow_trades (
  id            uuid primary key default gen_random_uuid(),
  session_date  date not null,
  strategy_id   text not null references strategy_registry(strategy_id),
  direction     text not null default 'long',
  entry numeric, sl numeric, tp numeric,
  exit_price    numeric,
  exit_type     text check (exit_type in ('TP','SL','TIME')),
  pnl_per_share numeric,            -- normalizado a 1 share → comparable con live
  latency_s     numeric,
  signal_ts timestamptz, eval_ts timestamptz,
  source        text default 'shadow' check (source in ('shadow','backtest')),
  created_at    timestamptz default now()
);
```
`/post-close` ya simula los outcomes de `analysis_log.shadow_signals`; aquí se persisten resueltos.
**Esto es la lectura segura de Fase 4 ("etiquetar/registrar")** y la base de evidencia para una
eventual promoción a órdenes reales (que sigue siendo decisión tuya, §8).

### 3.4 `market_conditions` — clasificación por sesión (reusa gates)
```sql
create table market_conditions (
  session_date  date primary key,
  symbol        text not null default 'QQQ',
  rvol30 numeric, gap_pct numeric, open_loc text, xvwap60 int,
  day_range_pct numeric,                       -- (high-low)/open de la sesión
  liquidity   text check (liquidity in ('low','high')),    -- rvol30 < / >= 0.85
  volatility  text check (volatility in ('low','high')),   -- day_range_pct vs mediana móvil
  regime      text,                                          -- 'choppy'/'trend' (xvwap60>=6)
  quadrant    text,                                          -- 'HH','HL','LH','LL' (liq×vol)
  created_at  timestamptz default now()
);
```
Sin datos nuevos: todo sale de `session_state.gates` + barras del día que el loop ya tiene.

### 3.5 `strategy_performance` — snapshots fechados (evolución temporal)
```sql
create table strategy_performance (
  id bigserial primary key,
  as_of         date not null,
  strategy_id   text not null references strategy_registry(strategy_id),
  scope         text not null default 'all',        -- 'all'|'liquidity:high'|'volatility:low'|'quadrant:HH'...
  window        text not null default 'inception',   -- 'inception'|'trailing20'|'trailing50'
  n int, wins int, wr numeric, pf numeric,
  expectancy numeric, exp_se numeric, exp_lb numeric,   -- $/sh; exp_lb = lower bound
  pnl_total numeric, avg_win numeric, avg_loss numeric,
  max_drawdown numeric, avg_duration_min numeric,
  consistency numeric, robustness numeric,
  tier text, score numeric,
  unique (as_of, strategy_id, scope, window)
);
```
Una fila/día/estrategia/scope → la serie temporal sale gratis (tendencias mejora/deterioro).

### 3.6 Vistas de lectura (dashboard)
- `v_strategy_trades` = `trades` (QQQ) ∪ `shadow_trades`, con `strategy_id` + condición de su sesión.
- `v_strategy_ranking` = último snapshot `as_of`, scope `all`, window `inception`, ordenado por `score`.

## 4. Normalización del histórico (backfill, sin borrar)

Mapeo PROPUESTO (requiere tu confirmación — algunas legacy son ambiguas):

| strategy_id | status | aliases (raw) |
|---|---|---|
| `fvg` | live | `fvg_v1`, `fvg_v3` |
| `vwappb` | live | `vwappb_v3`, `vwap_pullback_v2` |
| `rsi2` | shadow | (sin trades live; histórico vía shadow_trades) |
| `swp` | shadow | — |
| `gapf` | shadow | — |
| `swp_short` | shadow | — |
| `legacy_pulse_v2` | archived | `pulse_v2`, `pulse-v2`, `Pulse v2.0`, `pulse-v2-range` |
| `legacy_pulse_v25` | archived | `pulse_v25`, `pulse_v26`, `Pulse v1` |
| `legacy_orb` | archived | `orb_v2` |
| `legacy_momentum` | archived | `momentum_breakout_v2.7.2` |
| `legacy_carryover` | archived | `carry-over` |

**Decisión de diseño:** solo `fvg`/`vwappb` reciben histórico legacy (mapeo limpio); el resto se
archiva 1:1 para no atribuir trades de otra época/instrumento a sistemas actuales. Validación:
`select count(*) from trades where strategy_id is null` = 0 tras el backfill (los 55 mapeados).

## 5. Clasificación de condiciones de mercado

| Dimensión | Métrica (ya existe) | Buckets |
|---|---|---|
| **Liquidez** (mínimo requerido) | `rvol30` | `low` <0.85 · `high` ≥0.85 (umbral ya usado por el gate FVG) |
| **Volatilidad** (opcional) | `day_range_pct` vs mediana móvil 20 sesiones | `low` · `high` |
| **Régimen** | `xvwap60` | `choppy` ≥6 · `trend` <6 (ya usado por VWAPPB) |
| **Cuadrante** | liquidez × volatilidad | `HH/HL/LH/LL` |

El desempeño se agrega por estrategia **y** por cada valor de scope, para responder "¿dónde opera
mejor/peor cada sistema?" con evidencia.

## 6. Función de ranking (transparente, robustez primero)

Por estrategia activa QQQ, sobre live ∪ shadow, en `inception` y trailing:
```
n        = nº trades
exp      = mean(pnl_per_share)                       # expectativa matemática (núcleo)
se       = stdev(pnl_per_share) / sqrt(n)
exp_lb   = exp − z·se        (z=1.0 por defecto)     # LOWER BOUND: castiga muestra fina/volátil
pf, wr, max_drawdown                                  # estándar
consistency = fracción de sesiones (≥1 trade) netas positivas        ∈ [0,1]
robustness  = 1 si exp_lb ≥ 0 en ≥2 condiciones de liquidez, si no penaliza
```
Score (0–100), solo si `n ≥ n_provisional`:
```
Score = 100·( 0.45·norm(exp_lb) + 0.20·(0.5·norm(pf)+0.5·norm(wr)) + 0.25·(consistency·robustness) )
        − 10·penalty(max_drawdown)
```
Pesos por defecto (tunables): **expectancy-LB domina (0.45)** porque ES el objetivo; calidad 0.20;
robustez/consistencia 0.25; drawdown resta. `norm()` = escalado a rangos del playbook
(p.ej. PF 1.0→2.5, WR 50→80%, exp_lb por $/sh).

**Tiers por muestra mínima** (anti-overfit, núcleo del principio basado en evidencia):

| Tier | Criterio | Efecto |
|---|---|---|
| `insufficient_data` | n < 20 | Sin Score; jamás supera a una establecida; permanece shadow |
| `provisional` | 20 ≤ n < 50 | Score calculado pero con `exp_lb` (penalización por SE alta) |
| `established` | n ≥ 50 (y ≥15 por condición para claims por-condición) | Elegible para mayor prioridad operativa |

## 7. Adaptación controlada — qué puede y qué NO

**Puede (automático, dentro de guardas):**
- Recalcular el ranking y reordenar **prioridad operativa entre sistemas ya LIVE**.
- **Degradar** prioridad de un sistema con deterioro persistente (`exp_lb < 0` en la ventana trailing
  W sesiones) — conservando historial.
- Emitir **recomendaciones** y "cambios sugeridos pendientes" (no se auto-aplican).
- Actualizar `champion_strategy` con el líder del ranking.

**NO puede (requiere decisión del usuario):**
- Crear reglas de trading nuevas o cambiar parámetros críticos (sizing, SL/TP, gates).
- **Promover un sistema shadow a órdenes reales** (tu decisión Fase 4 — además requiere n suficiente
  y, para `swp_short`, la mecánica short/borrow que NO existe).
- Eliminar cualquier estrategia (prohibido por diseño).
- Decidir sobre muestra insuficiente.

## 8. Integración con `/post-close` (flujo diario)

`/post-close` (≥16:00 ET) se extiende, en orden:
1. (ya hace) Resolver outcomes de `shadow_signals` → **insertar en `shadow_trades`** (resueltos).
2. Calcular la fila `market_conditions` del día (desde `session_state.gates` + barras).
3. `select refresh_strategy_performance(CURRENT_DATE)` → inserta snapshots (idempotente por unique).
4. Recalcular `v_strategy_ranking` → actualizar `champion_strategy` + recomendaciones.
5. (ya hace) `session_memory`. La narrativa del agente queda igual de barata (la matemática es SQL).

## 9. Dashboard (añadidos)

- **Ranking de estrategias**: score, tier, n, WR, PF, expectancy LB, prioridad, flecha de tendencia.
- **Evolución histórica** por estrategia (expectancy/PF desde snapshots).
- **Desempeño por condición de liquidez** (y cuadrante).
- **Recomendaciones / cambios sugeridos pendientes**.
- **Métricas QQQ-only** (corrige DC2) + vista separada `legacy/archived`.

Todo son lecturas de las vistas nuevas → no cambia el modelo de fetch del dashboard (server fetch
en paralelo → props), solo añade componentes.

## 10. Plan de implementación por sub-fases (cada una con su validación)

| Sub-fase | Contenido | Criterio de validación |
|---|---|---|
| **3A** | `strategy_registry` + `trades.strategy_id` + backfill | `strategy_id is null` = 0; recuento reconcilia 55; raw intacto |
| **3B** | `market_conditions` + backfill de las sesiones con datos | 1 fila/sesión con gates; buckets coherentes con session_state |
| **3C** | `strategy_performance` + función SQL + `v_strategy_ranking` | Re-correr da el MISMO snapshot (idempotente); FVG/RSI2 rankean > invalidadas; legacy excluido; n<20 = insufficient |
| **3D** | `shadow_trades` + extensión `/post-close` | Outcomes shadow resueltos = los que ya calcula post-close; live+shadow comparables en $/sh |
| **3E** | Componentes dashboard (ranking, evolución, condición, recomendaciones) | Cifras del dashboard = queries directas a las vistas; QQQ-only cuadra |

Cada sub-fase es un PR independiente, revisable, sin tocar la lógica de trading del loop.

## 11. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Muestra actual minúscula (QQQ live: fvg ~22, vwappb ~3; shadow fino) | Tiers + exp_lb evitan conclusiones; el sistema "no concluye" hasta tener n |
| Mezclar live (real) con shadow (simulado) infla confianza | `shadow_trades.source` marcado; el dashboard distingue; promoción a real = gate usuario |
| Backfill mal mapeado | Mapeo §4 es propuesta; se valida con recuentos y revisión antes de aplicar |
| Cambiar el insert de `trades` rompe el loop | `strategy_id` es nullable y aditivo; el loop sigue funcionando aunque no se setee |
| Sobre-optimización de pesos del Score | Pesos por defecto fijos y documentados; cambiarlos = decisión explícita |

## 12. Lo que NO hace (fuera de alcance, por diseño)
- No coloca órdenes ni promueve shadows a real (eso es Fase 4, con tu decisión).
- No crea estrategias nuevas ni cambia gates/sizing.
- No borra nada.

## 13. Decisiones abiertas que necesito de ti (antes de 3A)
1. **Mapeo de alias** (§4): ¿OK mapear solo `fvg`/`vwappb` y archivar el resto 1:1?
2. **Umbrales de muestra**: ¿`provisional` n≥20 / `established` n≥50? (alineado con tu playbook)
3. **Pesos del Score** (§6): ¿OK que expectancy-LB domine (0.45)?
4. **Métrica de volatilidad**: ¿`day_range_pct` vs mediana móvil, o prefieres ATR?
5. **Shadow en el ranking**: ¿incluirlo (marcado `simulated`) o rankear solo live hasta promover?
6. **Alcance dashboard ahora**: ¿3A–3D primero (datos) y 3E (UI) después, o todo junto?
