import atexit, json, sys, os
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from trading.regime_agent import MarketRegimeAgent
from trading.market_learner import MarketLearner
from trading.allocation import AllocationEngine
from trading.exhaustion_filter import ExhaustionGapFilter
from trading.agent_reporter import report

atexit.register(report, 'Backtesting Engine', 'idle')
report('Backtesting Engine', 'running')

TSLA_FILES = [
    r'C:\Users\inaki\.claude\projects\C--Users-inaki-Claude\4b6a44fd-17b7-46ba-af07-660060a6e957\tool-results\mcp-alpaca-get_stock_bars-1778465292120.txt',
    r'C:\Users\inaki\.claude\projects\C--Users-inaki-Claude\4b6a44fd-17b7-46ba-af07-660060a6e957\tool-results\mcp-alpaca-get_stock_bars-1778465173714.txt',
    r'C:\Users\inaki\.claude\projects\C--Users-inaki-Claude\4b6a44fd-17b7-46ba-af07-660060a6e957\tool-results\mcp-alpaca-get_stock_bars-1778465376423.txt',
    r'C:\Users\inaki\.claude\projects\C--Users-inaki-Claude\4b6a44fd-17b7-46ba-af07-660060a6e957\tool-results\mcp-alpaca-get_stock_bars-1778464396264.txt',
]
QQQ_FILES = [
    r'C:\Users\inaki\.claude\projects\C--Users-inaki-Claude\4b6a44fd-17b7-46ba-af07-660060a6e957\tool-results\mcp-alpaca-get_stock_bars-1778465292491.txt',
    r'C:\Users\inaki\.claude\projects\C--Users-inaki-Claude\4b6a44fd-17b7-46ba-af07-660060a6e957\tool-results\mcp-alpaca-get_stock_bars-1778465173593.txt',
    r'C:\Users\inaki\.claude\projects\C--Users-inaki-Claude\4b6a44fd-17b7-46ba-af07-660060a6e957\tool-results\mcp-alpaca-get_stock_bars-1778465377137.txt',
    r'C:\Users\inaki\.claude\projects\C--Users-inaki-Claude\4b6a44fd-17b7-46ba-af07-660060a6e957\tool-results\mcp-alpaca-get_stock_bars-1778464399986.txt',
]

def load_merge(files, sym):
    seen = {}
    for f in files:
        with open(f) as fh:
            d = json.load(fh)
        for b in d['bars'].get(sym, []):
            seen[b['t']] = b
    return sorted(seen.values(), key=lambda x: x['t'])

def group(bars):
    days = defaultdict(list)
    for b in bars:
        t = b['t']; day = t[:10]; time = t[11:16]
        if '13:30' <= time <= '20:01':
            days[day].append(b)
    return {d: sorted(v, key=lambda x: x['t']) for d, v in days.items()}

tsla_days = group(load_merge(TSLA_FILES, 'TSLA'))
qqq_days  = group(load_merge(QQQ_FILES,  'QQQ'))
all_days  = sorted(set(tsla_days.keys()) & set(qqq_days.keys()))
print(f"Dataset: {len(all_days)} dias ({all_days[0]} a {all_days[-1]})\n")

def calc_vwap_series(day_bars):
    cum_pv = 0.0; cum_v = 0.0; result = []
    for b in day_bars:
        tp = (b['h'] + b['l'] + b['c']) / 3
        cum_pv += tp * b['v']; cum_v += b['v']
        vwap = cum_pv / cum_v if cum_v > 0 else b['c']
        result.append((b, vwap))
    return result

