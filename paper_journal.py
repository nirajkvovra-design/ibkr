"""
Paper-trading journal: records demo trades and session stats for review before going live.
"""

import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import config

JOURNAL_PATH = Path(getattr(config, "PAPER_JOURNAL_FILE", "paper_trading_journal.jsonl"))
DAILY_PNL_PATH = Path(getattr(config, "PAPER_DAILY_PNL_FILE", "daily_pnl.csv"))
TRADE_HISTORY_PATH = Path(getattr(config, "PAPER_TRADE_HISTORY_FILE", "trade_history.csv"))


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def record_event(event_type, **fields):
    """Append one JSON line to the paper trading journal."""
    entry = {"ts": _now_iso(), "event": event_type, **fields}
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, default=str) + "\n")
    return entry


def record_order_submitted(symbol, action, quantity, limit_price, order_id):
    return record_event(
        "order_submitted",
        symbol=symbol,
        action=action,
        quantity=quantity,
        limit_price=limit_price,
        order_id=order_id,
        account=config.IB_ACCOUNT,
    )


def record_order_status(order_id, status, filled, avg_fill_price, symbol=None):
    return record_event(
        "order_status",
        order_id=order_id,
        status=status,
        filled=filled,
        avg_fill_price=avg_fill_price,
        symbol=symbol,
    )


def _write_trade_history_csv(trade):
    TRADE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "date",
        "timestamp",
        "symbol",
        "side",
        "quantity",
        "price",
        "entry_price",
        "pnl",
        "order_id",
        "note",
    ]
    write_header = not TRADE_HISTORY_PATH.exists()

    with TRADE_HISTORY_PATH.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "date": datetime.now().date().isoformat(),
            "timestamp": _now_iso(),
            "symbol": trade.get("symbol"),
            "side": trade.get("side"),
            "quantity": trade.get("quantity"),
            "price": trade.get("price"),
            "entry_price": trade.get("entry_price"),
            "pnl": trade.get("pnl"),
            "order_id": trade.get("order_id"),
            "note": trade.get("note"),
        })


def record_execution(symbol, quantity, price, side=None, order_id=None, entry_price=None, note=None):
    trade = {
        "symbol": symbol,
        "quantity": quantity,
        "price": price,
        "side": side,
        "order_id": order_id,
        "entry_price": entry_price,
        "note": note,
    }
    if side == "SELL" and entry_price is not None:
        try:
            trade["pnl"] = float(quantity) * (float(price) - float(entry_price))
        except (TypeError, ValueError):
            trade["pnl"] = None
    else:
        trade["pnl"] = None

    entry = record_event(
        "execution",
        symbol=symbol,
        quantity=quantity,
        price=price,
        side=side,
        order_id=order_id,
        account=config.IB_ACCOUNT,
        entry_price=entry_price,
        pnl=trade["pnl"],
        note=note,
    )
    try:
        _write_trade_history_csv(trade)
    except Exception:
        pass
    return entry


def record_session_start(mode="PAPER"):
    return record_event("session_start", mode=mode, account=config.IB_ACCOUNT)


def _write_daily_pnl_csv(snapshot):
    DAILY_PNL_PATH.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "date",
        "net_liquidation",
        "total_cash",
        "funds_for_new_buys",
        "open_positions",
        "position_symbols",
        "daily_trades",
        "daily_pnl",
    ]
    write_header = not DAILY_PNL_PATH.exists()

    with DAILY_PNL_PATH.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "date": datetime.now().date().isoformat(),
            "net_liquidation": snapshot.get("net_liquidation"),
            "total_cash": snapshot.get("total_cash"),
            "funds_for_new_buys": snapshot.get("funds_for_new_buys"),
            "open_positions": snapshot.get("open_positions"),
            "position_symbols": ";".join(snapshot.get("position_symbols", [])),
            "daily_trades": snapshot.get("daily_trades"),
            "daily_pnl": snapshot.get("daily_pnl"),
        })


def record_daily_snapshot(account_snapshot, positions, daily_trades, daily_pnl):
    snapshot = record_event(
        "daily_snapshot",
        net_liquidation=account_snapshot.get("net_liquidation"),
        total_cash=account_snapshot.get("total_cash"),
        funds_for_buys=account_snapshot.get("funds_for_new_buys"),
        open_positions=len(positions),
        position_symbols=list(positions.keys()),
        daily_trades=daily_trades,
        daily_pnl=daily_pnl,
    )
    try:
        _write_daily_pnl_csv(snapshot)
    except Exception:
        pass
    return snapshot


def load_trade_history():
    if not TRADE_HISTORY_PATH.exists():
        return []
    trades = []
    with TRADE_HISTORY_PATH.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                row["quantity"] = float(row.get("quantity", 0))
            except (TypeError, ValueError):
                row["quantity"] = 0.0
            try:
                row["price"] = float(row.get("price", 0))
            except (TypeError, ValueError):
                row["price"] = 0.0
            try:
                row["entry_price"] = float(row.get("entry_price")) if row.get("entry_price") not in (None, "") else None
            except (TypeError, ValueError):
                row["entry_price"] = None
            try:
                row["pnl"] = float(row.get("pnl")) if row.get("pnl") not in (None, "") else None
            except (TypeError, ValueError):
                row["pnl"] = None
            trades.append(row)
    return trades


