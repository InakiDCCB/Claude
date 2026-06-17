# Horizon Shadow Lab

Acelerador **offline** de research de estrategias: escribes una hipótesis en lenguaje natural,
se compila a una Strategy IR y se backtestea sobre tus datos reales `qqq_1min.json` usando
**el mismo motor que ya tienes** (`backtest.py` + `backtest_short.py`). Devuelve métricas y un
**Horizon Score** con veredicto `DEPLOY / PAPER / KILLED`.

Es la adaptación nativa del concepto del vídeo "Horizon AI Quant Agent" a este repo:

```
frase ─► [horizon_parser] ─► Strategy IR ─► [horizon_lab.compile] ─► run_market/run_fvg(QQQ 1-min) ─► stats() ─► Horizon Score
```

## ⚠️ Qué NO es (no interfiere con el loop)

- **NO** coloca órdenes, **NO** escribe en Supabase, **NO** toca `cycle_prompt.md` ni el loop.
- Es distinto del **"shadow" del loop** (S1/S4/S5/S6), que loggea señales teóricas en
  `analysis_log.indicators.shadow_signals` durante la sesión. Esto es un **laboratorio offline**
  para evaluar ideas en segundos sobre la data ya acumulada.
- Sirve a la directiva STANDING `project_new_systems_research`: probar hipótesis nuevas rápido.
  El flujo de promoción no cambia: una idea con veredicto fuerte aquí → se promueve a **shadow del
  loop (5 sesiones)** a mano → recién entonces LIVE.

## Uso

Desde `strategies/research/` (stdlib puro, mismo Python que el resto del research):

```powershell
python horizon_lab.py "FVG con maximo 2 fills al dia"
python horizon_lab.py "RSI2 sobrevendido por debajo de 15" --since 2026-05-01
python horizon_lab.py "sweep de maximos de sesion en corto con rechazo"
python horizon_lab.py "pullback a VWAP" --json
```

Opciones: `--since YYYY-MM-DD` (primera sesión, default `2026-05-01`) · `--no-llm` (fuerza el
parser por reglas) · `--json` (salida estructurada).

## Parser NL → IR (dos modos)

1. **Por reglas (default, sin claves):** palabras clave + regex (es/en). Frágil pero instantáneo.
2. **Con Claude (recomendado):** refleja el vídeo. Exporta la clave y se activa solo:
   ```powershell
   $env:ANTHROPIC_API_KEY = "sk-ant-..."
   python horizon_lab.py "compra cuando barre el minimo de sesion y reconquista con volumen"
   ```
   Modelo configurable con `$env:HORIZON_MODEL` (default `claude-sonnet-4-6`). El SDK `anthropic`
   es opcional: si no está instalado o no hay clave, cae al parser por reglas.

## Familias de señal (mapean a tus factories existentes)

| signal | long → factory | short → factory (espejo) | params |
|---|---|---|---|
| `rsi2` | `rsi2_dip` | `rsi2_pop` | `thresh, tp, sl, time_stop` |
| `vwap_pullback` | `vwap_pullback` | `vwap_rejection` | `rsi_lo, rsi_hi, tp_r, be_at_r` |
| `sweep` | `sweep_reclaim` | `sweep_rejection` | `tp_r, min_depth` |
| `gap_fill` | `gap_fill` | `gap_fade` | `min_gap` |
| `fvg` | `run_fvg` | `run_fvg_short` | `max_fills, risk_lo, risk_hi` |
| `ema9_reclaim` | `ema9_reclaim` | — (long only) | `tp_r` |
| `vwap_band` | `vwap_band` | — (long only) | `mult, tp_r` |
| `red_run` | `red_run` | — (long only) | `tp, run_len` |

Los **defaults de cada familia = la config campeona del playbook 32 sesiones** (p.ej. `rsi2`
arranca en th<15 / tp 0.5×ATR5 / sl 1.0×ATR5 / ts45). Cada corrida reporta `base` y `+C4`.

## Horizon Score (heurística, calibrada al playbook)

`0–100 = Performance(0–50) + RiskMgmt(0–50)`:
- **Performance:** PF (mapeado 1.0→2.5) + hit% (mapeado 50→80).
- **RiskMgmt:** suficiencia de `n` (saturado en 30) + racha perdedora `mLL` (penaliza > 4).
- Penaliza `n < 20` (anti-sobreajuste) y capa a 35 si la expectancy es ≤ 0.
- Veredicto: `DEPLOY ≥ 65` · `PAPER ≥ 45` · `KILLED < 45`.

Referencias: el portfolio del playbook (69% hit, PF 1.90) puntúa DEPLOY; sistemas muertos OOS
(E9RC/VPOC, PF ≈ 1.0) puntúan KILLED. **No garantiza rentabilidad** — filtra rápido lo que no
tiene edge en la ventana. El veredicto es un punto de partida, no la decisión final.

## Archivos

```
horizon_parser.py   NL -> StrategyIR (Claude tool-use + fallback por reglas)
horizon_lab.py      IR -> backtest (reutiliza backtest.py + backtest_short.py) + score + CLI
HORIZON_LAB.md      este doc
```

No se modificó ningún archivo existente: el Lab importa `backtest.py`/`backtest_short.py` tal cual.
Re-correr con data nueva: `python fetch_data.py` (refresca `qqq_1min.json`) y vuelve a lanzar el Lab.