def run_v2(orb_thr, qqq_gap_min, stop_size, max_wait_bars, touch_tol, detail=False, return_trades=False):
    """
    TOB-V2: After bullish ORB, wait for first VWAP pullback, enter at VWAP.
    orb_thr      : min ORB bullish %
    qqq_gap_min  : min QQQ gap% at open
    stop_size    : fixed stop below VWAP entry (dollars)
    max_wait_bars: max 5-min bars after ORB to wait for VWAP touch
    touch_tol    : bar low can be up to this much ABOVE vwap and still count as touch
    """
    traded = []; wins = []; losses = []; times = []
    qqq_prev = None

    for day in all_days:
        tbars = tsla_days.get(day, [])
        qbars = qqq_days.get(day, [])
        if len(tbars) < 10 or len(qbars) < 3:
            if qbars: qqq_prev = qbars[-1]['c']
            continue

        qqq_open = qbars[0]['o']
        qqq_gap  = ((qqq_open - qqq_prev) / qqq_prev * 100) if qqq_prev else 0.0
        qqq_ok   = qqq_prev is None or qqq_gap >= qqq_gap_min

        orb_b = [b for b in tbars if b['t'][11:16] <= '13:44'][:3]
        if len(orb_b) < 3:
            qqq_prev = qbars[-1]['c']; continue

        tsla_open = orb_b[0]['o']
        orb_h = max(b['h'] for b in orb_b)
        orb_l = min(b['l'] for b in orb_b)
        orb_c = orb_b[-1]['c']
        orb_p = (orb_c - tsla_open) / tsla_open * 100

        signal = qqq_ok and orb_p >= orb_thr

        if signal:
            vwap_series = calc_vwap_series(tbars)
            vwap_map = {b['t']: vwap for b, vwap in vwap_series}

            post_orb = [(b, vwap_map[b['t']]) for b in tbars if b['t'][11:16] >= '13:45']
            post_orb_limited = post_orb[:max_wait_bars]

            # Find first VWAP touch: bar's low <= vwap + touch_tol
            entry_bar = None; entry_price = None; entry_vwap = None
            for b, vwap in post_orb_limited:
                if b['l'] <= vwap + touch_tol:
                    entry_bar = b; entry_vwap = vwap
                    entry_price = round(vwap, 2)
                    break

            if entry_bar is None:
                if detail:
                    all_post_vwaps = [(b['t'][11:16], b['l'], vwap_map[b['t']]) for b in tbars if b['t'][11:16] >= '13:45']
                    min_dist = min(abs(l - v) for _, l, v in all_post_vwaps[:max_wait_bars]) if all_post_vwaps else 999
                    print(f"  {day}: NO_TOUCH  ORB={orb_p:+.2f}%  QQQ={qqq_gap:+.2f}%  min_dist_to_vwap=${min_dist:.2f}")
                qqq_prev = qbars[-1]['c']
                continue

            target = orb_h
            stop   = entry_price - stop_size
            reward = target - entry_price
            risk   = stop_size
            rr     = reward / risk if risk > 0 else 0

            entry_idx = next(i for i, (b, _) in enumerate(post_orb) if b['t'] == entry_bar['t'])
            post_entry = post_orb[entry_idx:]

            outcome = 'TIME'; pnl = 0.0; exit_time = '-'
            for b, _ in post_entry:
                if b['h'] >= target: outcome = 'WIN';  pnl = target - entry_price; exit_time = b['t'][11:16]; break
                if b['l'] <= stop:   outcome = 'LOSS'; pnl = stop - entry_price;   exit_time = b['t'][11:16]; break
                if b['t'][11:16] >= '19:50': outcome = 'TIME'; pnl = b['c'] - entry_price; exit_time = b['t'][11:16]; break

            r = {'day': day, 'outcome': outcome, 'pnl': pnl, 'entry': entry_price,
                 'vwap': entry_vwap, 'target': target, 'stop': stop,
                 'reward': reward, 'risk': risk, 'rr': rr, 'orb_p': orb_p, 'qqq_gap': qqq_gap,
                 'entry_time': entry_bar['t'][11:16]}
            traded.append(r)
            if outcome == 'WIN':    wins.append(r)
            elif outcome == 'LOSS': losses.append(r)
            else:                   times.append(r)

            if detail:
                flag = 'GOOD' if rr >= 1.0 else ('OK' if rr >= 0.5 else ('LOW' if rr >= 0.25 else 'BAD'))
                print(f"  {day}: {outcome:4s} [{flag} R:R={rr:.2f}] "
                      f"entry={entry_price:.2f}@{r['entry_time']}(vwap={entry_vwap:.2f}) "
                      f"tgt={target:.2f} stp={stop:.2f} "
                      f"rew=${reward:.2f} risk=${risk:.2f} "
                      f"PnL=${pnl:+.2f} exit@{exit_time} ORB={orb_p:+.2f}% QQQ={qqq_gap:+.2f}%")

        qqq_prev = qbars[-1]['c']

    if not traded:
        return None
    hr   = len(wins) / len(traded) * 100
    pnl  = sum(r['pnl'] for r in traded)
    avgw = sum(r['pnl'] for r in wins)   / len(wins)   if wins   else 0
    avgl = sum(r['pnl'] for r in losses) / len(losses) if losses else 0
    avgt = sum(r['pnl'] for r in times)  / len(times)  if times  else 0
    avg_rr = sum(r['rr'] for r in traded) / len(traded)
    result = {'n': len(traded), 'w': len(wins), 'l': len(losses), 't': len(times),
              'hr': hr, 'pnl': pnl, 'avgw': avgw, 'avgl': avgl, 'avgt': avgt, 'avg_rr': avg_rr}
    if return_trades:
        result['trades'] = traded
    return result

