# Quick Start Guide - IBKR Trading System

Get your automated trading system running in 5 minutes!

## Prerequisites

- **Python 3.8+** - Download from https://www.python.org
- **Interactive Brokers Account** - https://www.interactivebrokers.com
- **TWS or IBGateway** - Download from IB website

## Step 1: Prepare Interactive Brokers (5 minutes)

1. **Open TWS or IBGateway**

2. **Enable API**
   - TWS: File → API → Settings
   - IBGateway: Settings → API → Settings
   - Check "Enable ActiveX and Socket Clients"
   - Click "OK"

3. **Note the Connection Port**
   - Paper trading: 7497 (default)
   - Live trading: 7496

## Step 2: Install Dependencies (2 minutes)

Open Command Prompt/PowerShell and run:

```bash
cd c:\ibkr
pip install -r requirements.txt
```

## Step 3: Verify Setup (1 minute)

```bash
python verify_setup.py
```

You should see all checks pass. If not, follow the instructions displayed.

## Step 4: Configure (2 minutes)

Edit `config.py`:

```python
# Line 1-3: Connection settings
IB_HOST = "127.0.0.1"      # Keep this
IB_PORT = 7497              # 7497 = Paper (recommended for testing)
PAPER_TRADING = True        # Keep True for now!

# Line 28-30: Risk limits
MAX_POSITION_SIZE = 10000   # Max per position
MAX_DAILY_LOSS = 5000       # Daily loss limit
```

## Step 5: Test (First Run)

```bash
python trading_engine.py
```

Expected output:
```
============================================================
Initializing Automated Trading Engine
============================================================
Connecting to IB on 127.0.0.1:7497...
Successfully connected to Interactive Brokers
Connected to account: DU12345
Trading mode: PAPER
...
```

If you see "Successfully connected", you're good! Press Ctrl+C to stop.

## Step 6: Enable Automatic Trading

### Option A: Simple - Run at Market Open (Easiest)

Create a scheduled task in Windows:

1. Open **Task Scheduler**
2. Right-click "Task Scheduler Library" → Create Basic Task
3. Name: "Start IBKR Trading"
4. Set trigger to "Daily" at 9:30 AM
5. Set action:
   - Program: `C:\ibkr\run_trading.bat`
   - Start in: `C:\ibkr`

### Option B: Advanced - Schedule Every 5 Minutes

Use PowerShell (run as Administrator):

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Python38\python.exe" `
  -Argument "C:\ibkr\task_scheduler_helper.py" -WorkingDirectory "C:\ibkr"

$trigger = New-ScheduledTaskTrigger -Daily -At 9:30AM

$principal = New-ScheduledTaskPrincipal -UserID "SYSTEM" `
  -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -Action $action -Trigger $trigger `
  -Principal $principal -TaskName "IBKR Trading" `
  -Description "Auto trading during market hours"
```

## Monitoring

### View Logs
```bash
tail -f trading_logs.txt
# Or open in Notepad: notepad trading_logs.txt
```

### Check Status
While running, the system logs:
- ✓ Connected positions
- ✓ Trades executed  
- ✓ Daily P&L
- ✓ Account value

## Troubleshooting

**"Failed to connect to Interactive Brokers"**
- TWS/IBGateway not running? Start it.
- Wrong port? Check `config.py`
- Firewall blocking? Add exception for port 7497/7496

**"No trades executing"**
- Is market open? Check trading hours in `config.py`
- Is paper trading on? It should be for testing
- Check logs for signal generation

**"High CPU usage"**
- Reduce trading frequency (5 minutes default)
- Edit `_setup_schedule()` in `trading_engine.py`

## Next Steps

1. **Let it run for a full day** - Watch the logs
2. **Review the trades** - Did they make sense?
3. **Adjust parameters** - Fine-tune risk and strategies
4. **Read README.md** - Full documentation

## Important ⚠️

- **ALWAYS test with PAPER TRADING first**
- Don't go live until you're confident
- Monitor the first few days closely
- Keep TWS/IBGateway running during market hours
- Set realistic expectations - past performance ≠ future results

## Need Help?

1. Check `README.md` - Comprehensive guide
2. Review logs - `trading_logs.txt`
3. Read strategy code - `strategies.py`
4. Check IB API docs - https://interactivebrokers.com/api

---

**Happy trading! Remember: Start small, test thoroughly, scale gradually.**
