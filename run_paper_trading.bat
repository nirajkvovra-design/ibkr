@echo off
REM Paper/demo trading — run for several market days before live money.
cd /d "%~dp0"

set "PYTHON_CMD=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"

echo.
echo ========================================
echo IBKR Paper Trading (demo money only)
echo ========================================
echo Port 7497 - Journal: paper_trading_journal.jsonl
echo Paper learning mode: more trades, $500 max position, 3-min loop
echo Keep TWS Paper Trading open with API enabled.
echo.

set PAPER_TRADING=True
set IB_PORT=7497
set ENABLE_LIVE_TRADING=False

"%PYTHON_CMD%" trading_launcher.py

pause
