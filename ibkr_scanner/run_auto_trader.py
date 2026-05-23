#!/usr/bin/env python3
"""
RUN AUTO TRADER - Example script for running the automated day trading system
"""

import subprocess
import sys
import os

def run_scanner():
    """Run the scanner to generate results"""
    print("🔍 Running Scanner...")
    cmd = [
        "python", "technical_scanner.py",
        "--preset", "day_trading",
        "--interval", "5min",
        "--max-results", "10",
        "--min-score", "70",
        "--client-id", "8"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Scanner completed successfully")
            return True
        else:
            print(f"❌ Scanner failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error running scanner: {e}")
        return False

def run_auto_trader(scanner_file, auto_execute=False):
    """Run the auto-trader with scanner results"""
    print(f"🚀 Running Auto Trader...")
    
    cmd = [
        "python", "auto_day_trader.py",
        "--scanner-file", scanner_file,
        "--max-daily-loss", "3.0",      # 3% max daily loss
        "--position-size", "2.0",       # 2% per position
        "--trailing-stop", "2.0",       # 2% trailing stop
        "--max-positions", "5",         # Max 5 concurrent positions
        "--client-id", "9"              # Different client ID
    ]
    
    if auto_execute:
        cmd.append("--auto-execute")
        print("⚠️  AUTO-EXECUTE ENABLED - Real trades will be placed!")
    else:
        print("📊 Preview mode - No trades will be executed")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Auto trader completed successfully")
            return True
        else:
            print(f"❌ Auto trader failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error running auto trader: {e}")
        return False

def find_latest_scanner_file():
    """Find the most recent scanner results file"""
    results_folder = "scanner_results"
    
    # Check if the folder exists
    if not os.path.exists(results_folder):
        print(f"📁 Scanner results folder '{results_folder}' not found")
        return None
    
    # Look for scanner result files in the folder
    files = [f for f in os.listdir(results_folder) if f.startswith('scanner_results_') and f.endswith('.json')]
    if not files:
        print(f"📁 No scanner result files found in '{results_folder}' folder")
        return None
    
    # Sort by modification time (newest first)
    files.sort(key=lambda x: os.path.getmtime(os.path.join(results_folder, x)), reverse=True)
    latest_file = files[0]
    
    # Return the full path to the file
    return os.path.join(results_folder, latest_file)

def main():
    print("🤖 AUTO DAY TRADING SYSTEM")
    print("=" * 50)
    
    # Step 1: Run scanner
    if not run_scanner():
        print("❌ Cannot proceed without scanner results")
        return
    
    # Step 2: Find scanner results file
    scanner_file = find_latest_scanner_file()
    if not scanner_file:
        print("❌ No scanner results file found")
        return
    
    print(f"📁 Found scanner results: {scanner_file}")
    
    # Step 3: Ask user about auto-execute
    print("\n🤔 Do you want to:")
    print("1. Preview trades only (safe)")
    print("2. Execute trades automatically (real money)")
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "2":
        confirm = input("⚠️  Are you sure you want to execute real trades? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("❌ Auto-execute cancelled")
            return
        auto_execute = True
    else:
        auto_execute = False
    
    # Step 4: Run auto-trader
    run_auto_trader(scanner_file, auto_execute)

if __name__ == "__main__":
    main()
