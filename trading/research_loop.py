"""
trading/research_loop.py — Nightly strategy optimization loop.

Runs after market close via Windows Task Scheduler (9:15 PM UTC / 5:15 PM ET, Mon-Fri).
Backtests Level A candidates and promotes the best one if it beats the current champion.

Promotion criteria (all must hold):
  - candidate.trades  >= 100
  - candidate.avg_pnl >= champion.avg_pnl + $0.15
  - candidate.win_rate >= champion.win_rate - 5%

Superseded strategies are archived in trading/strategy_archive/ before replacement.
"""
import logging, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from trading.bar_cache         import get_bars_cached
from trading.backtester        import run_backtest
from trading.strategy_explorer import generate_random_level_a, is_better_than_champion
from trading.strategy_schema   import load_champion, save_champion, archive_strategy, sync_champion_to_supabase

CANDIDATES_PER_RUN = 20
BACKTEST_START     = "2025-01-01"
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def _setup_log() -> logging.Logger:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s UTC  %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / f"research_{date}.log", encoding="utf-8"),
        ],
        force=True,
    )
    return logging.getLogger("research")


def run_nightly():
    log = _setup_log()
    log.info("=== Research loop started ===")

    champion = load_champion()
    log.info(f"Champion: {champion['id']}")
    sync_champion_to_supabase(champion)  # keep dashboard in sync

    symbol = champion["symbol"]
    signal = champion["signal_asset"]

    log.info(f"Updating bar cache: {symbol}, {signal} from {BACKTEST_START} ...")
    try:
        get_bars_cached(symbol, "5Min", BACKTEST_START)
        get_bars_cached(signal, "5Min", BACKTEST_START)
    except Exception as e:
        log.error(f"Bar cache update failed: {e}")
        return

    log.info("Backtesting champion ...")
    champ_metrics = run_backtest(champion, BACKTEST_START)
    log.info(
        f"  Champion: n={champ_metrics['trades']} | "
        f"win={champ_metrics['win_rate']:.1%} | "
        f"avg_pnl=${champ_metrics['avg_pnl']:.2f}"
    )

    log.info(f"Evaluating {CANDIDATES_PER_RUN} Level A candidates ...")
    best_candidate = None
    best_metrics   = None

    for i in range(CANDIDATES_PER_RUN):
        try:
            candidate = generate_random_level_a(champion)
            metrics   = run_backtest(candidate, BACKTEST_START)
            promoted  = is_better_than_champion(metrics, champ_metrics)
            log.info(
                f"  [{i+1:2d}/{CANDIDATES_PER_RUN}] "
                f"orb={candidate['entry']['orb_threshold_pct']:.3f} "
                f"bars={candidate['entry']['orb_bars']} "
                f"gap={candidate['entry']['qqq_gap_min_pct']:+.3f} "
                f"sl={candidate['exit']['sl_value']:.1f} | "
                f"n={metrics['trades']:3d} "
                f"wr={metrics['win_rate']:.1%} "
                f"avg=${metrics['avg_pnl']:.2f}"
                + (" [CANDIDATE]" if promoted else "")
            )
            if promoted:
                if best_metrics is None or metrics["avg_pnl"] > best_metrics["avg_pnl"]:
                    best_candidate = candidate
                    best_metrics   = metrics
        except Exception as e:
            log.warning(f"  [{i+1}] candidate error: {e}")

    if best_candidate is not None:
        log.info(
            f"NEW CHAMPION: {best_candidate['id']} | "
            f"n={best_metrics['trades']} "
            f"wr={best_metrics['win_rate']:.1%} "
            f"avg_pnl=${best_metrics['avg_pnl']:.2f}"
        )
        archive_strategy(champion, reason="superseded_by_level_a")
        best_candidate["performance"] = {
            "trades":     best_metrics["trades"],
            "win_rate":   best_metrics["win_rate"],
            "avg_pnl":    best_metrics["avg_pnl"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        save_champion(best_candidate)
        sync_champion_to_supabase(best_candidate)
        log.info("Champion saved to active_strategy.json and synced to Supabase")
    else:
        log.info("No improvement found - champion unchanged.")

    log.info("=== Research loop complete ===")


if __name__ == "__main__":
    run_nightly()
