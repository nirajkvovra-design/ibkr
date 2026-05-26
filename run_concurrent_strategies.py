"""
Quantitative Multi-Strategy Concurrent Testing Orchestrator
Launches all six quantitative strategies in parallel processes with isolated state files, 
logs, alert channels, and client IDs to TWS paper trading (Port 7497).
Streams high-visibility transaction logs (buy/sell orders, fills, and errors) directly
to the central orchestrator console in real-time.
"""

import os
import subprocess
import sys
import threading
import time

# Defined quantitative strategies with isolated client IDs and file configurations
STRATEGIES = {
    "MOMENTUM": {"client_id": 11, "suffix": "momentum", "name": "Momentum Technical indicator"},
    "ML": {"client_id": 12, "suffix": "ml", "name": "Machine Learning Forecast"},
    "PAIRS": {"client_id": 13, "suffix": "pairs", "name": "Statistical Arbitrage Pairs"},
    "BREAKOUT": {"client_id": 14, "suffix": "breakout", "name": "Volatility Breakout Channel"},
    "IPO": {"client_id": 15, "suffix": "ipo", "name": "IPO Base Breakout Chart"},
    "LAGGER": {"client_id": 16, "suffix": "lagger", "name": "Correlated Sector Laggard"},
}

def log_reader(strategy_name, process):
    """
    Reads process stdout in real-time, filtering and forwarding critical trade actions
    directly to the centralized orchestrator console stream.
    """
    for line in iter(process.stdout.readline, ''):
        line = line.strip()
        if not line:
            continue
        
        # Keywords that indicate critical trade operations
        keywords = [
            "[TRANSACTION SUBMITTED]",
            "[TRADE FILLED]",
            "[ORDER CANCELLED]",
            "LOCKDOWN",
            "Kill Switch",
            "MISMATCH",
            "emergency_flatten",
            "Error",
            "FAIL",
            "Connected to account"
        ]
        
        if any(kw in line for kw in keywords):
            # Select color based on trade action
            color = "\033[96m"  # Cyan default
            if "[TRADE FILLED]" in line:
                color = "\033[92;1m"  # Bold Green
            elif "[TRANSACTION SUBMITTED]" in line:
                color = "\033[95;1m"  # Bold Magenta
            elif "LOCKDOWN" in line or "Kill Switch" in line or "MISMATCH" in line or "FAIL" in line or "Error" in line:
                color = "\033[91;1m"  # Bold Red
            elif "[ORDER CANCELLED]" in line:
                color = "\033[90;1m"  # Bold Grey
                
            # Log message to central terminal with strategy prefix
            print(f"{color}[{strategy_name}] {line}\033[0m")
            sys.stdout.flush()
            
    process.stdout.close()

def main():
    # Configure console standard output to handle UTF-8 on Windows
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print("======================================================================")
    print("   CONCURRENT MULTI-STRATEGY QUANTITATIVE TESTING ENGINE")
    print("======================================================================")
    print("Starting all 6 strategies on TWS Paper Port 7497...")
    print("Each strategy executes inside an isolated OS process with dedicated")
    print("client sockets, states, logs, and trading journals.")
    print("======================================================================")
    
    # Prompt user for safety gate stage
    print("\nSelect the Safety Gate Stage for all strategies:")
    print("  [1] Shadow Mode (SHADOW) - Telemetry logging, zero orders [Default]")
    print("  [2] Micro Sizing (MICRO) - Actual fills truncated to exactly 1 share")
    print("  [3] Limited Sizing (LIMITED) - Caps exposure at 5% of net equity")
    print("  [4] Full Execution (FULL) - Unrestricted paper executions")
    
    try:
        stage_choice = input("Enter selection [1-4, default=1]: ").strip()
    except (KeyboardInterrupt, EOFError):
        stage_choice = "1"
        
    trading_stage = "SHADOW"
    if stage_choice == "2":
        trading_stage = "MICRO"
    elif stage_choice == "3":
        trading_stage = "LIMITED"
    elif stage_choice == "4":
        trading_stage = "FULL"
        
    print(f"\n[Orchestrator] Launching all strategies in Stage: {trading_stage}")
    print("[Orchestrator] Live transaction stream is now ACTIVE in this console.")
    print("======================================================================\n")
    
    processes = []
    
    try:
        for name, cfg in STRATEGIES.items():
            print(f" -> Launching {name} ({cfg['name']}) on Client ID {cfg['client_id']}...")
            sys.stdout.flush()
            
            # Form custom environment block to isolate files & credentials
            env = {
                "SELECTED_STRATEGY": name,
                "IB_CLIENTID": str(cfg["client_id"]),
                "IB_PORT": "7497",
                "PAPER_TRADING": "True",
                "ENABLE_LIVE_TRADING": "False",
                "TRADING_STAGE": trading_stage,
                "LOG_FILE": f"trading_logs_{cfg['suffix']}.txt",
                "ALERT_FILE": f"trading_alerts_{cfg['suffix']}.log",
                "HEALTH_STATUS_FILE": f"trading_health_{cfg['suffix']}.json",
                "PAPER_JOURNAL_FILE": f"paper_trading_journal_{cfg['suffix']}.jsonl",
                "PAPER_DAILY_PNL_FILE": f"daily_pnl_{cfg['suffix']}.csv",
                "PAPER_TRADE_HISTORY_FILE": f"trade_history_{cfg['suffix']}.csv",
                "ENGINE_PID_FILE": f".trading_engine_{cfg['suffix']}.pid",
                "ENGINE_RESTART_FILE": f".trading_engine_{cfg['suffix']}.restart",
                "STATE_CACHE_FILE": f".state_cache_{cfg['suffix']}.json",
                "DAILY_POSITIONS_FILE": f"daily_positions_{cfg['suffix']}.json",
            }
            
            # Copy parent environment
            full_env = {**dict(os.environ), **env}
            
            # Start process with piped standard streams
            p = subprocess.Popen(
                [sys.executable, "trading_launcher.py"],
                env=full_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Spin up daemon log tailer thread for this process
            t = threading.Thread(target=log_reader, args=(name, p), daemon=True)
            t.start()
            
            processes.append((name, p))
            time.sleep(1.5) # Guard socket bindings frequency in TWS API
            
        print("\n======================================================================")
        print(" SUCCESS: All 6 quantitative strategies are active!")
        print("======================================================================")
        print("Log files generated:")
        for name, cfg in STRATEGIES.items():
            print(f"  - {name}: trading_logs_{cfg['suffix']}.txt")
        print("----------------------------------------------------------------------")
        print("Keep Interactive Brokers TWS or IB Gateway open on port 7497.")
        print("Hold Ctrl+C to terminate all 6 strategies and clean up.")
        print("======================================================================\n")
        
        while True:
            # Check if processes are alive
            for name, p in processes:
                if p.poll() is not None:
                    print(f"\033[91m[Warning] Strategy daemon {name} exited prematurely with code {p.returncode}\033[0m")
                    sys.stdout.flush()
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n[Orchestrator] Interrupted. Shutting down all strategy daemons...")
    finally:
        # Graceful cleanup of all processes
        for name, p in processes:
            if p.poll() is None:
                print(f" -> Terminating {name} (PID: {p.pid})...")
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f" -> Killing {name} (PID: {p.pid})...")
                    p.kill()
        print("\n======================================================================")
        print(" All strategy processes successfully cleaned up. System offline.")
        print("======================================================================")

if __name__ == "__main__":
    main()
