"""
Market research: analyze open/close candidates even when orders are not placed.
"""

import json
from datetime import datetime
from pathlib import Path

import pytz

import config
from utils import get_logger, is_market_open

logger = get_logger(__name__)

_TZ = pytz.timezone("America/New_York")
_RESEARCH_LOG = Path(getattr(config, "RESEARCH_LOG_FILE", "trading_research.jsonl"))


class TradeResearch:
    def __init__(self, data_fetcher):
        self.data_fetcher = data_fetcher

    def build_report(self, strategy, stock_screener, ib_connection, risk_manager):
        now = datetime.now(_TZ)
        regime = self.data_fetcher.get_market_regime()
        blockers = strategy.get_trading_blockers() if hasattr(strategy, "get_trading_blockers") else []
        can_execute = len(blockers) == 0

        ib_connection.refresh_account_data()
        positions = ib_connection.get_positions()
        account = ib_connection.get_account_snapshot()

        watchlist = stock_screener.get_watchlist(config.WATCHLIST_METHOD)
        signals = strategy.generate_signals(watchlist) if watchlist else {}

        buys = [s for s, a in signals.items() if a == "BUY"]
        sells = [s for s, a in signals.items() if a == "SELL"]
        holds = [s for s, a in signals.items() if a == "HOLD"]

        position_analysis = []
        for symbol, pos in positions.items():
            qty = pos.get("quantity", 0)
            avg = pos.get("avg_cost", 0)
            price = self.data_fetcher.get_current_price(symbol)
            exit_rec = "HOLD"
            if price and avg:
                if risk_manager.check_stop_loss(symbol, price):
                    exit_rec = "CLOSE (stop-loss)"
                elif risk_manager.check_take_profit(symbol, price):
                    exit_rec = "CLOSE (take-profit)"
                elif symbol in sells:
                    exit_rec = "CLOSE (signal)"
            pnl_pct = ((price - avg) / avg * 100) if price and avg else None
            position_analysis.append({
                "symbol": symbol,
                "quantity": qty,
                "avg_cost": avg,
                "current_price": price,
                "pnl_percent": round(pnl_pct, 2) if pnl_pct is not None else None,
                "exit_recommendation": exit_rec,
            })

        return {
            "timestamp": now.isoformat(timespec="seconds"),
            "market_open": is_market_open(),
            "market_regime": regime,
            "can_execute_trades": can_execute,
            "blockers": blockers,
            "watchlist": watchlist,
            "signals": signals,
            "recommended_opens": buys,
            "recommended_closes": sells,
            "on_hold": holds,
            "open_positions": position_analysis,
            "account": {
                "net_liquidation": account.get("net_liquidation"),
                "funds_for_buys": account.get("funds_for_new_buys"),
            },
        }

    def log_report(self, report):
        if not config.ENABLE_MARKET_RESEARCH:
            return

        _RESEARCH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _RESEARCH_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(report, default=str) + "\n")

        logger.info("=" * 60)
        logger.info("Market research cycle @ %s", report["timestamp"][-8:])
        logger.info("Market Regime: %s", report.get("market_regime", "UNKNOWN"))
        logger.info("=" * 60)

        if report["blockers"]:
            logger.info("Execution blocked: %s", ", ".join(report["blockers"]))
        else:
            logger.info("Execution allowed — risk and market checks passed")

        if report["recommended_opens"]:
            logger.info("Research — candidates to OPEN: %s", ", ".join(report["recommended_opens"]))
        else:
            logger.info("Research — no OPEN candidates this cycle")

        if report["recommended_closes"]:
            logger.info("Research — candidates to CLOSE (signal): %s", ", ".join(report["recommended_closes"]))

        if report["open_positions"]:
            for pos in report["open_positions"]:
                pnl = pos.get("pnl_percent")
                pnl_s = f"{pnl:+.2f}%" if pnl is not None else "n/a"
                logger.info(
                    "  Position %s: qty=%s P&L=%s → %s",
                    pos["symbol"],
                    pos["quantity"],
                    pnl_s,
                    pos["exit_recommendation"],
                )
        else:
            logger.info("Research — no open positions")

        if report["on_hold"] and not report["recommended_opens"]:
            sample = report["on_hold"][:8]
            extra = len(report["on_hold"]) - len(sample)
            suffix = f" (+{extra} more)" if extra > 0 else ""
            logger.info("Research — watching (HOLD): %s%s", ", ".join(sample), suffix)

        logger.info("Research log appended: %s", _RESEARCH_LOG)
