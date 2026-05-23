"""
Task Scheduler Helper Script
Designed to run the trading engine via Windows Task Scheduler
This allows fully automated trading during market hours
"""

import os
import sys
import time
import subprocess
from datetime import datetime
import pytz

# Add the script directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def is_market_open():
    """Check if market is currently open"""
    tz = pytz.timezone('America/New_York')
    now = datetime.now(tz)
    
    # Market closed on weekends
    if now.weekday() >= 5:
        return False
    
    # Market hours: 9:30 AM - 4:00 PM ET
    market_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_end = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_start <= now <= market_end

def log_event(message):
    """Log events to file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = "scheduler_log.txt"
    
    with open(log_file, 'a') as f:
        f.write(f"[{timestamp}] {message}\n")
    
    print(f"[{timestamp}] {message}")

def main():
    """Main entry point for scheduled execution"""
    log_event("Task Scheduler triggered")
    
    # Check if market is open
    if not is_market_open():
        log_event("Market is not open. Exiting.")
        return
    
    log_event("Market is open. Starting trading engine...")
    
    try:
        # Run trading engine
        result = subprocess.run(
            [sys.executable, 'trading_engine.py'],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=False,
            timeout=None
        )
        
        log_event(f"Trading engine exited with code: {result.returncode}")
        
    except subprocess.TimeoutExpired:
        log_event("Trading engine timeout")
    except Exception as e:
        log_event(f"Error starting trading engine: {e}")

if __name__ == "__main__":
    main()
