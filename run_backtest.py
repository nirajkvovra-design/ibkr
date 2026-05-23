import os
import sys
import argparse
from datetime import datetime, timedelta
import pandas as pd

# Setup local paths
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from backtester import BacktestEngine
from strategies import MomentumStrategy, MachineLearningStrategy
from utils import setup_logging

def parse_args():
    parser = argparse.ArgumentParser(description="Automated Trading Strategy Backtester")
    parser.add_argument(
        "--tickers", 
        type=str, 
        default="INTC,BAC,F", 
        help="Comma-separated list of stock symbols to backtest (e.g. INTC,BAC,F)"
    )
    parser.add_argument(
        "--months", 
        type=int, 
        default=6, 
        help="Number of months of historical backtesting (default: 6)"
    )
    parser.add_argument(
        "--capital", 
        type=float, 
        default=10000.0, 
        help="Starting virtual capital (default: 10000.0)"
    )
    return parser.parse_args()

def main():
    args = parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    
    # Disable standard noisy strategy logs during backtesting to keep output focused
    setup_logging()
    
    # Calculate backtest window
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.months * 30)
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    print("=" * 70)
    print("      Interactive Brokers Automated Strategy Backtester")
    print("=" * 70)
    print(f"Tickers under test : {tickers}")
    print(f"Simulating Period  : {start_str} to {end_str} ({args.months} months)")
    print(f"Starting Capital   : ${args.capital:,.2f}")
    print("=" * 70)
    
    # Initialize Engine
    engine = BacktestEngine(tickers, start_str, end_str, starting_cash=args.capital)
    
    # Pre-load data once to save API requests
    engine.load_data()
    
    results = {}
    
    # 1. Run Momentum Strategy Backtest
    print("\n[Backtesting Strategy 1/2] Running MomentumStrategy...")
    try:
        momentum_res = engine.run(MomentumStrategy)
        if momentum_res:
            results["Momentum Strategy"] = momentum_res
            print(f"Completed! Return: {momentum_res['net_return_pct']:+.2f}% | Trades: {momentum_res['total_trades']}")
    except Exception as e:
        print(f"Error backtesting Momentum Strategy: {e}")
        
    # 2. Run Machine Learning Strategy Backtest (Monte Carlo GBM)
    print("\n[Backtesting Strategy 2/2] Running MachineLearningStrategy (Monte Carlo)...")
    try:
        ml_res = engine.run(MachineLearningStrategy, model_type="MONTE_CARLO")
        if ml_res:
            results["ML Strategy (Monte Carlo)"] = ml_res
            print(f"Completed! Return: {ml_res['net_return_pct']:+.2f}% | Trades: {ml_res['total_trades']}")
    except Exception as e:
        print(f"Error backtesting Machine Learning Strategy: {e}")

    # Output Side-by-Side Comparison
    if not results:
        print("\n[Error] No backtest results generated.")
        return
        
    print("\n" + "=" * 80)
    print("                         STRATEGY SIMULATION COMPARISON")
    print("=" * 80)
    print(f"{'Strategy Metric':<30} | {'Momentum Strategy':<22} | {'ML (Monte Carlo)':<22}")
    print("-" * 80)
    
    metrics_to_print = [
        ("Initial Capital", lambda r: f"${r['initial_capital']:,.2f}"),
        ("Final Capital", lambda r: f"${r['final_capital']:,.2f}"),
        ("Cumulative Return", lambda r: f"{r['net_return_pct']:+.2f}%"),
        ("Sharpe Ratio (Risk-Adj)", lambda r: f"{r['sharpe_ratio']:.2f}"),
        ("Max Drawdown", lambda r: f"{r['max_drawdown_pct']:.2f}%"),
        ("Total Trades Executed", lambda r: f"{r['total_trades']}"),
        ("Trade Win Rate", lambda r: f"{r['win_rate_pct']:.1f}%"),
        ("Total Fees & Commissions", lambda r: f"${r['total_fees']:.2f}")
    ]
    
    for label, formatter in metrics_to_print:
        momentum_val = formatter(results["Momentum Strategy"]) if "Momentum Strategy" in results else "N/A"
        ml_val = formatter(results["ML Strategy (Monte Carlo)"]) if "ML Strategy (Monte Carlo)" in results else "N/A"
        print(f"{label:<30} | {momentum_val:<22} | {ml_val:<22}")
        
    print("=" * 80)
    
    # Executive Summary / Recommendations
    print("\n--- Executive Recommendations ---")
    if "Momentum Strategy" in results and "ML Strategy (Monte Carlo)" in results:
        ret_mom = results["Momentum Strategy"]["net_return_pct"]
        ret_ml = results["ML Strategy (Monte Carlo)"]["net_return_pct"]
        sharpe_mom = results["Momentum Strategy"]["sharpe_ratio"]
        sharpe_ml = results["ML Strategy (Monte Carlo)"]["sharpe_ratio"]
        
        if ret_ml > ret_mom:
            print(f"🏆 The **Machine Learning Strategy** outperformed Momentum by **{ret_ml - ret_mom:+.2f}%** return.")
            if sharpe_ml > sharpe_mom:
                print(f"💡 It also achieved a superior Sharpe Ratio of **{sharpe_ml:.2f}** (vs {sharpe_mom:.2f}), offering better risk-adjusted returns.")
        else:
            print(f"🏆 The **Momentum Strategy** outperformed Machine Learning by **{ret_mom - ret_ml:+.2f}%** return.")
            if sharpe_mom > sharpe_ml:
                print(f"💡 It also achieved a superior Sharpe Ratio of **{sharpe_mom:.2f}** (vs {sharpe_ml:.2f}), offering better risk-adjusted returns.")
                
        dd_mom = results["Momentum Strategy"]["max_drawdown_pct"]
        dd_ml = results["ML Strategy (Monte Carlo)"]["max_drawdown_pct"]
        if abs(dd_ml) < abs(dd_mom):
            print(f"🛡️ The **Machine Learning Strategy** demonstrated better downside risk control, with a maximum drawdown of only **{dd_ml:.2f}%** (vs {dd_mom:.2f}%).")
        else:
            print(f"🛡️ The **Momentum Strategy** demonstrated better downside risk control, with a maximum drawdown of only **{dd_mom:.2f}%** (vs {dd_ml:.2f}%).")
            
    print("=" * 80)

if __name__ == "__main__":
    main()
