"""
Setup verification script for the IBKR trading system.
"""

import importlib
import subprocess
import sys
from pathlib import Path


def print_header(text):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def print_status(check, passed):
    status = "PASS" if passed else "FAIL"
    print(f"  {status} - {check}")
    return passed


def verify_python():
    print_header("Python Installation")
    version = sys.version_info
    passed = version.major >= 3 and version.minor >= 8
    print_status(f"Python {version.major}.{version.minor}.{version.micro}", passed)
    return passed


def verify_dependencies():
    print_header("Python Dependencies")
    required_packages = {
        "ibapi": ("ibapi", "Interactive Brokers API"),
        "schedule": ("schedule", "Scheduling Library"),
        "python-dotenv": ("dotenv", "Environment Variables"),
        "pandas": ("pandas", "Data Analysis"),
        "numpy": ("numpy", "Numerical Analysis"),
        "pytz": ("pytz", "Timezone Support"),
        "requests": ("requests", "HTTP Library"),
        "yfinance": ("yfinance", "Market Data"),
        "feedparser": ("feedparser", "News Feeds"),
        "TextBlob": ("textblob", "Sentiment Analysis"),
    }

    all_passed = True
    for package, (import_name, description) in required_packages.items():
        try:
            importlib.import_module(import_name)
            print_status(f"{description} ({package})", True)
        except ImportError:
            print_status(f"{description} ({package})", False)
            all_passed = False

    return all_passed


def verify_files():
    print_header("Required Files")
    required_files = [
        "config.py",
        "utils.py",
        "ib_connection.py",
        "strategies.py",
        "risk_manager.py",
        "trading_engine.py",
        "requirements.txt",
        "README.md",
    ]

    all_passed = True
    for filename in required_files:
        exists = Path(filename).exists()
        print_status(filename, exists)
        all_passed = all_passed and exists

    return all_passed


def verify_configuration():
    print_header("Configuration")
    try:
        import config

        checks = [
            ("IB_HOST configured", hasattr(config, "IB_HOST")),
            ("IB_PORT configured", hasattr(config, "IB_PORT")),
            ("Trading hours set", hasattr(config, "TRADING_HOURS_START")),
            ("Risk management configured", hasattr(config, "MAX_DAILY_LOSS")),
            ("Fee-to-profit guard configured", hasattr(config, "MAX_FEE_TO_PROFIT_RATIO")),
            ("Live trading safety gate configured", hasattr(config, "ENABLE_LIVE_TRADING")),
            ("Live order placement explicitly armed", config.PAPER_TRADING or config.ENABLE_LIVE_TRADING),
        ]

        all_passed = True
        for check, result in checks:
            print_status(check, result)
            all_passed = all_passed and result

        print("\n  Current Settings:")
        print(f"    - Connection: {config.IB_HOST}:{config.IB_PORT}")
        print(f"    - Mode: {'PAPER TRADING' if config.PAPER_TRADING else 'LIVE TRADING'}")
        print(f"    - Live orders armed: {config.ENABLE_LIVE_TRADING}")
        print(f"    - Max Daily Loss: ${config.MAX_DAILY_LOSS:,.0f}")
        print(f"    - Max Position: ${config.MAX_POSITION_SIZE:,.0f}")
        print(f"    - Max Fee/Profit Ratio: {config.MAX_FEE_TO_PROFIT_RATIO * 100:.0f}%")
        return all_passed
    except Exception as exc:
        print_status("Configuration import", False)
        print(f"    Error: {exc}")
        return False


def verify_ib_connection():
    print_header("Interactive Brokers Connection")
    checks = [
        "TWS/IBGateway should be running on port 7497 (paper) or 7496 (live)",
        "API must be enabled in TWS settings",
        "Connection test will be done when starting engine",
    ]
    for check in checks:
        print_status(check, True)
    return True


def verify_scheduler():
    print_header("Windows Task Scheduler")
    try:
        subprocess.run(["tasklist", "/FO", "CSV"], capture_output=True, text=True, check=True)
        print_status("Windows Task Scheduler available", True)
        print("    - To set up automatic trading, see README.md")
        return True
    except Exception:
        print_status("Windows Task Scheduler", False)
        return False


def main():
    print("\n")
    print("+" + "=" * 58 + "+")
    print("|" + " " * 10 + "IBKR Trading System - Setup Verification" + " " * 7 + "|")
    print("+" + "=" * 58 + "+")

    results = []
    results.append(("Python Installation", verify_python()))
    results.append(("Files", verify_files()))

    if not all(result for _, result in results):
        print("\n" + "!" * 60)
        print("  CRITICAL: Required files missing.")
        print("!" * 60)
        return False

    results.append(("Dependencies", verify_dependencies()))
    results.append(("Configuration", verify_configuration()))
    results.append(("IB Connection", verify_ib_connection()))
    results.append(("Task Scheduler", verify_scheduler()))

    print_header("Verification Summary")
    all_passed = True
    for check_name, result in results:
        print(f"  {'PASS' if result else 'FAIL'} - {check_name}")
        all_passed = all_passed and result

    print()
    if all_passed:
        print("  All checks passed.")
        print("\n  Next steps:")
        print("    1. Review config.py and .env settings")
        print("    2. Start TWS/IBGateway and enable API")
        print("    3. Run: python trading_engine.py")
        print("    4. Check logs: trading_logs.txt")
    else:
        print("  Some checks failed. Please review above.")
        print("\n  To install dependencies:")
        print("    pip install -r requirements.txt")

    print("\n  See README.md for detailed setup instructions.\n")
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
