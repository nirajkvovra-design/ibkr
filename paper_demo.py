"""
Manual paper trading demo script.

Usage:
  python paper_demo.py --symbol AAPL --action BUY --quantity 1 --limit-price 175.00
  python paper_demo.py --symbol AAPL --action SELL --quantity 1 --limit-price 176.00
  python paper_demo.py --symbol AAPL --action BUY --quantity 1 --limit-price 175.00 --paired --sell-price 176.00
  python paper_demo.py --symbol AAPL --action BUY --quantity 1 --limit-price 175.00 --paired --profit-target 0.01

This script connects to IB paper trading, submits manual orders, and optionally runs a buy+sell paired demo flow.
"""

import argparse
import sys
import time

import config
from ib_connection import InteractiveBrokersConnection
from utils import get_logger, setup_logging

logger = get_logger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Manual paper trade demo for IBKR bot")
    parser.add_argument("--symbol", required=True, help="Ticker symbol to trade")
    parser.add_argument(
        "--action",
        required=True,
        choices=["BUY", "SELL"],
        help="Order action: BUY or SELL",
    )
    parser.add_argument("--quantity", type=float, required=True, help="Order quantity")
    parser.add_argument(
        "--order-type",
        default="LMT",
        choices=["LMT", "MKT"],
        help="Order type to submit. Default is LMT.",
    )
    parser.add_argument(
        "--limit-price",
        type=float,
        help="Limit price for the order. Required for LMT orders.",
    )
    parser.add_argument(
        "--paired",
        action="store_true",
        help="Run a paired buy+sell demo flow after the initial order fills.",
    )
    parser.add_argument(
        "--sell-price",
        type=float,
        help="Limit price to use for the paired sell order.",
    )
    parser.add_argument(
        "--profit-target",
        type=float,
        help="Profit target fraction for the paired sell order (e.g. 0.02 = 2%% above entry).",
    )
    parser.add_argument(
        "--stop-loss-price",
        type=float,
        help="Absolute stop-loss price to submit after entry (STP trigger).",
    )
    parser.add_argument(
        "--stop-loss-fraction",
        type=float,
        help="Stop-loss as fraction below entry (e.g. 0.02 = 2%% below entry).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=config.ORDER_CONFIRMATION_TIMEOUT,
        help="Seconds to wait for order fill before retry/cancel.",
    )
    parser.add_argument(
        "--retry-count",
        type=int,
        default=config.ORDER_RETRY_LIMIT,
        help="Number of retries for unfilled orders before giving up.",
    )
    parser.add_argument(
        "--fallback-to-market",
        action="store_true",
        help="If a limit order does not fill in time, retry with a market order when allowed.",
    )
    return parser.parse_args()


def validate_args(args):
    if config.USE_LIMIT_ORDERS_ONLY and args.order_type != "LMT":
        logger.error("Order blocked: market orders are disabled by USE_LIMIT_ORDERS_ONLY.")
        return False

    if args.order_type == "LMT" and args.limit_price is None:
        logger.error("Limit price is required for LMT orders.")
        return False

    if args.paired and args.action != "BUY":
        logger.error("Paired flow is only supported for initial BUY orders.")
        return False

    if args.paired and args.sell_price is None and args.profit_target is None:
        logger.error("Paired flow requires either --sell-price or --profit-target.")
        return False

    if args.stop_loss_price is not None and args.stop_loss_fraction is not None:
        logger.error("Specify either --stop-loss-price or --stop-loss-fraction, not both.")
        return False

    if args.profit_target is not None and args.profit_target <= 0:
        logger.error("Profit target must be a positive fraction.")
        return False

    return True


def build_order_metadata():
    return {
        "demo": True,
        "script": "paper_demo",
        "note": "Manual paper trade demo",
    }


def wait_for_fill(connection, order_id, timeout):
    if connection.wait_for_order_filled(order_id, timeout=timeout):
        logger.info(f"Order {order_id} filled.")
        return True

    logger.warning(f"Order {order_id} did not fill in {timeout}s.")
    return False


