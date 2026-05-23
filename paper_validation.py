"""
Paper-trading validation: test one cycle, run readiness report, track demo progress.

Usage:
  python paper_validation.py --test-cycle     # single dry run (needs TWS paper on 7497)
  python paper_validation.py --report         # journal summary
  python paper_validation.py --readiness      # go-live checklist
"""

import sys
# Configure standard streams to support UTF-8 on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import argparse
import time

import config
from paper_journal import live_readiness_check, record_session_start, summarize
from utils import get_logger, is_market_open, setup_logging

logger = get_logger(__name__)


def test_one_cycle():
    """Connect to paper IB and run one trading-loop pass."""
    from ib_connection import InteractiveBrokersConnection
    from risk_manager import RiskManager
    from stock_screener import StockScreener
    from strategies import MomentumStrategy
    from trading_engine import TradingEngine

    setup_logging()
    record_session_start()

    if not config.PAPER_TRADING:
        logger.warning("PAPER_TRADING is False — use paper mode for this test")

    engine = TradingEngine()
    if not engine.initialize():
        print("FAIL: Could not connect to IB paper (port %s). Start TWS paper trading." % config.IB_PORT)
        return False

    print("OK: Connected — account %s" % config.IB_ACCOUNT)
    snap = engine.ib_connection.get_account_snapshot()
    print("  Net liquidation: $%s" % f"{snap['net_liquidation']:,.2f}")
    print("  Funds for buys:  $%s" % f"{snap['funds_for_new_buys']:,.2f}")
    print("  Market open:     %s" % is_market_open())

    try:
        engine.ib_connection.refresh_account_data()
        time.sleep(0.5)

        if not is_market_open():
            print("NOTE: Market closed — conditions/signals tested; orders only fire during RTH.")
        else:
            engine.running = True
            engine._trading_loop()
            print("OK: Trading loop completed one pass")
    finally:
        engine.stop()

    summary = summarize()
    print("\nJournal: %s" % summary["journal_path"])
    print("  Session days: %s | Orders submitted: %s | Executions: %s" % (
        summary["session_days"],
        summary["orders_submitted"],
        summary["executions"],
    ))
    return True


def print_report():
    summary = summarize()
    ready, report = live_readiness_check()

    print("\n=== Paper Trading Journal ===\n")
    print("File: %s" % summary["journal_path"])
    print("Total events:     %s" % summary["total_events"])
    print("Session days:     %s %s" % (summary["session_days"], summary["session_dates"]))
    print("Orders submitted: %s" % summary["orders_submitted"])
    print("Executions:       %s" % summary["executions"])
    print("Daily snapshots:  %s" % summary["daily_snapshots"])

    if summary["daily_snapshots"]:
        print("\nDaily P&L summary:")
        print("  Total P&L:      $%s" % f"{summary['total_pnl']:,.2f}")
        print("  Average daily:  $%s" % f"{summary['average_daily_pnl']:,.2f}")
        if summary["best_daily_pnl"] is not None:
            print("  Best daily:     $%s" % f"{summary['best_daily_pnl']:,.2f}")
        if summary["worst_daily_pnl"] is not None:
            print("  Worst daily:    $%s" % f"{summary['worst_daily_pnl']:,.2f}")
        if summary["last_snapshot"] and summary["last_snapshot"].get("daily_pnl") is not None:
            print("  Last daily:     $%s" % f"{float(summary['last_snapshot']['daily_pnl']):,.2f}")
        print("\nDaily P&L file: %s" % summary["daily_pnl_path"])
        print("Trade history file: %s" % summary["trade_history_path"])
        print("Closed trades:   %s" % summary["closed_trade_count"])
        print("Realized P&L:    $%s" % f"{summary['realized_pnl']:,.2f}")
        if summary["win_rate"] is not None:
            print("Win rate:        %s%%" % f"{summary['win_rate'] * 100:.1f}")
        print("Average trade:   $%s" % f"{summary['average_trade_pnl']:,.2f}")

    if summary["recent_executions"]:
        print("\nRecent fills:")
        for ex in summary["recent_executions"]:
            print("  %s %s %s @ $%s" % (
                ex.get("ts", "")[:16],
                ex.get("side", ex.get("action", "?")),
                ex.get("symbol"),
                ex.get("price"),
            ))

    print("\n=== Live readiness (%s days, %s fills required) ===\n" % (
        config.PAPER_MIN_SESSION_DAYS,
        config.PAPER_MIN_EXECUTIONS,
    ))
    for check in report["checks"]:
        mark = "PASS" if check["ok"] else "FAIL"
        print("  [%s] %s — %s" % (mark, check["name"], check["detail"]))

    if ready:
        print("\nPaper period looks complete. Review journal, then see PAPER_TO_LIVE.md before live.")
    else:
        print("\nKeep running paper sessions during market hours until all checks pass.")
    return ready


def main():
    parser = argparse.ArgumentParser(description="Paper trading validation for IBKR bot")
    parser.add_argument("--test-cycle", action="store_true", help="Run one paper trading loop")
    parser.add_argument("--report", action="store_true", help="Show journal summary")
    parser.add_argument("--readiness", action="store_true", help="Go-live checklist only")
    args = parser.parse_args()

    if args.test_cycle:
        ok = test_one_cycle()
        sys.exit(0 if ok else 1)
    if args.readiness or args.report or not any([args.test_cycle]):
        ready = print_report()
        sys.exit(0 if ready else 1)


if __name__ == "__main__":
    main()