# ---- Parameter Sweep ----
print("=== TOB-V2: VWAP PULLBACK — SWEEP DE PARAMETROS ===\n")
print(f"{'Config':<58} {'N':>3} {'W':>3} {'L':>3} {'T':>3} {'HR%':>6} {'PnL/shr':>9} {'AvgRR':>7} {'AvgW':>7} {'AvgL':>7}")
print('-' * 115)

best_results = []
for orb_t in [0.5, 0.75, 1.0]:
    for qqq_g in [0.0, 0.3]:
        for stop_s in [1.5, 2.0, 3.0, 5.0]:
            for wait in [6, 12, 18, 24]:      # 30, 60, 90, 120 min
                for tol in [0.0, 0.5, 1.0]:
                    r = run_v2(orb_t, qqq_g, stop_s, wait, tol)
                    if r and r['n'] >= 2:
                        lbl = f"ORB>{orb_t:.2f}% QQQ>={qqq_g:.1f}% stp=${stop_s:.1f} wait={wait*5}m tol=${tol:.1f}"
                        r['label'] = lbl
                        best_results.append(r)

best_results.sort(key=lambda x: (-x['hr'], -x['pnl']))

for r in best_results[:25]:
    print(f"{r['label']:<58} {r['n']:>3} {r['w']:>3} {r['l']:>3} {r['t']:>3} "
          f"{r['hr']:>6.1f} ${r['pnl']:>8.2f} {r['avg_rr']:>7.2f} ${r['avgw']:>6.2f} ${r['avgl']:>6.2f}")

# ---- Best config detail ----
print("\n=== DETALLE DIA A DIA — mejor configuracion ===")
# Find the top config by HR then PnL
top = best_results[0]
print(f"Config: {top['label']}")
print()