def load_events(since_days=None):
    if not JOURNAL_PATH.exists():
        return []
    cutoff = None
    if since_days is not None:
        cutoff = datetime.now() - timedelta(days=since_days)

    events = []
    with JOURNAL_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if cutoff:
                try:
                    ts = datetime.fromisoformat(entry["ts"])
                except (KeyError, ValueError):
                    continue
                if ts < cutoff:
                    continue
            events.append(entry)
    return events


def summarize(days=None):
    """Build stats used for learning review and live-readiness checks."""
    events = load_events(since_days=days)
    session_dates = set()
    executions = []
    submissions = []
    snapshots = []

    for entry in events:
        event = entry.get("event")
        ts = entry.get("ts", "")[:10]
        if event == "session_start" and ts:
            session_dates.add(ts)
        elif event == "execution":
            executions.append(entry)
        elif event == "order_submitted":
            submissions.append(entry)
        elif event == "daily_snapshot":
            snapshots.append(entry)

    pnl_values = []
    for snap in snapshots:
        try:
            if snap.get("daily_pnl") is not None:
                pnl_values.append(float(snap["daily_pnl"]))
        except (TypeError, ValueError):
            continue

    total_pnl = sum(pnl_values)
    average_daily_pnl = total_pnl / len(pnl_values) if pnl_values else 0.0
    best_daily_pnl = max(pnl_values) if pnl_values else None
    worst_daily_pnl = min(pnl_values) if pnl_values else None

    trade_history = load_trade_history()
    closed_trades = [t for t in trade_history if t.get("side") == "SELL" and t.get("pnl") is not None]
    total_realized = sum(t["pnl"] for t in closed_trades)
    winners = [t for t in closed_trades if t["pnl"] > 0]
    losers = [t for t in closed_trades if t["pnl"] < 0]
    avg_trade_pnl = total_realized / len(closed_trades) if closed_trades else 0.0
    win_rate = len(winners) / len(closed_trades) if closed_trades else None

    return {
        "journal_path": str(JOURNAL_PATH),
        "daily_pnl_path": str(DAILY_PNL_PATH),
        "trade_history_path": str(TRADE_HISTORY_PATH),
        "trade_history_count": len(trade_history),
        "closed_trade_count": len(closed_trades),
        "realized_pnl": total_realized,
        "average_trade_pnl": avg_trade_pnl,
        "win_rate": win_rate,
        "total_events": len(events),
        "session_days": len(session_dates),
        "session_dates": sorted(session_dates),
        "orders_submitted": len(submissions),
        "executions": len(executions),
        "daily_snapshots": len(snapshots),
        "last_snapshot": snapshots[-1] if snapshots else None,
        "total_pnl": total_pnl,
        "average_daily_pnl": average_daily_pnl,
        "best_daily_pnl": best_daily_pnl,
        "worst_daily_pnl": worst_daily_pnl,
        "recent_executions": executions[-10:],
    }


def live_readiness_check(
    min_session_days=None,
    min_executions=None,
    max_daily_loss=None,
):
    """
    Returns (ready: bool, report: dict) — all checks must pass before live trading.
    """
    min_session_days = min_session_days or config.PAPER_MIN_SESSION_DAYS
    min_executions = min_executions or config.PAPER_MIN_EXECUTIONS
    max_daily_loss = max_daily_loss if max_daily_loss is not None else config.MAX_DAILY_LOSS

    summary = summarize()
    checks = []

    checks.append(
        (
            "paper_mode_recommended",
            config.PAPER_TRADING,
            "Keep PAPER_TRADING=True until this checklist passes, then switch to live port with ENABLE_LIVE_TRADING.",
        )
    )
    checks.append(
        (
            f"at_least_{min_session_days}_session_days",
            summary["session_days"] >= min_session_days,
            f"Run the engine on {min_session_days}+ separate market days (have {summary['session_days']}).",
        )
    )
    checks.append(
        (
            f"at_least_{min_executions}_executions",
            summary["executions"] >= min_executions,
            f"Complete {min_executions}+ paper fills to validate order flow (have {summary['executions']}).",
        )
    )

    worst_daily_pnl = 0.0
    for snap in load_events():
        if snap.get("event") == "daily_snapshot" and snap.get("daily_pnl") is not None:
            worst_daily_pnl = min(worst_daily_pnl, float(snap["daily_pnl"]))
    checks.append(
        (
            "daily_loss_within_limit",
            worst_daily_pnl >= -max_daily_loss,
            f"Worst logged daily P&L ${worst_daily_pnl:.2f} vs limit -${max_daily_loss:.2f}.",
        )
    )

    passed = [name for name, ok, _ in checks if ok]
    failed = [(name, detail) for name, ok, detail in checks if not ok]
    return len(failed) == 0, {
        "ready_for_live_review": len(failed) == 0,
        "summary": summary,
        "passed": passed,
        "failed": failed,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }
