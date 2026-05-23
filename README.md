# Interactive Brokers Automated Trading System

A complete Python-based automated trading system for Interactive Brokers that runs automatically during trading hours.

## Features

- **Automated Trading**: Executes trades based on configurable strategies
- **Real-time Risk Management**: Built-in position sizing, stop-loss, and take-profit management
- **Trading Hour Scheduling**: Automatically activates during market hours
- **Multiple Strategies**: Momentum-based and Grid trading strategies included
- **Comprehensive Logging**: Detailed logs of all trades and system events
- **Account Management**: Real-time position and account value tracking
- **Paper Trading Mode**: Test strategies without risking real money

## System Architecture

```
trading_engine.py          # Main engine with scheduling
├── ib_connection.py       # Interactive Brokers API wrapper
├── strategies.py          # Trading strategies
├── risk_manager.py        # Risk management and position control
├── config.py             # Configuration settings
├── utils.py              # Utility functions
└── task_scheduler_helper.py  # Windows Task Scheduler integration
```

## Prerequisites

1. **Interactive Brokers Account**
   - Active TWS (Trader Workstation) or IBGateway running
   - API enabled in account settings

2. **Python 3.8 or higher**
   - Download from https://www.python.org

3. **TWS/IBGateway**
   - Download from https://www.interactivebrokers.com
   - Ensure "Enable API" is checked in settings

## Installation

1. **Clone/Extract the project**
   ```
   cd c:\ibkr
   ```

2. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

3. **Configure settings**
   Edit `config.py`:
   - Set `IB_HOST` and `IB_PORT` (7497 for paper, 7496 for live)
   - Set `PAPER_TRADING = True` for testing
   - Adjust trading hours, risk limits, and strategy parameters

## Quick Start

### Manual Start (Testing)

```bash
python trading_engine.py
```

The system will:
1. Connect to Interactive Brokers
2. Retrieve account information
3. Start monitoring market conditions
4. Execute trades based on strategy signals
5. Log all activity to `trading_logs.txt`

### Automated Start via Batch File

```bash
run_trading.bat
```

This will install dependencies if needed and start the engine.

## Configuration Guide

### config.py

**Connection Settings**
```python
IB_HOST = "127.0.0.1"        # TWS/IBGateway host
IB_PORT = 7497                # 7497 = Paper, 7496 = Live
PAPER_TRADING = True          # Always test first!
```

**Trading Hours** (24-hour format, US/Eastern timezone)
```python
TRADING_HOURS_START = 9       # 9:30 AM market open
TRADING_MINUTES_START = 30
TRADING_HOURS_END = 16        # 4:00 PM market close
TRADING_MINUTES_END = 0
```

**Risk Management**
```python
MAX_POSITION_SIZE = 10000     # Max per position
MAX_DAILY_LOSS = 5000         # Daily loss limit
POSITION_SIZE_PERCENT = 0.02  # 2% per trade
```

**Strategy Settings**
```python
MOMENTUM_THRESHOLD = 0.02     # 2% momentum threshold
VOLUME_THRESHOLD = 1000000    # Min volume to trade
MIN_PRICE = 5.0               # Min stock price
MAX_PRICE = 500.0             # Max stock price
```

## Scheduling for Automatic Execution

### Option 1: Windows Task Scheduler (Recommended)

1. **Open Task Scheduler**
   - Press `Win + R`, type `taskschd.msc`, press Enter

2. **Create New Task**
   - Right-click "Task Scheduler Library" → "Create Basic Task"
   - Name: "IBKR Trading Engine"
   - Description: "Automated trading during market hours"

3. **Set Trigger**
   - Choose "Daily"
   - Set time to market open (9:30 AM ET)
   - Check "Repeat task every 5 minutes for a duration of 7 hours"

4. **Set Action**
   - Program: `C:\Python3X\python.exe` (your Python path)
   - Arguments: `C:\ibkr\task_scheduler_helper.py`
   - Start in: `C:\ibkr`

5. **Set Conditions**
   - Check "Wake the computer to run this task"
   - Uncheck "Stop the task if it runs longer than"

6. **Finish**
   - Check "Open the Properties dialog for this task when I click Finish"
   - Set to run with highest privileges
   - Check "Run whether user is logged in or not"

### Option 2: Command Line Task Creation

```powershell
# Open PowerShell as Administrator

$action = New-ScheduledTaskAction -Execute "C:\Python3X\python.exe" `
  -Argument "C:\ibkr\task_scheduler_helper.py" `
  -WorkingDirectory "C:\ibkr"

$trigger = New-ScheduledTaskTrigger -Daily -At 9:30AM

$principal = New-ScheduledTaskPrincipal -UserID "SYSTEM" `
  -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -Action $action -Trigger $trigger `
  -Principal $principal -TaskName "IBKR Trading Engine" `
  -Description "Automated trading during market hours"
```

## Trading Strategies

### Momentum Strategy (Default)

Buys when price shows upward momentum, sells on downward momentum.

```python
# In trading_engine.py
self.strategy = MomentumStrategy(self.ib_connection)
```

Configuration in `config.py`:
- `MOMENTUM_THRESHOLD`: Price movement % to trigger signal
- `VOLUME_THRESHOLD`: Minimum volume to trade

### Grid Trading Strategy

Places orders at regular price intervals, averaging down.

```python
# To use instead
self.strategy = GridTradingStrategy(
    self.ib_connection,
    symbol='AAPL',
    grid_size=10,
    grid_interval=50
)
```

### Creating Custom Strategies

Inherit from `TradingStrategy` in `strategies.py`:

```python
from strategies import TradingStrategy

class MyStrategy(TradingStrategy):
    def check_trading_conditions(self):
        # Your logic here
        return True
    
    def generate_signals(self, symbols):
        # Return {'SYMBOL': 'BUY'/'SELL'/'HOLD'}
        return signals
    
    def execute_trades(self, signals):
        # Place orders based on signals
        pass
```

## Risk Management

The system includes automatic risk controls:

1. **Position Sizing**: No single trade exceeds `MAX_POSITION_SIZE`
2. **Stop Loss**: Automatically exits losing positions
3. **Take Profit**: Closes winners at target prices
4. **Daily Loss Limit**: Stops trading after `MAX_DAILY_LOSS`
5. **Portfolio Limit**: No position > 10% of account

## Monitoring & Logs

**Log Files**
- `trading_logs.txt`: All trading activity
- `scheduler_log.txt`: Task Scheduler execution log

**Monitor Active Sessions**
```python
python -c "from trading_engine import TradingEngine; e = TradingEngine(); e.start()"
```

**Check Status**
```python
# View current status while running
import trading_engine
engine = trading_engine.TradingEngine()
print(engine.get_status())
```

## Troubleshooting

### Connection Issues
- **Error**: "Failed to connect to Interactive Brokers"
  - Ensure TWS/IBGateway is running
  - Check IB_PORT in config (7497=paper, 7496=live)
  - Verify API is enabled in TWS settings

### No Trades Executing
- Check `PAPER_TRADING` setting
- Verify market is open (9:30 AM - 4:00 PM ET)
- Review strategy signals in logs
- Check account has sufficient cash

### High CPU Usage
- Increase the sleep interval in the scheduler
- Reduce trading loop frequency (currently 5 minutes)
- Check for infinite loops in custom strategies

## Best Practices

1. **Always Test with Paper Trading First**
   - Set `PAPER_TRADING = True`
   - Run for at least a week
   - Verify logic and risk management

2. **Monitor the First Live Session**
   - Don't run overnight initially
   - Watch the logs closely
   - Be ready to stop the system

3. **Maintain Realistic Expectations**
   - Start with conservative risk settings
   - Test multiple strategies
   - Backtest if possible

4. **Regular Maintenance**
   - Review logs daily
   - Adjust parameters based on performance
   - Update risk limits as needed

5. **Keep TWS/IBGateway Running**
   - Don't log out during trading hours
   - Set session timeout to maximum
   - Consider running on dedicated machine

## Advanced Configuration

### Custom Watchlist
Edit the watchlist in `trading_engine.py`:
```python
symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
```

### Modify Schedule
Edit `_setup_schedule()` in `trading_engine.py`:
```python
# Trade every 10 minutes instead of 5
schedule.every(10).minutes.do(self._trading_loop)

# Add additional pre-market logic
schedule.every().weekday.at("09:00").do(self._pre_market_setup)
```

### Custom Risk Parameters
```python
# In risk_manager.py
self.risk_manager.set_stop_loss(symbol, entry_price, stop_loss_percent=3)
self.risk_manager.set_take_profit(symbol, entry_price, take_profit_percent=10)
```

## Support & Documentation

- **Interactive Brokers API**: https://interactivebrokers.com/en/software/api/latest/
- **Python ibapi**: `pip install ibapi --upgrade`
- **Schedule Library**: https://github.com/dbader/schedule

## Disclaimer

This software is provided for educational purposes. Trading involves risk. You are responsible for:
- Understanding the strategies being used
- Setting appropriate risk limits
- Monitoring your account regularly
- Complying with all applicable regulations

**ALWAYS TEST WITH PAPER TRADING FIRST**

## License

Use this software at your own risk. The author assumes no liability for financial losses.
