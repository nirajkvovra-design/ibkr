@echo off
REM Windows batch script to launch the concurrent multi-strategy testing orchestrator
cd /d "%~dp0"

set "PYTHON_CMD=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"

echo ============================================================
echo   QUANTITATIVE TRADING OPERATING SYSTEM - CONCURRENT RUNNER
echo ============================================================
echo.

"%PYTHON_CMD%" run_concurrent_strategies.py

pause