# Parse params from label
import re
m = re.search(r'ORB>([\d.]+)%.*QQQ>=([\d.]+)%.*stp=\$([\d.]+).*wait=(\d+)m.*tol=\$([\d.]+)', top['label'])
if m:
    run_v2(float(m.group(1)), float(m.group(2)), float(m.group(3)),
           int(m.group(4))//5, float(m.group(5)), detail=True)

# ---- Key stats for top configs ----
print("\n=== TOP 5 CONFIGURACIONES ===")
for i, r in enumerate(best_results[:5], 1):
    print(f"\n#{i}: {r['label']}")
    print(f"    Trades={r['n']}  W={r['w']}  L={r['l']}  T={r['t']}")
    print(f"    Hit Rate={r['hr']:.1f}%  Total PnL/shr=${r['pnl']:.2f}")
    print(f"    Avg R:R={r['avg_rr']:.2f}  AvgWin=${r['avgw']:.2f}  AvgLoss=${r['avgl']:.2f}")
    if r['n'] > 0:
        exp = r['hr']/100 * r['avgw'] + (1 - r['hr']/100) * r['avgl']
        print(f"    Expected value/trade=${exp:.2f}")

# ---- Regime + Exhaustion Analysis ----
_regime_agent  = MarketRegimeAgent()
_exhaust       = ExhaustionGapFilter()
_learner       = MarketLearner()
_alloc         = AllocationEngine()

if m:
    _best_with_trades = run_v2(
        float(m.group(1)), float(m.group(2)), float(m.group(3)),
        int(m.group(4))//5, float(m.group(5)), return_trades=True
    )
    _traded_dates = {r['day'] for r in (_best_with_trades.get('trades') or [])}
else:
    _traded_dates = set()
    _best_with_trades = None

# --- Regime table (QQQ-based) ---
print("\n=== REGIMEN MULTI-RESOLUCION — QQQ (VOO: pendiente datos) ===")
print(f"{'Date':<12} {'5m M_t':>8} {'15m M_t':>9} {'1h M_t':>8} {'WtdMt':>8} {'Regime':<16} {'Quality':>8}")
print('-' * 80)

_day_regimes    = {}
_day_exhaustion = {}
_qqq_prev_close = None

for day in all_days:
    qbars = qqq_days.get(day, [])
    if not qbars:
        continue

    # Regime: QQQ-based (add voo_bars=... when VOO data available)
    if len(qbars) >= 5:
        reg = _regime_agent.classify(qbars)
        _day_regimes[day] = reg
        traded_marker = " <-- TRADED" if day in _traded_dates else ""
        print(f"{day:<12} {reg['signals']['5m']:>8.3f} {reg['signals']['15m']:>9.3f} "
              f"{reg['signals']['1h']:>8.3f} {reg['weighted_mt']:>8.3f} "
              f"{reg['regime']:<16} {reg['quality']:>8.3f}{traded_marker}")

    # Exhaustion: uses only first 3 bars + prev_close (no lookahead)
    if _qqq_prev_close:
        ex = _exhaust.detect(qbars, _qqq_prev_close)  # add voo_bars= when available
        _day_exhaustion[day] = ex

    _qqq_prev_close = qbars[-1]['c']

# --- Exhaustion gap table (traded days only) ---
print("\n=== FILTRO EXHAUSTION GAP — QQQ ORB (primeros 15 min) ===")
print(f"{'Date':<12} {'Gap%':>7} {'FillR':>7} {'Candle':>8} {'OrbMt':>8} {'Score':>7} {'Exhaust?':>9}  Outcome")
print('-' * 75)

for day in all_days:
    if day not in _traded_dates:
        continue
    ex = _day_exhaustion.get(day)
    if ex is None:
        print(f"{day:<12}  (no prev_close available)")
        continue
    q  = ex['QQQ']
    flag = '  YES ←' if ex['is_exhaustion'] else '  no'
    tr = next((t for t in (_best_with_trades.get('trades') or []) if t['day'] == day), None)
    outcome = tr['outcome'] if tr else '-'
    print(f"{day:<12} {q['gap_pct']:>+7.3f}% {q['fill_ratio']:>7.3f} {q['candle']:>8.3f} "
          f"{q['mt_orb']:>8.3f} {ex['score']:>7.3f}{flag}  {outcome}")

# --- Interpretation note ---
print()
print("  fill_ratio > 0 = gap se llena (reversal) | < 0 = gap se extiende (momentum)")
print("  candle > 0 = primera barra bearish después del gap (señal de agotamiento)")
print("  Score >= 0.40 → is_exhaustion = YES (mercado agotado, evitar entradas momentum)")

# --- Impact: what if we had filtered exhaustion days? ---
if _best_with_trades and _best_with_trades.get('trades'):
    _trades = _best_with_trades['trades']
    filtered_in  = [t for t in _trades if not _day_exhaustion.get(t['day'], {}).get('is_exhaustion', False)]
    filtered_out = [t for t in _trades if     _day_exhaustion.get(t['day'], {}).get('is_exhaustion', False)]
    fi_wins = sum(1 for t in filtered_in  if t['outcome'] == 'WIN')
    fo_wins = sum(1 for t in filtered_out if t['outcome'] == 'WIN')
    print(f"\n  Sin filtro:     {len(_trades)} trades, {sum(1 for t in _trades if t['outcome']=='WIN')} wins")
    if filtered_in:
        print(f"  Filtro activo:  {len(filtered_in)} trades, {fi_wins} wins  "
              f"→ HR {fi_wins/len(filtered_in)*100:.1f}%")
    if filtered_out:
        print(f"  Descartados:    {len(filtered_out)} trades ({fo_wins} wins, {len(filtered_out)-fo_wins} losses)")

# --- Allocation score per traded day ---
print("\n=== ALLOCATION SCORE (A) POR TRADE ===")
print(f"{'Date':<12} {'Regime':<16} {'Exh?':>5} {'Quality':>8} {'A (size)':>9} {'Outcome':>8}")
print('-' * 65)

_qqq_hist = [b for d in all_days for b in qqq_days.get(d, [])]

if _best_with_trades and _best_with_trades.get('trades'):
    for tr in _best_with_trades['trades']:
        reg_info = _day_regimes.get(tr['day'])
        ex_info  = _day_exhaustion.get(tr['day'])
        if not reg_info:
            continue
        qbars_day = qqq_days.get(tr['day'], [])
        base_quality = _learner.get_entry_quality_score(reg_info)
        # Apply exhaustion penalty: if exhaustion detected, zero quality → A = 0
        ex_score   = ex_info['score'] if ex_info else 0.0
        is_exhaust = ex_info['is_exhaustion'] if ex_info else False
        adj_quality = 0.0 if is_exhaust else base_quality * (1.0 - 0.5 * ex_score)
        alloc = _alloc.compute(
            tsla_bars=qbars_day,    # QQQ vol as primary (no TSLA)
            qqq_bars=[],            # VOO pending: empty → correlation defaults to 0.5
            entry_time_utc=tr['entry_time'],
            quality=adj_quality,
            tsla_history=_qqq_hist,
        )
        ex_marker = ' YES' if is_exhaust else '  no'
        print(f"{tr['day']:<12} {reg_info['regime']:<16} {ex_marker:>5} "
              f"{adj_quality:>8.3f} {alloc['A']:>9.3f} {tr['outcome']:>8}")

print("\n[Nota] Regime y Exhaustion basados en QQQ — VOO se integrará cuando haya datos.")
print("[Nota] Exhaustion usa solo los primeros 15min del dia (sin lookahead).")
print("[Nota] A=0 si Exhaust=YES (hard gate) o si régimen incompatible (Y<0.05).")
