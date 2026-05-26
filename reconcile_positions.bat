@echo off
REM Windows batch script to run the positions reconciliation utility
cd /d "%~dp0"

set "PYTHON_CMD=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"

echo ============================================================
echo   QUANTITATIVE TRADING OPERATING SYSTEM - PORTFOLIO SYNC
echo ============================================================
echo.

"%PYTHON_CMD%" reconcile_positions.py

pause
