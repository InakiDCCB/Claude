---
name: feedback-stick-with-pulse
description: Mantener Pulse v2.8 + FVG sin añadir setups de momentum / chase. Evaluar ≥3 sesiones antes de proponer cambios estructurales
metadata:
  type: feedback
---

Mantener **Pulse v2.8** (VWAP Pullback + Volume Absorption + ORB + filtro Volume Profile) **+ FVG v1** sin añadir setups de momentum / chase / breakout improvisados. Cambios estructurales solo después de ≥3 sesiones de evidencia con la spec actual.

**Why:** Sesión 2026-05-28 (TREND UP day): Pulse v2.7 puro no disparó entradas. Para "aumentar agresividad" se añadió Momentum Breakout v2.7.2 (close > max prior 3 highs + vol filter). Resultado: 2 entradas, 0 wins (−$16.52). Ambos breakouts marginales ($0.05–$0.09 sobre prior highs) en mercado lateral → chop → exit manual. La lección: si Pulse no genera trades en un día concreto, **ese es el resultado correcto** — no inventar setups intra-sesión para forzar actividad.

**How to apply:**
- NO añadir Momentum Breakout, chase, ni breakout-style entries sin antes acumular ≥3 sesiones de evidencia con Pulse v2.8 + FVG puros.
- Si Pulse no genera trades en un día TREND, esa es la señal correcta — no inventar setups. Ver [[feedback-trading-philosophy]].
- Si el usuario pide "aumentar agresividad" en el momento → recordar este aprendizaje y proponer en su lugar: extender periodo de evaluación, esperar pullback, no chase.
- Cambios estructurales (nuevos setups, ajustes de filtros) solo después de patrón confirmado en ≥2-3 sesiones, validado en post-close.
- Excepción: ajustes operacionales puntuales (bin size de Volume Profile, manejo de SGOV, formato de log) no requieren ≥3 sesiones — son tuning, no cambios de estrategia.
