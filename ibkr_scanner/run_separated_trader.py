#!/usr/bin/env python3
"""
RUN SEPARATED TRADER - Properly separated scanner and auto trader execution
This script ensures the scanner runs first in a separate process, then the auto trader
runs with the fresh results, avoiding any IB connection conflicts.

USAGE:
    python run_separated_trader.py [options]

EXAMPLES:
    # Preview mode (safe)
    python run_separated_trader.py
    
    # Auto-execute trades (real money)
    python run_separated_trader.py --auto-execute
    
    # Continuous session with monitoring
    python run_separated_trader.py --auto-execute --continuous-session
"""

import subprocess
import sys
import os
import time
import json
import argparse
from datetime import datetime

# Safe print function that handles Unicode characters
def safe_print(text):
    """Print text safely, handling any Unicode characters"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback: encode to ASCII with replacement
        safe_text = text.encode('ascii', 'replace').decode('ascii')
        print(safe_text)

def run_scanner_separately():
    """Run the scanner in a completely separate process to avoid IB conflicts"""
    safe_print("STEP 1: Running Technical Scanner...")
    safe_print("   Scanner runs in separate process to avoid IB connection conflicts")
    
    # Scanner command with day trading optimized settings
    scanner_cmd = [
        sys.executable, 'technical_scanner.py',
        '--interval', '5min',           # 5-minute bars for day trading
        '--min-score', '70',            # Higher score threshold for auto-trading
        '--max-results', '15',          # Limit results for faster processing
        '--macd-fast', '5',             # Fast MACD for day trading
        '--macd-slow', '13',            # Fast MACD for day trading
        '--macd-signal', '4',           # Fast signal line
        '--rsi-period', '9',            # Shorter RSI for responsiveness
        '--adx-threshold', '30',        # Strong trend requirement
        '--min-price', '5.0',           # Minimum price filter
        '--scan-code', 'MOST_ACTIVE',   # Focus on active stocks
        '--client-id', '8'              # Use different client ID to avoid conflicts
    ]
    
    safe_print(f"   Scanner command: {' '.join(scanner_cmd)}")
    safe_print("   Starting scanner in separate process...")
    
    try:
        # Start scanner process with output redirected to files to avoid Unicode issues
        start_time = time.time()
        
        # Create temporary output files
        stdout_file = "scanner_stdout.tmp"
        stderr_file = "scanner_stderr.tmp"
        
        scanner_process = subprocess.Popen(
            scanner_cmd,
            stdout=open(stdout_file, 'w', encoding='utf-8', errors='replace'),
            stderr=open(stderr_file, 'w', encoding='utf-8', errors='replace'),
            cwd=os.path.dirname(os.path.abspath(__file__))  # Ensure correct working directory
        )
        
        # Monitor scanner progress
        safe_print("   Monitoring scanner progress...")
        scanner_output = ""
        scanner_error = ""
        
        # Wait for scanner to complete with timeout
        try:
            scanner_process.wait(timeout=300)  # 5 minute timeout
            
            # Read output files safely
            scanner_output = ""
            scanner_error = ""
            
            try:
                with open(stdout_file, 'r', encoding='utf-8', errors='replace') as f:
                    scanner_output = f.read()
            except Exception as e:
                safe_print(f"   Warning: Could not read stdout file: {e}")
            
            try:
                with open(stderr_file, 'r', encoding='utf-8', errors='replace') as f:
                    scanner_error = f.read()
            except Exception as e:
                safe_print(f"   Warning: Could not read stderr file: {e}")
            
            # Clean up temporary files
            try:
                os.remove(stdout_file)
                os.remove(stderr_file)
            except Exception as e:
                safe_print(f"   Warning: Could not remove temp files: {e}")
            
            if scanner_process.returncode == 0:
                safe_print("   Scanner completed successfully")
                if scanner_output:
                    safe_print("   Scanner output preview:")
                    lines = scanner_output.strip().split('\n')
                    for line in lines[-5:]:  # Show last 5 lines
                        if line.strip():
                            # Clean any remaining problematic characters
                            clean_line = line.encode('ascii', 'replace').decode('ascii')
                            safe_print(f"      {clean_line}")
                return True
            else:
                safe_print(f"   Scanner failed with return code {scanner_process.returncode}")
                if scanner_error:
                    safe_print("   Scanner errors:")
                    lines = scanner_error.strip().split('\n')
                    for line in lines[-5:]:  # Show last 5 error lines
                        if line.strip():
                            # Clean any remaining problematic characters
                            clean_line = line.encode('ascii', 'replace').decode('ascii')
                            safe_print(f"      {clean_line}")
                return False
                
        except subprocess.TimeoutExpired:
            safe_print("   Scanner timed out after 5 minutes - terminating process")
            scanner_process.terminate()
            try:
                scanner_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                scanner_process.kill()
            safe_print("   Scanner process terminated")
            return False
            
    except Exception as e:
        safe_print(f"   Error starting scanner: {e}")
        return False

def find_latest_scanner_results():
    """Find the most recent scanner results file"""
    print("   Looking for scanner results...")
    
    scanner_dir = "scanner_results"
    if not os.path.exists(scanner_dir):
        print(f"   Scanner results directory '{scanner_dir}' not found")
        return None
    
    # Get all scanner result files
    files = [f for f in os.listdir(scanner_dir) 
             if f.startswith('scanner_results_') and f.endswith('.json')]
    
    if not files:
        print(f"   No scanner result files found")
        return None
    
    # Sort by modification time (newest first)
    files.sort(key=lambda x: os.path.getmtime(os.path.join(scanner_dir, x)), reverse=True)
    latest_file = os.path.join(scanner_dir, files[0])
    
    # Check if file is recent (within last 10 minutes)
    file_mtime = os.path.getmtime(latest_file)
    time_since_scan = time.time() - file_mtime
    
    if time_since_scan < 600:  # 10 minutes
        print(f"   Found recent results: {os.path.basename(latest_file)} ({int(time_since_scan)} seconds old)")
        return latest_file
    else:
        print(f"   Results are old: {os.path.basename(latest_file)} ({int(time_since_scan)} seconds old)")
        return latest_file

def load_scanner_results(file_path):
    """Load and validate scanner results"""
    print(f"   Loading results from: {os.path.basename(file_path)}")
    
    try:
        with open(file_path, 'r') as f:
            results = json.load(f)
        
        # Validate results format
        if 'long' in results and 'short' in results:
            long_count = len(results.get('long', []))
            short_count = len(results.get('short', []))
            
            print(f"   Results loaded successfully:")
            print(f"      Long opportunities: {long_count}")
            print(f"      Short opportunities: {short_count}")
            
            if 'timestamp' in results:
                print(f"      Scan timestamp: {results['timestamp']}")
            
            return results
        else:
            print("   Invalid results format - missing 'long' or 'short' keys")
            return None
            
    except Exception as e:
        print(f"   Error loading results: {e}")
        return None

def run_auto_trader(scanner_results, auto_execute=False, continuous_session=False):
    """Run the auto trader with scanner results"""
    print("\nSTEP 2: Running Auto Day Trader...")
    print(f"   Auto trader runs with fresh scanner results")
    print(f"   Processing {len(scanner_results.get('long', []))} long and {len(scanner_results.get('short', []))} short opportunities")
    
    # Auto trader command
    trader_cmd = [
        sys.executable, 'auto_day_trader.py',
        '--max-daily-loss', '3.0',      # 3% max daily loss
        '--position-size', '2.0',       # 2% per position
        '--trailing-stop', '2.0',       # 2% trailing stop
        '--max-positions', '5',         # Max 5 concurrent positions
        '--client-id', '9',             # Different client ID from scanner
        '--scanner-refresh-interval', '300'  # 5 minute scanner refresh
    ]
    
    if auto_execute:
        trader_cmd.append('--auto-execute')
        print("   AUTO-EXECUTE ENABLED - Real trades will be placed!")
    else:
        print("   Preview mode - No trades will be executed")
    
    if continuous_session:
        trader_cmd.append('--continuous-session')
        print("   Continuous session mode - Scanner will refresh every 5 minutes")
    
    print(f"   Trader command: {' '.join(trader_cmd)}")
    print("   Starting auto trader...")
    
    try:
        # Start auto trader process
        trader_process = subprocess.Popen(
            trader_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        # For continuous session, let it run indefinitely
        if continuous_session:
            print("   Continuous session started - Press Ctrl+C to stop")
            try:
                # Monitor output in real-time
                while True:
                    output = trader_process.stdout.readline()
                    if output:
                        try:
                            decoded_output = output.decode('utf-8', errors='replace')
                        except UnicodeDecodeError:
                            decoded_output = output.decode('latin-1', errors='replace')
                        
                        # Clean any remaining problematic characters
                        clean_output = decoded_output.encode('ascii', 'replace').decode('ascii')
                        print(f"   {clean_output.strip()}")
                    else:
                        time.sleep(0.1)
            except KeyboardInterrupt:
                print("\nStopping continuous session...")
                trader_process.terminate()
                try:
                    trader_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    trader_process.kill()
                print("Continuous session stopped")
        else:
            # For single run, wait for completion
            print("   Waiting for auto trader to complete...")
            stdout, stderr = trader_process.communicate(timeout=600)  # 10 minute timeout
            
            if trader_process.returncode == 0:
                print("   Auto trader completed successfully")
                if stdout:
                    print("   Trader output preview:")
                    try:
                        decoded_stdout = stdout.decode('utf-8', errors='replace')
                    except UnicodeDecodeError:
                        decoded_stdout = stdout.decode('latin-1', errors='replace')
                    
                    lines = decoded_stdout.strip().split('\n')
                    for line in lines[-5:]:
                        if line.strip():
                            # Clean any remaining problematic characters
                            clean_line = line.encode('ascii', 'replace').decode('ascii')
                            print(f"      {clean_line}")
                return True
            else:
                print(f"   Auto trader failed with return code {trader_process.returncode}")
                if stderr:
                    print(f"   Trader errors:")
                    try:
                        decoded_stderr = stderr.decode('utf-8', errors='replace')
                    except UnicodeDecodeError:
                        decoded_stderr = stderr.decode('latin-1', errors='replace')
                    
                    lines = decoded_stderr.strip().split('\n')
                    for line in lines[-5:]:
                        if line.strip():
                            # Clean any remaining problematic characters
                            clean_line = line.encode('ascii', 'replace').decode('ascii')
                            print(f"      {clean_line}")
                return False
                
    except Exception as e:
        print(f"   Error running auto trader: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Run Separated Trader - Scanner first, then Auto Trader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
    # Preview mode (safe)
    python run_separated_trader.py
    
    # Auto-execute trades (real money)
    python run_separated_trader.py --auto-execute
    
    # Continuous session with monitoring
    python run_separated_trader.py --auto-execute --continuous-session
    
    # Show scanner status only
    python run_separated_trader.py --show-scanner-status
        """
    )
    
    parser.add_argument("--auto-execute", action="store_true",
                       help="Automatically execute trades (default: preview only)")
    parser.add_argument("--continuous-session", action="store_true",
                       help="Run continuous trading session with scanner refresh")
    parser.add_argument("--show-scanner-status", action="store_true",
                       help="Show current scanner status and exit")
    
    args = parser.parse_args()
    
    print("SEPARATED TRADER SYSTEM")
    print("=" * 60)
    print("This system ensures proper separation between scanner and auto trader")
    print("to avoid IB connection conflicts and ensure fresh data.")
    print("=" * 60)
    
    # Handle scanner status check
    if args.show_scanner_status:
        print("Scanner Status Check")
        print("=" * 50)
        
        # Create a minimal trader instance just for status check
        try:
            from auto_day_trader import AutoDayTrader
            trader = AutoDayTrader()
            scanner_status = trader.get_scanner_status()
            
            print(f"Status: {scanner_status.get('status', 'Unknown')}")
            if scanner_status.get('status') == 'Active':
                print(f"Last Scan: {scanner_status.get('last_scan', 'Unknown')}")
                print(f"Time Since: {scanner_status.get('time_since_scan', 'Unknown')}")
                print(f"Total Files: {scanner_status.get('total_files', 0)}")
                print(f"Latest Results: {scanner_status.get('latest_results', {}).get('long_count', 0)} long, {scanner_status.get('latest_results', {}).get('short_count', 0)} short")
                
                if scanner_status.get('scanner_settings'):
                    settings = scanner_status['scanner_settings']
                    print(f"Scanner Settings:")
                    print(f"  Interval: {settings.get('interval', 'Unknown')}")
                    print(f"  Min Score: {settings.get('min_score', 'Unknown')}")
                    print(f"  Max Results: {settings.get('max_results', 'Unknown')}")
            else:
                print(f"Error: {scanner_status.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"Error checking scanner status: {e}")
        return
    
    # Step 1: Run scanner separately
    if not run_scanner_separately():
        print("Scanner failed - cannot proceed")
        return
    
    # Step 2: Find and load scanner results
    print("\nSTEP 1.5: Loading Scanner Results...")
    scanner_file = find_latest_scanner_results()
    if not scanner_file:
        print("No scanner results found - cannot proceed")
        return
    
    scanner_results = load_scanner_results(scanner_file)
    if not scanner_results:
        print("Failed to load scanner results - cannot proceed")
        return
    
    # Step 3: Run auto trader
    if not run_auto_trader(scanner_results, args.auto_execute, args.continuous_session):
        print("Auto trader failed")
        return
    
    print("\nSEPARATED TRADER SYSTEM COMPLETED SUCCESSFULLY")
    print("=" * 60)
    print("The scanner and auto trader ran in separate processes")
    print("to avoid IB connection conflicts and ensure fresh data.")

if __name__ == "__main__":
    main()
