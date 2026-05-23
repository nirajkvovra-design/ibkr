#!/usr/bin/env python3
"""
RUN LONG SESSION - Long-duration auto trading session with continuous scanning
Optimized for running from market open until close with 5-minute scanner refresh
"""

import subprocess
import sys
import os
import time
from datetime import datetime, timedelta
import argparse

def run_scanner_first():
    """Run the scanner once to generate initial results"""
    print("🔍 Running initial scanner scan...")
    cmd = [
        "python", "technical_scanner.py",
        "--preset", "day_trading",
        "--interval", "5min",
        "--max-results", "15",
        "--min-score", "70",
        "--client-id", "8"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode == 0:
            print("✅ Initial scanner completed successfully")
            return True
        else:
            print(f"❌ Initial scanner failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("⏰ Initial scanner timed out, proceeding anyway...")
        return True
    except Exception as e:
        print(f"❌ Error running initial scanner: {e}")
        return False

def run_long_session_trader(scanner_file, auto_execute=False, session_duration=390):
    """Run the auto-trader with long session settings"""
    print(f"🚀 Starting Long Session Auto Trader...")
    print(f"   Session Duration: {session_duration} minutes")
    print(f"   Scanner Refresh: Every 5 minutes")
    print(f"   Auto Execute: {'ENABLED' if auto_execute else 'DISABLED'}")
    
    cmd = [
        "python", "auto_day_trader.py",
        "--scanner-file", scanner_file,
        "--continuous-session",                    # Enable continuous session
        "--session-duration", str(session_duration),  # Session duration in minutes
        "--scanner-refresh-interval", "300",      # 5 minutes = 300 seconds
        "--max-daily-loss", "3.0",               # 3% max daily loss
        "--position-size", "2.0",                # 2% per position
        "--trailing-stop", "2.0",                # 2% trailing stop
        "--max-positions", "5",                  # Max 5 concurrent positions
        "--client-id", "9"                       # Unique client ID
    ]
    
    if auto_execute:
        cmd.append("--auto-execute")
        print("⚠️  AUTO-EXECUTE ENABLED - Real trades will be placed!")
    else:
        print("📊 Preview mode - No trades will be executed")
    
    print(f"📋 Command: {' '.join(cmd)}")
    
    try:
        # Run the trader - this will run continuously until session ends
        result = subprocess.run(cmd, capture_output=False, text=True)
        
        if result.returncode == 0:
            print("✅ Long session completed successfully")
            return True
        else:
            print(f"❌ Long session failed with return code: {result.returncode}")
            return False
            
    except KeyboardInterrupt:
        print("\n⏹️  Long session interrupted by user")
        return True
    except Exception as e:
        print(f"❌ Error running long session: {e}")
        return False

def find_latest_scanner_file():
    """Find the most recent scanner results file"""
    results_folder = "scanner_results"
    
    if not os.path.exists(results_folder):
        print(f"📁 Scanner results folder '{results_folder}' not found")
        return None
    
    files = [f for f in os.listdir(results_folder) if f.startswith('scanner_results_') and f.endswith('.json')]
    if not files:
        print(f"📁 No scanner result files found in '{results_folder}' folder")
        return None
    
    # Sort by modification time (newest first)
    files.sort(key=lambda x: os.path.getmtime(os.path.join(results_folder, x)), reverse=True)
    latest_file = files[0]
    
    return os.path.join(results_folder, latest_file)

def calculate_session_duration():
    """Calculate optimal session duration based on current time"""
    now = datetime.now()
    
    # US Eastern Time market hours: 9:30 AM - 4:00 PM ET
    # For simplicity, we'll use a standard 6.5 hour session
    # You can adjust this based on your timezone and preferences
    
    # If it's before 9:30 AM ET, run until 4:00 PM ET (6.5 hours)
    # If it's after 9:30 AM ET, run until 4:00 PM ET (remaining time)
    
    # For now, use standard 6.5 hours (390 minutes)
    return 390

def main():
    parser = argparse.ArgumentParser(description="Run Long Session Auto Trader")
    
    parser.add_argument("--auto-execute", action="store_true",
                       help="Enable auto-execute (real trades)")
    parser.add_argument("--session-duration", type=int, default=390,
                       help="Session duration in minutes (default: 390 = 6.5 hours)")
    parser.add_argument("--skip-initial-scan", action="store_true",
                       help="Skip initial scanner run (use existing results)")
    parser.add_argument("--scanner-file", type=str, default="",
                       help="Specific scanner file to use (leave empty for latest)")
    
    args = parser.parse_args()
    
    print("🤖 LONG SESSION AUTO DAY TRADING SYSTEM")
    print("=" * 60)
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Session Duration: {args.session_duration} minutes")
    print(f"Scanner Refresh: Every 5 minutes")
    print(f"Auto Execute: {'ENABLED' if args.auto_execute else 'DISABLED'}")
    print("=" * 60)
    
    # Step 1: Run initial scanner (unless skipped)
    if not args.skip_initial_scan:
        if not run_scanner_first():
            print("⚠️  Initial scanner failed, but proceeding with existing results...")
    else:
        print("⏭️  Skipping initial scanner scan")
    
    # Step 2: Find scanner results file
    scanner_file = args.scanner_file
    if not scanner_file:
        scanner_file = find_latest_scanner_file()
        if not scanner_file:
            print("❌ No scanner results file found")
            return
    
    print(f"📁 Using scanner results: {scanner_file}")
    
    # Step 3: Confirm settings if auto-execute is enabled
    if args.auto_execute:
        print("\n⚠️  AUTO-EXECUTE ENABLED - Real trades will be placed!")
        confirm = input("Are you sure you want to execute real trades? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("❌ Auto-execute cancelled")
            return
    else:
        print("\n📊 Preview mode - No trades will be executed")
        print("Add --auto-execute flag to enable real trading")
    
    # Step 4: Run the long session trader
    print(f"\n🚀 Starting long session...")
    print(f"   This will run continuously for {args.session_duration} minutes")
    print(f"   Scanner will refresh every 5 minutes")
    print(f"   Press Ctrl+C to stop early")
    print("=" * 60)
    
    success = run_long_session_trader(scanner_file, args.auto_execute, args.session_duration)
    
    if success:
        print("✅ Long session completed successfully")
    else:
        print("❌ Long session encountered an error")

if __name__ == "__main__":
    main()
