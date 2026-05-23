import os
from dotenv import load_dotenv

load_dotenv()


def _bool_env(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name, default):
    return int(os.getenv(name, default))


def _float_env(name, default):
    return float(os.getenv(name, default))


def _list_env(name, default):
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip().upper() for item in value.split(",") if item.strip()]


# Interactive Brokers Connection Settings
IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = _int_env("IB_PORT", 7497)  # 7497 for paper trading, 7496 for live trading
IB_CLIENTID = _int_env("IB_CLIENTID", 1)
IB_ACCOUNT = os.getenv("IB_ACCOUNT", "")  # Leave empty to use default, or specify account ID

# Trading Hours (24-hour format, assumes US/Eastern timezone)
TRADING_HOURS_START = 9  # 9:30 AM
TRADING_MINUTES_START = 30
TRADING_HOURS_END = 16  # 4:00 PM
TRADING_MINUTES_END = 0

# Risk Management
STARTER_ACCOUNT_MODE = _bool_env("STARTER_ACCOUNT_MODE", True)
STARTER_ACCOUNT_CAPITAL = _float_env("STARTER_ACCOUNT_CAPITAL", 1000)
MAX_POSITION_SIZE = _float_env("MAX_POSITION_SIZE", 50)  # Maximum dollar amount per position
MAX_DAILY_LOSS = _float_env("MAX_DAILY_LOSS", 20)  # Stop trading if daily loss exceeds this
POSITION_SIZE_PERCENT = _float_env("POSITION_SIZE_PERCENT", 0.05)  # Use 5% of cash per trade
MAX_PORTFOLIO_POSITION_PERCENT = _float_env("MAX_PORTFOLIO_POSITION_PERCENT", 0.05)
MAX_OPEN_POSITIONS = _int_env("MAX_OPEN_POSITIONS", 1)
DYNAMIC_RISK_SCALING = _bool_env("DYNAMIC_RISK_SCALING", True)  # Scale position sizes and risk dynamically as capital grows
REQUIRE_SETTLED_CASH_FOR_BUYS = _bool_env("REQUIRE_SETTLED_CASH_FOR_BUYS", True)
STOP_LOSS_PERCENT = _float_env("STOP_LOSS_PERCENT", 1.25)
TAKE_PROFIT_PERCENT = _float_env("TAKE_PROFIT_PERCENT", 0.75)
MAX_DAILY_TRADES = _int_env("MAX_DAILY_TRADES", 1)
MAX_FEE_TO_PROFIT_RATIO = _float_env("MAX_FEE_TO_PROFIT_RATIO", 0.35)  # Max fees as fraction of expected profit
EARNINGS_BLACKOUT_DAYS_BEFORE = _int_env("EARNINGS_BLACKOUT_DAYS_BEFORE", 3)
EARNINGS_BLACKOUT_DAYS_AFTER = _int_env("EARNINGS_BLACKOUT_DAYS_AFTER", 1)
DIVIDEND_BLACKOUT_DAYS_BEFORE = _int_env("DIVIDEND_BLACKOUT_DAYS_BEFORE", 1)
DIVIDEND_BLACKOUT_DAYS_AFTER = _int_env("DIVIDEND_BLACKOUT_DAYS_AFTER", 0)


