"""
Track positions opened during the current US/Eastern session for end-of-day flattening.
"""

import json
from datetime import datetime
from pathlib import Path

import pytz

import config
from utils import get_logger

logger = get_logger(__name__)

_TZ = pytz.timezone("America/New_York")
_STORE = Path(getattr(config, "DAILY_POSITIONS_FILE", "daily_positions.json"))


def _today():
    return datetime.now(_TZ).strftime("%Y-%m-%d")


def _load():
    if not _STORE.exists():
        return {"session_date": _today(), "opens": {}, "starting_positions": {}}
    try:
        data = json.loads(_STORE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {"session_date": _today(), "opens": {}, "starting_positions": {}}
    if data.get("session_date") != _today():
        return {"session_date": _today(), "opens": {}, "starting_positions": {}}
    data.setdefault("opens", {})
    data.setdefault("starting_positions", {})
    return data


def _save(data):
    _STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def reset_if_new_day(starting_positions=None):
    data = _load()
    if data["session_date"] != _today():
        data = {
            "session_date": _today(),
            "opens": {},
            "starting_positions": starting_positions or {}
        }
        _save(data)
        logger.info(f"Daily position tracker reset for new session. Starting positions tracked: {list(data['starting_positions'].keys())}")
    elif starting_positions:
        # If it's the same day, but we initialized again and got starting positions (e.g. first startup of the engine today),
        # we can set them if not already present.
        if "starting_positions" not in data or not data["starting_positions"]:
            data["starting_positions"] = starting_positions
            _save(data)
            logger.info(f"Recorded starting positions for today: {list(starting_positions.keys())}")


def record_open(symbol, quantity, entry_price, order_id=None):
    data = _load()
    data["opens"][symbol.upper()] = {
        "quantity": quantity,
        "entry_price": entry_price,
        "opened_at": datetime.now(_TZ).isoformat(timespec="seconds"),
        "order_id": order_id,
    }
    _save(data)
    logger.info(f"Recorded today's open: {symbol} x {quantity} @ ${entry_price:.2f}")


def record_close(symbol):
    data = _load()
    symbol = symbol.upper()
    if symbol in data["opens"]:
        del data["opens"][symbol]
        _save(data)
        logger.info(f"Removed {symbol} from today's open positions")


def get_opened_today():
    return list(_load()["opens"].keys())


def get_open_details():
    return dict(_load()["opens"])


def sync_from_ib_positions(positions):
    """Align tracker with live IB positions opened earlier today (e.g. after restart)."""
    data = _load()
    changed = False
    starting_positions = data.get("starting_positions", {})
    
    for symbol, info in positions.items():
        symbol = symbol.upper()
        qty = info.get("quantity", 0)
        if qty <= 0:
            continue
            
        starting_qty = starting_positions.get(symbol, 0)
        # If we have a position, check if we opened more today
        incremental_qty = qty - starting_qty
        
        if incremental_qty > 0:
            if symbol in data["opens"]:
                # If already tracked, let's update the quantity if it changed
                if data["opens"][symbol]["quantity"] != incremental_qty:
                    data["opens"][symbol]["quantity"] = incremental_qty
                    changed = True
            else:
                # Add to opens
                data["opens"][symbol] = {
                    "quantity": incremental_qty,
                    "entry_price": info.get("avg_cost") or 0,
                    "opened_at": datetime.now(_TZ).isoformat(timespec="seconds"),
                    "order_id": None,
                    "synced_from_ib": True,
                }
                changed = True
        else:
            # If the quantity is <= starting quantity, it shouldn't be in opens
            if symbol in data["opens"]:
                del data["opens"][symbol]
                changed = True
                
    if changed:
        _save(data)


def clear_all():
    data = _load()
    data["opens"] = {}
    _save(data)

