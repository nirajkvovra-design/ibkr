@echo off
REM Paper/demo trading — run for several market days before live money.
cd /d "%~dp0"

set "PYTHON_CMD=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"

echo ============================================================
echo   QUANTITATIVE TRADING OPERATING SYSTEM - LAUNCH RADAR
echo ============================================================
echo.
echo Select the Quantitative Strategy to test:
echo   [1] Momentum Strategy (MOMENTUM) - Technical Indicators [Default]
echo   [2] Machine Learning Strategy (ML) - Stochastic Monte Carlo Forecasts
echo   [3] Cointegrated Pairs Trading Strategy (PAIRS) - Stat Arbitrage
echo   [4] Volatility Breakout Strategy (BREAKOUT) - Donchian Channels
echo   [5] IPO Breakout Strategy (IPO) - Chart Base Breakout
echo   [6] Correlated Laggard Strategy (LAGGER) - Sector Catch-Up
echo.
set /p STRATEGY_CHOICE="Enter selection [1-6, default=1]: "

set SELECTED_STRATEGY=MOMENTUM
if "%STRATEGY_CHOICE%"=="2" set SELECTED_STRATEGY=ML
if "%STRATEGY_CHOICE%"=="3" set SELECTED_STRATEGY=PAIRS
if "%STRATEGY_CHOICE%"=="4" set SELECTED_STRATEGY=BREAKOUT
if "%STRATEGY_CHOICE%"=="5" set SELECTED_STRATEGY=IPO
if "%STRATEGY_CHOICE%"=="6" set SELECTED_STRATEGY=LAGGER

echo.
echo Select the Safety Gate Execution Stage:
echo   [1] Shadow Mode (SHADOW) - Logs signals, blocks paper order routing
echo   [2] Micro Sizing (MICRO) - Truncates all fills to exactly 1 share
echo   [3] Limited Sizing (LIMITED) - Caps exposure at 5% of net equity
echo   [4] Full Execution (FULL) - Unrestricted paper executions [Recommended for Paper]
echo.
set /p STAGE_CHOICE="Enter selection [1-4, default=4]: "

set TRADING_STAGE=FULL
if "%STAGE_CHOICE%"=="1" set TRADING_STAGE=SHADOW
if "%STAGE_CHOICE%"=="2" set TRADING_STAGE=MICRO
if "%STAGE_CHOICE%"=="3" set TRADING_STAGE=LIMITED

echo.
echo ============================================================
echo   LAUNCHING ENGINE DAEMON IN PAPER PORT 7497
echo ============================================================
echo Strategy    : %SELECTED_STRATEGY%
echo Safety Stage: %TRADING_STAGE%
echo.
echo Keep Trader Workstation (TWS) open with ActiveX API enabled.
echo ============================================================
echo.

set PAPER_TRADING=True
set IB_PORT=7497
set ENABLE_LIVE_TRADING=False

"%PYTHON_CMD%" trading_launcher.py

pause
