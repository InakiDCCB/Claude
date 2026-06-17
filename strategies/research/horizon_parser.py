"""NL -> Strategy IR, adaptado a los sistemas REALES de este proyecto (QQQ 1-min).

Es la etapa "Parse + IR Build" del concepto Horizon, pero el enum de senal mapea
a las familias que ya tienen factory en backtest.py / backtest_short.py:

    rsi2 | vwap_pullback | sweep | gap_fill | fvg | ema9_reclaim | vwap_band | red_run

Dos caminos (igual que el resto del repo: stdlib puro, sin deps obligatorias):
  1) LLM (Claude) via tool use si hay ANTHROPIC_API_KEY y el paquete 'anthropic'.
  2) Fallback deterministico por palabras clave (es/en), sin red ni claves.

Universo fijo = QQQ (constraint del proyecto). No hay campo universe.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any

SIGNALS = ("rsi2", "vwap_pullback", "sweep", "gap_fill", "fvg",
           "ema9_reclaim", "vwap_band", "red_run")
DIRECTIONS = ("long", "short")
# Familias sin espejo short validado en backtest_short.py:
LONG_ONLY = {"ema9_reclaim", "vwap_band", "red_run"}


@dataclass
class StrategyIR:
    name: str
    signal: str
    direction: str = "long"
    params: dict[str, Any] = field(default_factory=dict)
    c4: bool = True               # 2 SL seguidos -> sistema off (regla del playbook)
    notes: str = ""

    def validate(self) -> "StrategyIR":
        if self.signal not in SIGNALS:
            raise ValueError(f"signal '{self.signal}' no soportada {SIGNALS}")
        if self.direction not in DIRECTIONS:
            raise ValueError(f"direction '{self.direction}' invalida {DIRECTIONS}")
        if self.direction == "short" and self.signal in LONG_ONLY:
            raise ValueError(f"'{self.signal}' no tiene espejo short validado "
                             f"(ver backtest_short.py). Usa long.")
        self.params = {**default_params(self.signal, self.direction), **(self.params or {})}
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_params(signal: str, direction: str) -> dict[str, Any]:
    """Defaults = config CAMPEONA del playbook 32 sesiones donde existe."""
    if signal == "rsi2":
        # S1 oficial: th<15 long / >85 short, tp 0.5xATR5, sl 1.0xATR5, ts45
        return {"thresh": 85 if direction == "short" else 15,
                "tp": 0.5, "sl": 1.0, "time_stop": 45}
    if signal == "vwap_pullback":
        return {"rsi_lo": 35 if direction == "short" else 45,
                "rsi_hi": 55 if direction == "short" else 65,
                "tp_r": 1.0, "be_at_r": None}
    if signal == "sweep":
        return {"tp_r": 0.5, "min_depth": 0.01}     # S4 SWP / S6 SWP-short
    if signal == "gap_fill":
        return {"min_gap": 0.003 if direction == "short" else -0.003}
    if signal == "fvg":
        return {"max_fills": None, "risk_lo": None, "risk_hi": None}  # v3.0.2 sin tope
    if signal == "ema9_reclaim":
        return {"tp_r": 0.5}
    if signal == "vwap_band":
        return {"mult": 2.0, "tp_r": 1.0}
    if signal == "red_run":
        return {"tp": "fpc", "run_len": 5}
    return {}


# --- Esquema de tool use para Claude ---
IR_TOOL_SCHEMA: dict[str, Any] = {
    "name": "emit_strategy_ir",
    "description": "Emite la IR estructurada de una estrategia intradia QQQ.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "signal": {"type": "string", "enum": list(SIGNALS),
                       "description": "rsi2=dip/pop RSI(2) 5m; vwap_pullback=pullback/rechazo "
                       "a VWAP; sweep=barrido de high/low+reclaim; gap_fill=gap fade; "
                       "fvg=fair value gap 3 barras; ema9_reclaim; vwap_band=banda sigma; "
                       "red_run=racha de velas."},
            "direction": {"type": "string", "enum": list(DIRECTIONS)},
            "params": {"type": "object", "description":
                       "rsi2:{thresh,tp,sl,time_stop} vwap_pullback:{rsi_lo,rsi_hi,tp_r,be_at_r} "
                       "sweep:{tp_r,min_depth} gap_fill:{min_gap} "
                       "fvg:{max_fills,risk_lo,risk_hi} ema9_reclaim:{tp_r} "
                       "vwap_band:{mult,tp_r} red_run:{tp,run_len}"},
            "notes": {"type": "string"},
        },
        "required": ["name", "signal", "direction"],
    },
}

SYSTEM_PROMPT = (
    "Eres un compilador de estrategias intradia para QQQ (velas 1-min, sistemas tipo "
    "FVG, RSI2, VWAP-pullback, sweep&reclaim, gap-fill). Recibes una frase y SIEMPRE "
    "llamas a emit_strategy_ir eligiendo la familia de senal mas cercana y rellenando "
    "parametros razonables. direction=short solo para rsi2/vwap_pullback/sweep/gap_fill/fvg."
)


def parse(sentence: str, use_llm: bool = True) -> StrategyIR:
    if use_llm and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _parse_llm(sentence).validate()
        except Exception as e:
            print(f"[parser] LLM no disponible ({e}); fallback por reglas.")
    return _parse_fallback(sentence).validate()


def _parse_llm(sentence: str) -> StrategyIR:
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=os.environ.get("HORIZON_MODEL", "claude-sonnet-4-6"),
        max_tokens=1024, system=SYSTEM_PROMPT, tools=[IR_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "emit_strategy_ir"},
        messages=[{"role": "user", "content": sentence}],
    )
    for block in msg.content:
        if getattr(block, "type", None) == "tool_use":
            d = block.input
            return StrategyIR(name=d.get("name", "estrategia"), signal=d["signal"],
                              direction=d.get("direction", "long"),
                              params=d.get("params", {}), notes=d.get("notes", ""))
    raise RuntimeError("sin tool_use")


# --------------------------- Fallback por reglas ---------------------------

def _num(pat: str, text: str, default):
    m = re.search(pat, text, re.IGNORECASE)
    return float(m.group(1)) if m else default


def _parse_fallback(sentence: str) -> StrategyIR:
    low = sentence.lower()
    direction = "short" if re.search(r"\b(short|corto|bajista|vender|fade|rechazo)\b", low) else "long"

    if re.search(r"\bfvg|fair value|imbalance|hueco|gap de valor\b", low):
        signal = "fvg"
        params = {}
        mf = re.search(r"(\d)\s*(?:fills?|llenad|por dia|/dia)", low)
        if mf:
            params["max_fills"] = int(mf.group(1))
    elif re.search(r"\brsi|sobrevent|oversold|sobrecompr|overbought|dip\b", low):
        signal = "rsi2"
        params = {}
        # umbral = numero tras palabra direccional (NO el "2" de "rsi2")
        th = re.search(r"(?:debajo de|below|encima de|above|umbral|threshold|"
                       r"menor que|mayor que|[<>])\D{0,4}(\d{1,3})", low)
        if th:
            params["thresh"] = int(th.group(1))
    elif re.search(r"\bsweep|barrido|liquidity|reclaim|reconquist\b", low):
        signal = "sweep"
        params = {}
    elif re.search(r"\bgap\b", low):
        signal = "gap_fill"
        params = {}
    elif re.search(r"\bema\s*9|media (?:exponencial )?9|reclaim ema\b", low):
        signal = "ema9_reclaim"
        params = {}
    elif re.search(r"\bband|banda|sigma|desviaci\b", low):
        signal = "vwap_band"
        params = {}
    elif re.search(r"\bvela.{0,6}roja|red run|racha\b", low):
        signal = "red_run"
        params = {}
    elif re.search(r"\bvwap\b", low):
        signal = "vwap_pullback"
        params = {}
    else:
        signal = "rsi2"          # default: la familia mas robusta del playbook
        params = {}

    return StrategyIR(name=f"{signal}-{direction}", signal=signal,
                      direction=direction, params=params, notes="parser-fallback")