# Strategy Settings
MIN_PRICE = _float_env("MIN_PRICE", 10.0)  # Minimum stock price to trade
MAX_PRICE = _float_env("MAX_PRICE", 120.0)  # Maximum stock price to trade
STARTER_MAX_PRICE = _float_env("STARTER_MAX_PRICE", 120.0)
STARTER_MIN_MARKET_CAP = _float_env("STARTER_MIN_MARKET_CAP", 5_000_000_000)
MOMENTUM_THRESHOLD = 0.02  # 2% price movement threshold
VOLUME_THRESHOLD = 1000000  # Minimum average volume
REQUIRE_MARKET_REGIME_CONFIRMATION = _bool_env("REQUIRE_MARKET_REGIME_CONFIRMATION", True)
MARKET_REGIME_SYMBOLS = _list_env("MARKET_REGIME_SYMBOLS", ["SPY", "QQQ"])
MAX_ENTRY_SLIPPAGE_PERCENT = _float_env("MAX_ENTRY_SLIPPAGE_PERCENT", 0.10)
MAX_EXIT_SLIPPAGE_PERCENT = _float_env("MAX_EXIT_SLIPPAGE_PERCENT", 0.15)
COMMISSION_PER_SHARE = _float_env("COMMISSION_PER_SHARE", 0.005)
MIN_COMMISSION = _float_env("MIN_COMMISSION", 1.00)
SEC_FEE_PERCENT = _float_env("SEC_FEE_PERCENT", 0.0000221)
FINRA_FEE_PERCENT = _float_env("FINRA_FEE_PERCENT", 0.000119)
USE_LIMIT_ORDERS_ONLY = _bool_env("USE_LIMIT_ORDERS_ONLY", True)
REGULAR_HOURS_BUFFER_MINUTES = _int_env("REGULAR_HOURS_BUFFER_MINUTES", 5)
TRADE_FREE_US_STOCKS_ONLY = _bool_env("TRADE_FREE_US_STOCKS_ONLY", True)
REQUIRE_BULLISH_NEWS_FOR_BUY = _bool_env("REQUIRE_BULLISH_NEWS_FOR_BUY", True)
WATCHLIST_METHOD = os.getenv("WATCHLIST_METHOD", "news_trending")
MAX_WATCHLIST_SIZE = _int_env("MAX_WATCHLIST_SIZE", 8)
USE_AI_INFRA_UNIVERSE = _bool_env("USE_AI_INFRA_UNIVERSE", True)
MIN_BUY_VOLUME_RATIO = _float_env("MIN_BUY_VOLUME_RATIO", 1.1)
MIN_BUY_1D_CHANGE = _float_env("MIN_BUY_1D_CHANGE", 0.0025)
MIN_BUY_5D_CHANGE = _float_env("MIN_BUY_5D_CHANGE", 0.01)
MIN_BUY_SIGNALS_FOR_ENTRY = _int_env("MIN_BUY_SIGNALS_FOR_ENTRY", 4)
MIN_SELL_SIGNALS_FOR_ENTRY = _int_env("MIN_SELL_SIGNALS_FOR_ENTRY", 4)
MIN_WEAK_BUY_SIGNALS = _int_env("MIN_WEAK_BUY_SIGNALS", 2)
TRADING_LOOP_MINUTES = _int_env("TRADING_LOOP_MINUTES", 5)
NEWS_TRENDING_MIN_SCORE = _int_env("NEWS_TRENDING_MIN_SCORE", 5)
ALLOWED_US_STOCKS = _list_env("ALLOWED_US_STOCKS", [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO",
    "AMD", "NFLX", "CRM", "ORCL", "COST", "ADBE", "NOW", "PANW",
    "CRWD", "MU", "QCOM", "INTC", "SHOP", "UBER", "ABNB", "PLTR",
    "JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "AXP", "PYPL",
    "LLY", "UNH", "JNJ", "ABBV", "MRK", "PFE", "TMO", "ISRG",
    "XOM", "CVX", "CAT", "GE", "BA", "DE", "WMT", "HD",
    "MRVL", "ANET", "VRT", "DELL", "SMCI", "WDC", "STX", "LRCX",
    "AMAT", "KLAC", "TER", "LITE", "COHR", "CIEN", "ETN", "PWR",
    "CEG", "EQIX", "DLR", "ADI", "TXN", "MPWR", "ON",
    "MSTR", "COIN", "ARM", "DKNG", "CELH", "SOXX", "TQQQ"
])
AI_INFRA_STOCKS = _list_env("AI_INFRA_STOCKS", [
    "NVDA", "AMD", "AVGO", "MU", "MRVL", "QCOM", "ANET", "VRT",
    "DELL", "SMCI", "WDC", "STX", "LRCX", "AMAT", "KLAC", "TER",
    "LITE", "COHR", "CIEN", "ETN", "PWR", "CEG", "GOOGL", "MSFT",
    "AMZN", "META", "ORCL", "ADI", "TXN", "MPWR", "ON", "INTC",
    "ARM", "MSTR", "COIN"
])
STARTER_STOCKS = _list_env("STARTER_STOCKS", [
    "INTC", "HPE", "BAC", "WFC", "CSCO", "PFE", "KO", "T",
    "VZ", "F", "GM", "UBER", "PYPL", "ON", "HPQ"
])
EXCLUDED_EVENT_SENSITIVE_STOCKS = _list_env("EXCLUDED_EVENT_SENSITIVE_STOCKS", [
    "XOM", "CVX", "OXY", "COP", "SLB", "HAL", "USO"
])

