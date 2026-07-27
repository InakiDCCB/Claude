"""SMC backtest — Order Block + Market Structure (BOS/CHoCH) sobre QQQ 1-min.

Primera formalización del estudio SMC (strategies/research/smc_study.md). Definiciones
SMC ESTÁNDAR (sin acceso a los cursos de Casapia). Long-only: Bullish Order Block v1.
Reutiliza Day / simulate / stats de backtest.py.

Definiciones deterministas (v1):
  - Swing (fractal n): swing high en i si high[i] >= n barras a la izq y > n a la der.
    Causal: un swing en idx se "confirma" en idx+n (no se usa antes).
  - BOS up (Break of Structure): close rompe el último swing high confirmado, con el último
    swing low ANTES de ese swing high (pierna alcista válida).
  - Order Block (bullish): la última vela ROJA de la pierna antes de la ruptura.
  - Entrada: limit pasivo en el HIGH del OB (retroceso al order block). SL = low_OB − 0.05.
    TP = tp_r × riesgo. Limit válido `expiry` barras o hasta close < low_OB.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from backtest import Day, simulate, stats, ENTRY_MIN, ENTRY_MAX

DATA = Path(__file__).parent / "data" / "qqq_1min.json"


def build_days(since="2026-05-01"):
    bars = json.loads(DATA.read_text())
    bydate = {}
    for b in bars:
        bydate.setdefault(b["t"][:10], []).append(b)
    dates = sorted(bydate)
    days_all, prev = {}, None
    for d in dates:
        days_all[d] = Day(d, bydate[d], prev)
        prev = days_all[d]
    return [days_all[d] for d in dates if d >= since]


def swings(day, n=2):
    """Swing highs/lows por fractal de n barras. Devuelve dos listas de (idx, price)."""
    h, l, m = day.h, day.l, day.n
    sh, sl = [], []
    for i in range(n, m - n):
        if (all(h[i] >= h[i - k] for k in range(1, n + 1))
                and all(h[i] > h[i + k] for k in range(1, n + 1))):
            sh.append((i, h[i]))
        if (all(l[i] <= l[i - k] for k in range(1, n + 1))
                and all(l[i] < l[i + k] for k in range(1, n + 1))):
            sl.append((i, l[i]))
    return sh, sl


def run_ob(days, n=2, expiry=60, tp_r=2.0, c4=False):
    trades = []
    for day in days:
        sh, sl = swings(day, n)
        sh_conf = sorted((idx + n, idx, price) for idx, price in sh)   # (conf_bar, idx, price)
        sl_conf = sorted((idx + n, idx, price) for idx, price in sl)
        pending, pos_until, consec_sl = None, -1, 0
        last_sh = last_sl = None
        si = sj = 0
        for i in range(day.n):
            while si < len(sh_conf) and sh_conf[si][0] <= i:
                last_sh = (sh_conf[si][1], sh_conf[si][2]); si += 1
            while sj < len(sl_conf) and sl_conf[sj][0] <= i:
                last_sl = (sl_conf[sj][1], sl_conf[sj][2]); sj += 1
            if i <= pos_until:
                pending = None
                continue
            if pending is not None:
                if day.l[i] <= pending["px"]:
                    entry = min(day.o[i], pending["px"])
                    slp = pending["sl"]
                    if slp < entry:
                        xi, xp, xt = simulate(day, i, entry, slp, ("r", tp_r))
                        pnl = xp - entry
                        trades.append({"day": day.date, "ei": i, "entry": entry, "sl": slp,
                                       "xi": xi, "xp": xp, "xt": xt, "pnl": pnl})
                        pos_until = xi
                        consec_sl = consec_sl + 1 if pnl <= 0 else 0
                    pending = None
                    continue
                if day.c[i] < pending["sl"] or i - pending["placed"] >= expiry or i > ENTRY_MAX + 10:
                    pending = None
            if c4 and consec_sl >= 2:
                continue
            if (pending is None and last_sh is not None and last_sl is not None
                    and ENTRY_MIN <= i + 1 <= ENTRY_MAX):
                # BOS up: close rompe el último swing high, con swing low previo (pierna alcista)
                if day.c[i] > last_sh[1] and last_sl[0] < last_sh[0] < i:
                    ob = None
                    for k in range(i - 1, last_sl[0] - 1, -1):
                        if day.c[k] < day.o[k]:        # última vela roja de la pierna
                            ob = k
                            break
                    if ob is not None and day.c[i] > day.h[ob]:
                        pending = {"px": round(day.h[ob], 2),
                                   "sl": round(day.l[ob] - 0.05, 2), "placed": i}
                        last_sh = None                  # consumido — no re-disparar este SH
    return trades


def main():
    days = build_days()
    print(f"Sesiones: {len(days)} ({days[0].date} -> {days[-1].date})")
    print("Bullish Order Block (SMC estándar) — grid:\n")
    print(f"{'variante':<20}{'N':>4}{'HIT%':>7}{'PnL/sh':>9}{'mean':>8}{'PF':>6}{'mLL':>5}")
    for nn in (1, 2, 3):
        for tp in (1.5, 2.0, 3.0):
            for c4 in (False, True):
                s = stats(run_ob(days, n=nn, tp_r=tp, c4=c4))
                tag = f"OB n{nn} tp{tp}{'+C4' if c4 else ''}"
                if s:
                    pf = f"{s['pf']:.2f}" if s['pf'] != float('inf') else 'inf'
                    print(f"{tag:<20}{s['n']:>4}{s['hit']:>7.1f}{s['pnl']:>+9.2f}"
                          f"{s['mean']:>+8.3f}{pf:>6}{s['mll']:>5}")
                else:
                    print(f"{tag:<20}{'0':>4}")


if __name__ == "__main__":
    main()
