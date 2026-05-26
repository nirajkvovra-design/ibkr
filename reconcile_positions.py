"""
Quantitative Positions Reconciliation Utility
Connects to Interactive Brokers TWS Paper Port (7497) and synchronizes
the isolated strategy state caches and daily positions with active TWS holdings.
"""

import json
import os
import sys
from ib_connection import InteractiveBrokersConnection

# Isolated strategy suffixes
SUFFIXES = ["momentum", "ml", "pairs", "breakout", "ipo", "lagger"]

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print("======================================================================")
    print("   QUANTITATIVE POSITION RECONCILIATION & SYNC TOOL")
    print("======================================================================")
    print("Connecting to Interactive Brokers TWS paper trading...")
    
    # Initialize real TWS connection on unique client ID 99 to avoid lock conflicts
    os.environ["IB_CLIENTID"] = "99"
    conn = InteractiveBrokersConnection()
    
    if not conn.connect():
        print("\n[FAIL] Could not connect to TWS API.")
        print("Please verify that:")
        print("  1. Trader Workstation (TWS) is running in Paper mode.")
        print("  2. Socket API is enabled on port 7497.")
        print("======================================================================")
        return

    try:
        print("Connected. Fetching TWS portfolio positions...")
        conn.refresh_account_data()
        positions = conn.get_positions()
        
        print(f"Active TWS positions detected: {list(positions.keys())}")
        
        # Construct unified tracking structures
        open_positions = {}
        starting_positions = {}
        
        for sym, info in positions.items():
            sym = sym.upper()
            # Handle both class object and dict formats safely
            qty = getattr(info, "quantity", 0) if not isinstance(info, dict) else info.get("quantity", 0)
            avg_cost = getattr(info, "avg_cost", 0.0) if not isinstance(info, dict) else info.get("avg_cost", 0.0)
            
            if qty != 0:
                open_positions[sym] = {
                    "quantity": qty,
                    "entry_price": avg_cost,
                    "current_value": round(qty * avg_cost, 2)
                }
                starting_positions[sym] = qty
                print(f"  -> Ticker: {sym:<6} | Quantity: {qty:<6} | Average Cost: ${avg_cost:.2f}")

        # Synchronize all concurrent strategy files
        print("\nReconciling isolated state files...")
        
        from datetime import datetime
        import pytz
        tz = pytz.timezone("America/New_York")
        today = datetime.now(tz).strftime("%Y-%m-%d")

        for suf in SUFFES:
            cache_file = f".state_cache_{suf}.json"
            daily_file = f"daily_positions_{suf}.json"
            
            # 1. Update State Cache File
            state_data = {
                "daily_loss": 0.0,
                "open_positions": open_positions,
                "stop_loss_prices": {},
                "take_profit_prices": {}
            }
            # Maintain existing stops/losses if file is present
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, "r") as f:
                        existing = json.load(f)
                        if isinstance(existing, dict):
                            state_data["daily_loss"] = existing.get("daily_loss", 0.0)
                            state_data["stop_loss_prices"] = existing.get("stop_loss_prices", {})
                            state_data["take_profit_prices"] = existing.get("take_profit_prices", {})
                except Exception:
                    pass
            
            with open(cache_file, "w") as f:
                json.dump(state_data, f, indent=4)
            print(f"  - Synchronized {cache_file}")
            
            # 2. Update Daily Session Positions file
            daily_data = {
                "session_date": today,
                "opens": {},
                "starting_positions": starting_positions
            }
            with open(daily_file, "w") as f:
                json.dump(daily_data, f, indent=2)
            print(f"  - Synchronized {daily_file}")
            
        print("\n======================================================================")
        print(" SUCCESS: All strategy files are synchronized with TWS holdings!")
        print("======================================================================")
        print("You can now safely restart run_concurrent_strategies.bat")
        print("======================================================================")

    except Exception as exc:
        print(f"\n[ERROR] Position reconciliation failed: {exc}")
    finally:
        print("Disconnecting from TWS API...")
        conn.disconnect()

if __name__ == "__main__":
    # Correction for potential typos in SUFFIXES reference
    SUFFES = SUFFIXES
    main()
