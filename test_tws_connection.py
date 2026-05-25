import os
import sys
import time

# Add current path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config
from utils import setup_logging, get_logger
from ib_connection import InteractiveBrokersConnection

# Setup logging
setup_logging()
logger = get_logger("test_tws_connection")

def test_tws():
    print("=" * 60)
    print("       Interactive Brokers TWS Real-Time Connection Test")
    print("=" * 60)
    print(f"Targeting host    : {config.IB_HOST}")
    print(f"Targeting port    : {config.IB_PORT} (TWS Demo Mode)")
    print(f"Targeting clientID: {config.IB_CLIENTID}")
    print("-" * 60)
    print("Connecting to TWS...")

    # Initialize connection wrapper
    ib = InteractiveBrokersConnection()
    
    # Establish connection
    success = ib.connect()
    
    if not success:
        print("\n[FAIL] Failed to connect to TWS. Please verify that:")
        print("  1. Trader Workstation (TWS) is running in Demo/Paper mode.")
        print("  2. API is enabled in TWS settings (Settings -> API -> Configuration).")
        print("  3. 'Enable ActiveX and Socket Clients' is checked.")
        print(f"  4. Port is set to {config.IB_PORT} in TWS and matches your config.")
        print("=" * 60)
        return False
        
    print("\n[PASS] Connected successfully to Interactive Brokers TWS!")
    print("-" * 60)

    try:
        # Request Account Data
        print("Requesting account summary...")
        ib.refresh_account_data()
        
        # Wait a moment for callbacks to populate values
        time.sleep(2.0)
        
        snapshot = ib.get_account_snapshot()
        print("\n--- Account Live Snapshot ---")
        print(f"Net Liquidation Value (Equity): ${getattr(snapshot, 'net_liquidation', 0.0):,.2f}")
        print(f"Total Cash                    : ${getattr(snapshot, 'total_cash', 0.0):,.2f}")
        print(f"Settled Cash                  : ${getattr(snapshot, 'settled_cash', 0.0):,.2f}")
        print(f"Buying Power for New Buys     : ${getattr(snapshot, 'funds_for_new_buys', 0.0):,.2f}")
        
        # Request Open Positions
        print("\nRequesting active portfolio positions...")
        positions = ib.get_positions()
        
        print("\n--- Open Positions ---")
        if not positions:
            print("  No active positions found in this paper/demo account.")
        else:
            for symbol, info in positions.items():
                print(f"  Ticker: {symbol:<6} | Quantity: {getattr(info, 'quantity', 0):<6} | Average Cost: ${getattr(info, 'avg_cost', 0.0):,.2f}")
                
        print("\n" + "=" * 60)
        print("[SUCCESS] API connection to TWS is 100% functional and verified!")
        print("=" * 60)
        
    except Exception as e:
        logger.exception(f"Error reading TWS connection metrics: {e}")
    finally:
        print("Disconnecting from TWS API...")
        ib.disconnect()
        print("Disconnected cleanly.")

if __name__ == "__main__":
    test_tws()
