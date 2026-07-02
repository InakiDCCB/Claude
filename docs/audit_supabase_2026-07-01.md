# Auditoría Integral de Supabase — 2026-07-01 (Épica A.1)

> Solo lectura: catálogos pg_*, information_schema, advisors oficiales (security + performance) y
> queries de calidad de datos. **Ningún fix aplicado** — propuestas al final, gated por aprobación
> del usuario (metodología: documentar antes de modificar).

## 1. Esquema — inventario

- **15 tablas** / **8 vistas** / **7 funciones** / **3 triggers**. Todo en `public`.
- Tamaños triviales: la mayor es `analysis_log` (619 filas, 408 kB). Total BD < 2 MB.
- Triggers: `session_state_updated_at` (BEFORE UPDATE), `trg_trades_strategy_id` (BEFORE INSERT/UPDATE
  → auto-mapeo strategy→strategy_id). Correctos.
- FKs: `trades.strategy_id` y `strategy_performance.strategy_id` → `strategy_registry`. Íntegras.
- Constraints QQQ-only `NOT VALID` presentes en trades / analysis_log / volume_profiles /
  market_context / situational_analysis (por diseño, legacy grandfathered). `market_conditions`
  valida symbol con check normal. ✔

## 2. Calidad de datos — LIMPIA en el núcleo

| Chequeo | Resultado |
|---|---|
| Trades duplicados (order_id) | **0** |
| Trades huérfanos (filled sin exit) | **0** |
| Filas 'sell' (regla update-buy) | **0** |
| `strategy` / `strategy_id` NULL | **0 / 0** → **el `NOT NULL` de F.2 es seguro de aplicar** |
| exit_price sin pnl | **0** |
| session_memory fechas duplicadas | **0** |
| strategy_performance snapshots duplicados | **0** (el fix del bug UTC aguantó) |
| market_conditions sin market_context | **0** (backfill 3.1 completo) |
| Legacy no-QQQ (grandfathered, intencional) | trades 14 · analysis_log 216 · vp 10 — histórico, no tocar |

**Hallazgos de higiene:**
- **H1 · `agent_status` con 4 filas para 1 agente**: el spec usa `pulse-v3` (cycle_prompt STEP 8);
  `pulse` (status=running, 07-01), `pulse_v3` (running, 06-30) y `shadow-A4` (PoC descartado, 06-22)
  son huérfanas — el AgentGrid del dashboard muestra agentes "running" que no existen.
- **H2 · `champion_strategy` congelada desde 06-11** — el ChampionCard muestra config obsoleta.
  Decisión ya tomada: DEFERIR hasta que un sistema cruce tier (G). Solo se documenta.
- **H3 · columnas semi-sin-uso** en `analysis_log`: `outcome` (17/619) y `tags` (108/619). Inofensivas;
  no se propone borrarlas (romperían histórico), solo dejar constancia.

## 3. Seguridad (advisors oficiales)

| Nivel | Hallazgo | Detalle |
|---|---|---|
| 🔴 ERROR | **`strategy_registry` sin RLS** | Única tabla expuesta a PostgREST sin RLS: el rol `anon` podría ESCRIBIR en el catálogo de estrategias. Introducido en la migración Fase 3A. [Remediación](https://supabase.com/docs/guides/database/database-linter?lint=0013_rls_disabled_in_public) |
| 🔴 ERROR ×6 | **Vistas `v_market_*` con SECURITY DEFINER** | Las 6 vistas de Fase 3.1 (07-01) se crearon sin `security_invoker` (default definer): evalúan permisos del creador, no del consultante. Exposición real hoy = nula (las tablas subyacentes ya son anon-SELECT), pero es mala práctica y contrasta con `v_strategy_ranking`/`shadow_signals` que sí son invoker. [Remediación](https://supabase.com/docs/guides/database/database-linter?lint=0010_security_definer_view) |
| 🟡 WARN ×7 | **Funciones con search_path mutable** | Las 7 funciones plpgsql (aprendizaje + MI + triggers) sin `SET search_path` — vector de search-path hijacking. [Remediación](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable) |

## 4. Rendimiento

| Nivel | Hallazgo | Acción propuesta |
|---|---|---|
| 🟡 WARN | **Índice duplicado** `trades_order_id_key` + `trades_order_id_unique` (idénticos; el 2º tiene 15 usos, el 1º 0) | DROP del no usado |
| ⚪ INFO | FKs sin índice de cobertura (`trades.strategy_id`, `strategy_performance.strategy_id`) | Añadir (trivial a este tamaño; barato prevenirlo) |
| ⚪ INFO | `idx_situational_analysis_date` sin uso (tabla de 3 filas) | Mantener — la tabla crecerá con /situational |
| — | `trades_asset_idx` con 0 usos (universo QQQ-only ⇒ índice de valor único) | DROP opcional |

Sin consultas costosas: volúmenes minúsculos, dashboard hace SELECTs simples con LIMIT, funciones
corren 1×/día. **Escalabilidad**: a ritmo actual (~600 filas/mes en analysis_log) años de margen.
Riesgo futuro = ninguno estructural.

## 5. Preparación para el Sistema de Aprendizaje — LISTA

- Fase 3 (ranking) + Fase 3.1 (Market Intelligence) operativas: funciones deterministas ET-default,
  vistas públicas, gates min-N verificados (0 hipótesis espurias con 11 sesiones).
- `strategy_registry` como taxonomía canónica con FKs desde trades y performance. ✔
- Único gap real: **n** (muestra) — no arquitectura. El diseño snapshot + vistas soporta C.2/C.3/C.4
  sin cambios estructurales; C.4 (fuente única) puede construirse SOBRE `v_market_intelligence`.

## 6. Propuesta de fixes (NO aplicados — requieren OK del usuario)

**P0 — Seguridad (1 migración, reversible):**
1. `ALTER TABLE strategy_registry ENABLE ROW LEVEL SECURITY` + policy anon SELECT (igual al resto).
2. `ALTER VIEW v_market_context / v_market_patterns / v_market_hypotheses / v_emerging_context_labels /
   v_market_recommendations / v_market_intelligence SET (security_invoker = true)`.

**P1 — Hardening + higiene (misma migración o segunda):**
3. `ALTER FUNCTION … SET search_path = public, pg_temp` en las 7 funciones.
4. `DROP INDEX trades_order_id_key` (queda `trades_order_id_unique`, el usado).
5. `DELETE FROM agent_status WHERE name IN ('pulse','pulse_v3','shadow-A4')` (huérfanas; el heartbeat
   canónico `pulse-v3` queda).

**P2 — Opcional:**
6. Índices de cobertura FK: `trades(strategy_id)`, `strategy_performance(strategy_id)`.
7. `DROP INDEX trades_asset_idx` (valor único QQQ).
8. F.2 (`trades.strategy_id NOT NULL`) — validado como seguro (0 nulls); se ejecuta cuando F.2 se active.

**Verificación post-fix:** re-correr `get_advisors` (security → 0 ERROR; performance → sin WARN),
smoke del dashboard (vistas MI siguen sirviendo datos con anon), y un ciclo de heartbeat.
