"""SMC confluencia — Order Block × carácter de estructura (E.1 addendum, 2026-07-02).

Última pregunta del stream SMC: OB solo (PF ~0.95) y estructura sola (PF ~1.0) no pagan;
¿paga el OB CONDICIONADO al carácter de la ruptura que lo genera?
  - kind='choch' → el OB nace de un cambio de carácter (reversal desde estado bear)
  - kind='bos'   → el OB nace de una continuación (estado ya bull)
  - kind='first' → primera ruptura del día (sin carácter)
Mecánica OB idéntica a smc_backtest.run_ob (limit al high del OB, SL bajo el OB, TP r×riesgo).
v1: el tracking de estado se pausa durante posiciones/pendings (igual que el motor OB base) — declarado.
Killzone etiquetada en la FORMACIÓN (dato, no gate).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from backtest import simulate, stats, ENTRY_MIN, ENTRY_MAX
from smc_backtest import build_days, swings
from smc_structure_backtest import killzone


def run_ob_conf(days, n=2, expiry=60, tp_r=2.0):
    trades = []
    for day in days:
        sh, sl_ = swings(day, n)
        sh_conf = sorted((idx + n, idx, px) for idx, px in sh)
        sl_conf = sorted((idx + n, idx, px) for idx, px in sl_)
        si = sj = 0
        brk_sh = brk_sl = None   # niveles pendientes de romper (consumibles)
        last_sl = None           # último swing low confirmado (pierna del OB)
        state = None
        pending, pos_until = None, -1
        for i in range(day.n):
            while si < len(sh_conf) and sh_conf[si][0] <= i:
                brk_sh = (sh_conf[si][1], sh_conf[si][2]); si += 1
            while sj < len(sl_conf) and sl_conf[sj][0] <= i:
                brk_sl = (sl_conf[sj][1], sl_conf[sj][2]); last_sl = brk_sl; sj += 1
            if brk_sl is not None and day.c[i] < brk_sl[1]:
                state = "bear"
                brk_sl = None
            if i <= pos_until:
                pending = None
                continue
            if pending is not None:
                if day.l[i] <= pending["px"]:
                    entry = min(day.o[i], pending["px"])
                    slp = pending["sl"]
                    if slp < entry:
                        xi, xp, xt = simulate(day, i, entry, slp, ("r", tp_r))
                        trades.append({"day": day.date, "kind": pending["kind"], "kz": pending["kz"],
                                       "xt": xt, "pnl": xp - entry})
                        pos_until = xi
                    pending = None
                    continue
                if day.c[i] < pending["sl"] or i - pending["placed"] >= expiry or i > ENTRY_MAX + 10:
                    pending = None
            if (pending is None and brk_sh is not None and last_sl is not None
                    and ENTRY_MIN <= i + 1 <= ENTRY_MAX
                    and day.c[i] > brk_sh[1] and last_sl[0] < brk_sh[0] < i):
                kind = "choch" if state == "bear" else ("bos" if state == "bull" else "first")
                ob = None
                for k in range(i - 1, last_sl[0] - 1, -1):
                    if day.c[k] < day.o[k]:
                        ob = k
                        break
                state = "bull"
                brk_sh = None
                if ob is not None and day.c[i] > day.h[ob]:
                    pending = {"px": round(day.h[ob], 2), "sl": round(day.l[ob] - 0.05, 2),
                               "placed": i, "kind": kind, "kz": killzone(i)}
    return trades


def row(tag, s):
    if not s:
        return f"{tag:<24}{'0':>4}"
    pf = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "inf"
    return (f"{tag:<24}{s['n']:>4}{s['hit']:>7.1f}{s['pnl']:>+9.2f}"
            f"{s['mean']:>+8.3f}{pf:>6}{s['mll']:>5}")


def main():
    days = build_days()
    print(f"Sesiones: {len(days)} ({days[0].date} -> {days[-1].date})")
    print(f"\n{'OB × carácter':<24}{'N':>4}{'HIT%':>7}{'PnL/sh':>9}{'mean':>8}{'PF':>6}{'mLL':>5}")
    for tp in (1.5, 2.0, 3.0):
        tr = run_ob_conf(days, n=2, tp_r=tp)
        for kind in ("choch", "bos", "first"):
            sub = [t for t in tr if t["kind"] == kind]
            print(row(f"tp{tp} OB×{kind}", stats(sub)))
        print(row(f"tp{tp} OB todos", stats(tr)))
        print()
    print("Killzone × carácter (tp2.0 — dato):")
    tr = run_ob_conf(days, n=2, tp_r=2.0)
    for kind in ("choch", "bos"):
        for kz in ("open", "mid", "lunch", "pm"):
            sub = [t for t in tr if t["kind"] == kind and t["kz"] == kz]
            print(row(f"  {kind}×{kz}", stats(sub)))


if __name__ == "__main__":
    main()
