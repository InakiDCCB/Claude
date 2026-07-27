"""SMC backtest — Market Structure (BOS / CHoCH) long sobre QQQ 1-min. E.1 (2026-07-02).

Formalización determinista SMC ESTÁNDAR (decisión usuario 07-01: sin reglas Casapia; killzones = DATO):
  - Swings fractal n (reusa smc_backtest.swings; causal, confirmado en idx+n).
  - Estado de estructura: 'bull' tras cerrar sobre el último swing high confirmado;
    'bear' tras cerrar bajo el último swing low confirmado.
  - BOS up   = ruptura de swing high con estado ya 'bull'  (continuación).
  - CHoCH up = ruptura de swing high con estado 'bear'     (cambio de carácter / reversal).
  - 'first'  = primera ruptura del día sin estado previo (sin carácter — se reporta aparte).
  - Entrada LONG: open de la barra siguiente a la ruptura. SL = último swing low confirmado − 0.05.
    TP = tp_r × riesgo. Variante displacement: cuerpo de la barra de ruptura > disp × promedio
    de cuerpos de las 10 previas.
  - Killzone etiquetada por señal (open 9:30-11:00 / mid 11:00-11:30 / lunch 11:30-13:30 / pm 13:30+)
    — SOLO dato, no gate.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from backtest import simulate, stats, ENTRY_MIN, ENTRY_MAX
from smc_backtest import build_days, swings


def killzone(i):
    if i < 90:
        return "open"
    if i < 120:
        return "mid"
    if i < 240:
        return "lunch"
    return "pm"


def run_structure(days, n=2, tp_r=2.0, kinds=("bos", "choch"), disp=None, c4=False):
    trades = []
    for day in days:
        sh, sl_ = swings(day, n)
        sh_conf = sorted((idx + n, idx, px) for idx, px in sh)
        sl_conf = sorted((idx + n, idx, px) for idx, px in sl_)
        si = sj = 0
        brk_sh = None     # swing high pendiente de romper (consumible)
        brk_sl = None     # swing low pendiente de romper (consumible — solo cambia estado)
        ref_sl = None     # último swing low confirmado (referencia para SL, no consumible)
        state = None
        pos_until, consec = -1, 0
        for i in range(day.n - 1):
            while si < len(sh_conf) and sh_conf[si][0] <= i:
                brk_sh = (sh_conf[si][1], sh_conf[si][2]); si += 1
            while sj < len(sl_conf) and sl_conf[sj][0] <= i:
                brk_sl = (sl_conf[sj][1], sl_conf[sj][2])
                ref_sl = brk_sl
                sj += 1
            # ruptura bajista → estado 'bear' (consumida para no re-marcar cada barra)
            if brk_sl is not None and day.c[i] < brk_sl[1]:
                state = "bear"
                brk_sl = None
            # ruptura alcista
            if brk_sh is not None and day.c[i] > brk_sh[1]:
                kind = "choch" if state == "bear" else ("bos" if state == "bull" else "first")
                state = "bull"
                brk_sh = None
                if i <= pos_until or (c4 and consec >= 2):
                    continue
                if kind not in kinds or not (ENTRY_MIN <= i + 1 <= ENTRY_MAX) or ref_sl is None:
                    continue
                if disp:
                    body = abs(day.c[i] - day.o[i])
                    lo = max(0, i - 10)
                    avgb = sum(abs(day.c[k] - day.o[k]) for k in range(lo, i)) / max(i - lo, 1)
                    if body < disp * avgb:
                        continue
                entry = day.o[i + 1]
                slp = round(ref_sl[1] - 0.05, 2)
                if slp >= entry:
                    continue
                xi, xp, xt = simulate(day, i + 1, entry, slp, ("r", tp_r))
                pnl = xp - entry
                trades.append({"day": day.date, "ei": i + 1, "kind": kind, "kz": killzone(i),
                               "entry": entry, "sl": slp, "xi": xi, "xp": xp, "xt": xt, "pnl": pnl})
                pos_until = xi
                consec = consec + 1 if pnl <= 0 else 0
    return trades


def row(tag, s):
    if not s:
        return f"{tag:<26}{'0':>4}"
    pf = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "inf"
    return (f"{tag:<26}{s['n']:>4}{s['hit']:>7.1f}{s['pnl']:>+9.2f}"
            f"{s['mean']:>+8.3f}{pf:>6}{s['mll']:>5}")


def main():
    days = build_days()
    print(f"Sesiones: {len(days)} ({days[0].date} -> {days[-1].date})")
    print("\nMarket Structure long (SMC estándar) — grid:")
    print(f"{'variante':<26}{'N':>4}{'HIT%':>7}{'PnL/sh':>9}{'mean':>8}{'PF':>6}{'mLL':>5}")
    for nn in (2, 3):
        for tp in (1.5, 2.0):
            for kinds, ktag in ((("bos",), "bos"), (("choch",), "choch"), (("bos", "choch"), "ambos")):
                for disp in (None, 1.3):
                    tag = f"n{nn} tp{tp} {ktag}{' disp' if disp else ''}"
                    print(row(tag, stats(run_structure(days, n=nn, tp_r=tp, kinds=kinds, disp=disp))))
    # 'first' (sin carácter) — referencia
    print("\n'first break' (sin estado previo, referencia):")
    print(row("n2 tp2.0 first", stats(run_structure(days, n=2, tp_r=2.0, kinds=("first",)))))

    # Cruce por killzone del set base (n2 tp2.0, ambos, sin disp) — killzone = DATO
    print("\nKillzone (n2 tp2.0 ambos — dato, no gate):")
    tr = run_structure(days, n=2, tp_r=2.0, kinds=("bos", "choch"))
    for kz in ("open", "mid", "lunch", "pm"):
        sub = [t for t in tr if t["kz"] == kz]
        print(row(f"  {kz}", stats(sub)))
    print("\nPor tipo (n2 tp2.0):")
    for kind in ("bos", "choch"):
        sub = [t for t in tr if t["kind"] == kind]
        print(row(f"  {kind}", stats(sub)))


if __name__ == "__main__":
    main()
