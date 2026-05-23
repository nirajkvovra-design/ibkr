@echo off
REM Interactive Brokers Automated Trading System Launcher
REM This script starts the trading engine

setlocal enabledelayedexpansion

REM Set working directory
cd /d "%~dp0"

echo.
echo ========================================
echo IBKR Automated Trading System
echo ========================================
echo.

REM Prefer project virtual environment when present
set "PYTHON_CMD=python"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
)

REM Check if Python is installed
"%PYTHON_CMD%" --version > nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org
    pause
    exit /b 1
)

echo Checking dependencies...
"%PYTHON_CMD%" -m pip list | findstr "ibapi" > nul
if errorlevel 1 (
    echo Installing required packages...
    "%PYTHON_CMD%" -m pip install -r requirements.txt
)

echo.
echo Starting Trading Engine...
echo Log file: trading_logs.txt
echo.

REM Run the trading engine (graceful restart if already running)
"%PYTHON_CMD%" trading_launcher.py

pause