# Logging
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_FILE = "trading_logs.txt"
ALERT_FILE = os.getenv("ALERT_FILE", "trading_alerts.log")
ALERT_WEBHOOK_ENABLED = _bool_env("ALERT_WEBHOOK_ENABLED", False)
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
ALERT_WEBHOOK_TIMEOUT = _int_env("ALERT_WEBHOOK_TIMEOUT", 5)
HEALTH_STATUS_FILE = os.getenv("HEALTH_STATUS_FILE", "trading_health.json")

# Paper Trading (set to True to test without real money)
PAPER_TRADING = _bool_env("PAPER_TRADING", True)

# Live trading safety gate. Keep live connection settings, but refuse orders until
# this is explicitly enabled in the environment after account setup is complete.
ENABLE_LIVE_TRADING = _bool_env("ENABLE_LIVE_TRADING", False)

# News and market-data safety
NEWS_REFRESH_MINUTES = _int_env("NEWS_REFRESH_MINUTES", 15)
REQUIRE_NEWS_CHECK = _bool_env("REQUIRE_NEWS_CHECK", True)
BLOCK_ON_NEWS_FAILURE = _bool_env("BLOCK_ON_NEWS_FAILURE", True)

# Reconnection settings
RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY = 5  # seconds
STALE_ORDER_TIMEOUT = _int_env("STALE_ORDER_TIMEOUT", 120)  # seconds before stale working orders are cancelled
ORDER_CONFIRMATION_TIMEOUT = _int_env("ORDER_CONFIRMATION_TIMEOUT", 60)  # seconds to wait for a fill before retry
ORDER_RETRY_LIMIT = _int_env("ORDER_RETRY_LIMIT", 1)
ORDER_RETRY_FALLBACK_TO_MARKET = _bool_env("ORDER_RETRY_FALLBACK_TO_MARKET", False)

# Paper validation period (run engine in demo before live money)
PAPER_JOURNAL_FILE = os.getenv("PAPER_JOURNAL_FILE", "paper_trading_journal.jsonl")
PAPER_DAILY_PNL_FILE = os.getenv("PAPER_DAILY_PNL_FILE", "daily_pnl.csv")
PAPER_TRADE_HISTORY_FILE = os.getenv("PAPER_TRADE_HISTORY_FILE", "trade_history.csv")
PAPER_MIN_SESSION_DAYS = _int_env("PAPER_MIN_SESSION_DAYS", 3)
PAPER_MIN_EXECUTIONS = _int_env("PAPER_MIN_EXECUTIONS", 3)
ENGINE_PID_FILE = os.getenv("ENGINE_PID_FILE", ".trading_engine.pid")
ENGINE_RESTART_FILE = os.getenv("ENGINE_RESTART_FILE", ".trading_engine.restart")
RESTART_SHUTDOWN_TIMEOUT = _int_env("RESTART_SHUTDOWN_TIMEOUT", 180)
RESTART_POLL_INTERVAL = _int_env("RESTART_POLL_INTERVAL", 2)
ENABLE_MARKET_RESEARCH = _bool_env("ENABLE_MARKET_RESEARCH", True)
RESEARCH_LOG_FILE = os.getenv("RESEARCH_LOG_FILE", "trading_research.jsonl")
CLOSE_TODAYS_POSITIONS_AT_EOD = _bool_env("CLOSE_TODAYS_POSITIONS_AT_EOD", True)
DAILY_POSITIONS_FILE = os.getenv("DAILY_POSITIONS_FILE", "daily_positions.json")
EOD_CLOSE_MINUTES_BEFORE_END = _int_env("EOD_CLOSE_MINUTES_BEFORE_END", 5)
# Faster paper learning: more signals/trades while still using limits & journal (disable via .env)
PAPER_LEARNING_MODE = _bool_env("PAPER_LEARNING_MODE", True)

