import json
import logging
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta
import config

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

def setup_logging():
    """Configure logging for the trading system"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config.LOG_LEVEL))

    if logger.handlers:
        return logger

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format))
    file_handler = logging.FileHandler(config.LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

def get_logger(name):
    """Get a logger instance"""
    return logging.getLogger(name)


def send_alert(message, level="ERROR", details=None):
    """Send an alert to the log, alert file, and optional webhook."""
    logger = get_logger("alert")
    if level.upper() == "ERROR":
        logger.error(message)
    elif level.upper() == "WARNING":
        logger.warning(message)
    else:
        logger.info(message)

    alert = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "level": level.upper(),
        "message": message,
        "details": details or {},
    }

    try:
        with open(config.ALERT_FILE, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(alert, default=str) + "\n")
    except Exception as exc:
        logger.warning(f"Failed to write alert file: {exc}")

    if config.ALERT_WEBHOOK_ENABLED and config.ALERT_WEBHOOK_URL:
        try:
            payload = json.dumps(alert).encode("utf-8")
            request = urllib.request.Request(
                config.ALERT_WEBHOOK_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(request, timeout=config.ALERT_WEBHOOK_TIMEOUT)
        except Exception as exc:
            logger.warning(f"Alert webhook failed: {exc}")


def update_health_status(status):
    """Write a simple health status JSON file for monitoring."""
    status_record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        **status,
    }
    try:
        with open(config.HEALTH_STATUS_FILE, "w", encoding="utf-8") as handle:
            json.dump(status_record, handle, indent=2, default=str)
    except Exception as exc:
        get_logger("alert").warning(f"Failed to write health status file: {exc}")


def is_market_open():
    """Check if market is currently open"""
    from datetime import datetime
    import pytz
    
    tz = pytz.timezone('America/New_York')
    now = datetime.now(tz)
    
    # Market closed on weekends
    if now.weekday() >= 5:
        return False
    
    # Market hours check
    market_start = now.replace(hour=config.TRADING_HOURS_START,
                               minute=config.TRADING_MINUTES_START, second=0, microsecond=0)
    market_end = now.replace(hour=config.TRADING_HOURS_END,
                             minute=config.TRADING_MINUTES_END, second=0, microsecond=0)
    buffer = timedelta(minutes=config.REGULAR_HOURS_BUFFER_MINUTES)
    
    return market_start + buffer <= now <= market_end - buffer

def format_trade_log(action, symbol, quantity, price, order_id=None):
    """Format a trade action for logging"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"[{timestamp}] {action:10s} {symbol:6s} | Qty: {quantity:6.0f} | Price: ${price:8.2f}" + \
           (f" | OrderID: {order_id}" if order_id else "")

def calculate_position_size(account_value, risk_percent):
    """Calculate position size based on account value and risk percentage"""
    return account_value * risk_percent


def calculate_transaction_cost(quantity, price, side="BUY"):
    """Estimate transaction cost including commission and regulatory fees."""
    trade_value = quantity * price
    commission = max(quantity * config.COMMISSION_PER_SHARE, config.MIN_COMMISSION)
    sec_fee = 0.0
    finra_fee = 0.0

    if side.upper() == "SELL":
        sec_fee = trade_value * config.SEC_FEE_PERCENT
        finra_fee = trade_value * config.FINRA_FEE_PERCENT

    return round(commission + sec_fee + finra_fee, 2)


def get_front_month_future(symbol):
    """
    Returns the active front-month contract month (YYYYMM) for futures contracts.
    Handles quarterly rolls on the 10th of March (03), June (06), September (09), and December (12).
    Monthly rolls for commodities on the 20th of each preceding month.
    """
    now = datetime.now()
    year = now.year
    month = now.month
    sym = symbol.upper()
    
    if sym in {"ES", "NQ", "YM", "RTY"}:
        if month < 3 or (month == 3 and now.day < 10):
            expiry = 3
        elif month < 6 or (month == 6 and now.day < 10):
            expiry = 6
        elif month < 9 or (month == 9 and now.day < 10):
            expiry = 9
        elif month < 12 or (month == 12 and now.day < 10):
            expiry = 12
        else:
            expiry = 3
            year += 1
        return f"{year}{expiry:02d}"
    else:
        # Monthly contracts (CL, GC, etc.)
        expiry = month
        if now.day >= 20:
            expiry += 1
            if expiry > 12:
                expiry = 1
                year += 1
        return f"{year}{expiry:02d}"