def submit_order(connection, symbol, action, quantity, order_type, limit_price, timeout, retry_count, fallback_to_market):
    metadata = build_order_metadata()
    return connection.place_order_with_confirmation(
        symbol,
        action,
        quantity,
        order_type=order_type,
        limit_price=limit_price,
        metadata=metadata,
        timeout=timeout,
        retry=retry_count,
        fallback_to_market=fallback_to_market,
    )


def settle_sell_price(entry_price, sell_price, profit_target):
    if sell_price is not None:
        return sell_price
    if entry_price is None:
        return None
    return round(entry_price * (1 + profit_target), 2)


def main():
    setup_logging()
    args = parse_args()
    if not validate_args(args):
        sys.exit(1)

    if not config.PAPER_TRADING:
        logger.warning("PAPER_TRADING is False — this demo script is intended for paper mode.")
        if not config.ENABLE_LIVE_TRADING:
            logger.error("LIVE orders are disarmed. Enable ENABLE_LIVE_TRADING=True only after manual review.")
            sys.exit(1)

    connection = InteractiveBrokersConnection()
    if not connection.connect():
        logger.error("Could not connect to IB. Confirm TWS/IB Gateway paper trading is running.")
        sys.exit(1)

    logger.info("Connected to IB paper trading for demo order.")

    order_id = submit_order(
        connection,
        args.symbol,
        args.action,
        args.quantity,
        args.order_type,
        args.limit_price,
        timeout=args.timeout,
        retry_count=args.retry_count,
        fallback_to_market=args.fallback_to_market,
    )

    if not order_id:
        logger.error("Order could not be submitted or confirmed.")
        connection.disconnect()
        sys.exit(1)

    logger.info(f"Initial order submitted: {args.action} {args.quantity} {args.symbol} (ID {order_id})")

    if args.paired:
        logger.info("Waiting for initial buy fill before submitting paired sell order...")
        if not wait_for_fill(connection, order_id, timeout=args.timeout):
            logger.error("Initial buy order did not fill; aborting paired sell flow.")
            connection.disconnect()
            sys.exit(1)

        entry_price = connection.get_order_status(order_id).get("avg_fill_price")
        if entry_price is None:
            logger.warning("Could not determine fill price from IB; using limit price as entry price.")
            entry_price = args.limit_price

        # Place protective stop-loss if requested (STP order using auxPrice)
        stop_order_id = None
        stop_price = None
        if args.stop_loss_price is not None:
            stop_price = args.stop_loss_price
        elif args.stop_loss_fraction is not None and entry_price is not None:
            stop_price = round(entry_price * (1 - args.stop_loss_fraction), 2)

        if stop_price is not None:
            logger.info(f"Submitting protective stop-loss at ${stop_price:.2f}")
            try:
                stop_order_id = connection.place_order(
                    args.symbol,
                    "SELL",
                    args.quantity,
                    order_type="STP",
                    limit_price=stop_price,
                    metadata={"note": "paired_stop_loss"},
                )
                if stop_order_id:
                    logger.info(f"Stop-loss order {stop_order_id} submitted.")
            except Exception as exc:
                logger.warning(f"Could not submit stop-loss order: {exc}")

        sell_limit_price = settle_sell_price(entry_price, args.sell_price, args.profit_target)
        if sell_limit_price is None:
            logger.error("Could not compute paired sell price; aborting.")
            connection.disconnect()
            sys.exit(1)

        logger.info(f"Submitting paired sell order for {args.symbol} at ${sell_limit_price:.2f}")
        sell_order_id = submit_order(
            connection,
            args.symbol,
            "SELL",
            args.quantity,
            "LMT",
            sell_limit_price,
            timeout=args.timeout,
            retry_count=args.retry_count,
            fallback_to_market=args.fallback_to_market,
        )

        if not sell_order_id:
            logger.error("Paired sell order could not be submitted or confirmed.")
            # If sell couldn't be submitted, leave stop-loss in place for manual review
            connection.disconnect()
            sys.exit(1)

        # Wait for either the paired sell or the protective stop to fill, then cancel the other
        terminal_statuses = {"Filled", "Cancelled", "Inactive", "ApiCancelled"}
        filled_event = None
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            sell_status = connection.get_order_status(sell_order_id).get("status")
            stop_status = connection.get_order_status(stop_order_id).get("status") if stop_order_id else None

            if sell_status == "Filled":
                filled_event = ("sell", sell_order_id)
                logger.info("Paired sell order filled successfully.")
                # cancel protective stop-loss if still pending
                if stop_order_id:
                    st = connection.get_order_status(stop_order_id).get("status")
                    if st not in terminal_statuses:
                        try:
                            connection.cancel_order(stop_order_id)
                            logger.info(f"Cancelled protective stop-loss {stop_order_id} after paired sell.")
                        except Exception:
                            logger.debug("Failed to cancel protective stop-loss; check IB status.")
                break

            if stop_order_id and stop_status == "Filled":
                filled_event = ("stop", stop_order_id)
                logger.info("Protective stop-loss filled; cancelling paired sell order.")
                # cancel paired sell if still pending
                st_sell = connection.get_order_status(sell_order_id).get("status")
                if st_sell not in terminal_statuses:
                    try:
                        connection.cancel_order(sell_order_id)
                        logger.info(f"Cancelled paired sell order {sell_order_id} after stop fill.")
                    except Exception:
                        logger.debug("Failed to cancel paired sell; check IB status.")
                break

            time.sleep(1)

        if not filled_event:
            logger.warning("Neither paired sell nor protective stop filled before timeout.")
            # Attempt fallback to market exit if requested and permitted
            if args.fallback_to_market:
                if config.USE_LIMIT_ORDERS_ONLY:
                    logger.warning("Fallback to market disabled by USE_LIMIT_ORDERS_ONLY config; no automatic market exit performed.")
                else:
                    logger.info("Attempting fallback market exit for paired sell.")
                    # cancel the original limit sell if still pending
                    st_sell = connection.get_order_status(sell_order_id).get("status")
                    terminal_statuses = {"Filled", "Cancelled", "Inactive", "ApiCancelled"}
                    if st_sell not in terminal_statuses:
                        try:
                            connection.cancel_order(sell_order_id)
                            logger.info(f"Cancelled stale paired sell order {sell_order_id} before market fallback.")
                        except Exception:
                            logger.debug("Failed to cancel stale paired sell; proceeding to submit market order.")

                    # cancel protective stop to avoid duplicate exits
                    if stop_order_id:
                        st_stop = connection.get_order_status(stop_order_id).get("status")
                        if st_stop not in terminal_statuses:
                            try:
                                connection.cancel_order(stop_order_id)
                                logger.info(f"Cancelled protective stop-loss {stop_order_id} before market fallback.")
                            except Exception:
                                logger.debug("Failed to cancel protective stop; proceeding to submit market order.")

                    # submit market sell
                    market_order_id = submit_order(
                        connection,
                        args.symbol,
                        "SELL",
                        args.quantity,
                        "MKT",
                        None,
                        timeout=args.timeout,
                        retry_count=args.retry_count,
                        fallback_to_market=False,
                    )
                    if not market_order_id:
                        logger.error("Market fallback exit could not be submitted. Manual intervention required.")
                    else:
                        if wait_for_fill(connection, market_order_id, timeout=args.timeout):
                            logger.info("Market fallback exit filled successfully.")
                        else:
                            logger.warning("Market fallback exit did not fill before timeout. Manual intervention required.")
            else:
                logger.warning("No fallback requested; manual intervention required to exit position.")

    else:
        logger.info("Manual order submitted. Waiting briefly for status updates...")
        time.sleep(5)
        if connection.has_pending_orders():
            logger.info("Order is still pending. Check TWS for status or use the order status logs.")
        else:
            logger.info("No pending orders detected after wait period.")

    connection.disconnect()
    logger.info("Demo complete. Review paper_trading_journal.jsonl and trade_history.csv.")


if __name__ == "__main__":
    main()