# Strategy Selection and Machine Learning Configs
SELECTED_STRATEGY = os.getenv("SELECTED_STRATEGY", "MOMENTUM")  # MOMENTUM or ML
ML_MODEL_TYPE = os.getenv("ML_MODEL_TYPE", "MONTE_CARLO")  # MONTE_CARLO, LSTM, or RNN
ML_FORECAST_PERIOD = _int_env("ML_FORECAST_PERIOD", 10)  # Number of days to forecast
ML_MONTE_CARLO_SIMULATIONS = _int_env("ML_MONTE_CARLO_SIMULATIONS", 500)  # Number of simulation paths
ML_BUY_THRESHOLD_PERCENT = _float_env("ML_BUY_THRESHOLD_PERCENT", 1.5)  # Expected gain to BUY (e.g. 1.5%)
ML_SELL_THRESHOLD_PERCENT = _float_env("ML_SELL_THRESHOLD_PERCENT", -1.0)  # Expected loss to SELL (e.g. -1.0%)
ML_NEURAL_WINDOW_SIZE = _int_env("ML_NEURAL_WINDOW_SIZE", 10)  # Time window for LSTM/RNN
ML_NEURAL_EPOCHS = _int_env("ML_NEURAL_EPOCHS", 20)  # Training epochs for dynamic neural networks

# Pairs Trading Configurations
PAIRS_WATCHLIST = [("V", "MA"), ("KO", "PEP"), ("AAPL", "MSFT")]
PAIRS_LOOKBACK = _int_env("PAIRS_LOOKBACK", 20)  # Rolling window for calculating mean and std dev
PAIRS_ENTRY_ZSCORE = _float_env("PAIRS_ENTRY_ZSCORE", 2.0)  # Standard deviations to trigger trade
PAIRS_EXIT_ZSCORE = _float_env("PAIRS_EXIT_ZSCORE", 0.0)  # Standard deviations to exit (mean reversion)

# Volatility Breakout Configurations
BREAKOUT_LOOKBACK = _int_env("BREAKOUT_LOOKBACK", 20)  # Donchian channel lookback window
BREAKOUT_ATR_MULTIPLIER = _float_env("BREAKOUT_ATR_MULTIPLIER", 1.5)  # Volatility ATR channel expander



def _apply_env_overrides(overrides):
    """Set module-level settings only when the variable is not set in .env."""
    module_globals = globals()
    for name, value in overrides.items():
        if os.getenv(name) is None:
            module_globals[name] = value


# Paper/demo: fix IB paper-account quirks + optional faster-learning profile (live defaults unchanged).
if PAPER_TRADING:
    _apply_env_overrides({
        "REQUIRE_SETTLED_CASH_FOR_BUYS": False,
        "STARTER_ACCOUNT_MODE": False,
        "REQUIRE_MARKET_REGIME_CONFIRMATION": False,
    })
    if PAPER_LEARNING_MODE:
        _apply_env_overrides({
            "MAX_POSITION_SIZE": 500.0,
            "MAX_DAILY_LOSS": 250.0,
            "MAX_DAILY_TRADES": 5,
            "MAX_OPEN_POSITIONS": 2,
            "POSITION_SIZE_PERCENT": 0.10,
            "MAX_PORTFOLIO_POSITION_PERCENT": 0.15,
            "TAKE_PROFIT_PERCENT": 1.5,
            "STOP_LOSS_PERCENT": 2.0,
            "REQUIRE_BULLISH_NEWS_FOR_BUY": False,
            "BLOCK_ON_NEWS_FAILURE": False,
            "MIN_BUY_VOLUME_RATIO": 1.0,
            "MIN_BUY_1D_CHANGE": 0.001,
            "MIN_BUY_5D_CHANGE": 0.005,
            "MIN_BUY_SIGNALS_FOR_ENTRY": 2,
            "MIN_SELL_SIGNALS_FOR_ENTRY": 4,
            "MIN_WEAK_BUY_SIGNALS": 2,
            "TRADING_LOOP_MINUTES": 3,
            "MAX_WATCHLIST_SIZE": 12,
            "NEWS_TRENDING_MIN_SCORE": 2,
        })
