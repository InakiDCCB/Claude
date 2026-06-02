# Memory — Trading / Pulse

> Estrategia activa: **Pulse v2.8** (3 setups con árbol v2.7 + Volume Profile hard filter) **+ FVG v1** (independiente). Última consolidación: 2026-05-29.

## Usuario
- [Perfil de Inaki](user_inaki_profile.md) — paper trader QQQ/TSLA/RIVN en Alpaca, hispanohablante, conocimiento avanzado de trading

## Proyecto Pulse
- [Visión general Pulse](project_pulse_overview.md) — agente autónomo v2.8 con 4 setups; FVG aislado del resto
- [Restricciones permanentes del universo](project_universe_constraints.md) — QQQ/TSLA/RIVN long-only, lista ética de exclusión
- [Dashboard](project_dashboard.md) — Next.js Vercel; layout 6 niveles; cron-job.org sync cada minuto
- [Análisis situacional /situational](project_situational_analysis.md) — skill D-1 → D independiente, solo informativo

## Referencias externas
- [Supabase](ref_supabase.md) — project_id y tablas clave del sistema
- [Repo de skills locales](ref_skills_repo.md) — pre-market / post-close en `.claude/commands/` con git local
- [Vault de Obsidian](ref_obsidian_vault.md) — el directorio Trading es también el vault del usuario; memoria se lee en Obsidian

## Operativa de la sesión
- [Horario de sesión](feedback_session_schedule.md) — 9:50 pre-análisis · 10:00 loop · 15:45 passive · 15:55 forced close
- [Forced close 15:55](feedback_forced_close.md) — obligatorio; brackets DAY expiran a 16:00; GTC solo si overnight autorizado
- [EOD escalonado + SGOV parking](feedback_eod_close_sgov.md) — 15:00 +0.7%, 15:30 +0.4%, 15:55 todo; SGOV con 95% cash overnight
- [Ciclos directos](feedback_direct_cycles.md) — loop = conversación local con Alpaca MCP; cloud/CCR sin internet; reiniciar CLI si MCP falla
- [Loop ultra-terse](feedback_loop_terse.md) — una línea por ciclo; tablas/notas solo en eventos

## Registro y observaciones
- [Consolidación de trades](feedback_trade_consolidation.md) — 1 trade = 1 compra; FIFO; no registrar hasta cierre 100%
- [Observaciones pendientes](feedback_pending_observations.md) — OBS-1 entrada tardía · OBS-2 TP2 por lower-high; validar con ≥3 sesiones

## Filosofía y disciplina de estrategia
- [Filosofía de trading](feedback_trading_philosophy.md) — aprender el mercado es lo permanente; estrategias son reemplazables
- [Mantener Pulse v2.8 + FVG](feedback_stick_with_pulse.md) — no añadir momentum/chase sin ≥3 sesiones de evidencia
- [Sin filtro EMA](feedback_no_ema_filter.md) — eliminado el gate EMA9/EMA21 + buffer; solo VWAP/VA/ORB/FVG deciden entradas

## Preferencias del usuario
- [Estilo de decisión](feedback_decision_style.md) — propuestas opinionadas con tradeoffs explícitos
- [Local-first](feedback_local_first.md) — evita instalaciones/remotos cuando local funciona
- [Idioma](feedback_language.md) — conversación en español, código en su idioma original
