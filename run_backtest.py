import os
import sys
import argparse
from datetime import datetime, timedelta
import pandas as pd

# Setup local paths
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from backtester import BacktestEngine
from strategies import MomentumStrategy, MachineLearningStrategy, VolatilityBreakoutStrategy, PairsTradingStrategy
from utils import setup_logging

def parse_args():
    parser = argparse.ArgumentParser(description="Automated Trading Strategy Backtester")
    parser.add_argument(
        "--tickers", 
        type=str, 
        default="INTC,BAC,F,V,MA,KO,PEP", 
        help="Comma-separated list of stock symbols to backtest"
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
    
    print("=" * 100)
    print("                      Interactive Brokers Automated Strategy Backtester")
    print("=" * 100)
    print(f"Tickers under test : {tickers}")
    print(f"Simulating Period  : {start_str} to {end_str} ({args.months} months)")
    print(f"Starting Capital   : ${args.capital:,.2f}")
    print("=" * 100)
    
    # Initialize Engine
    engine = BacktestEngine(tickers, start_str, end_str, starting_cash=args.capital)
    
    # Pre-load data once to save API requests
    engine.load_data()
    
    results = {}
    
    # 1. Run Momentum Strategy Backtest
    print("\n[Backtesting 1/4] Running MomentumStrategy...")
    try:
        momentum_res = engine.run(MomentumStrategy)
        if momentum_res:
            results["Momentum"] = momentum_res
            print(f"Completed! Return: {momentum_res['net_return_pct']:+.2f}% | Trades: {momentum_res['total_trades']}")
    except Exception as e:
        print(f"Error backtesting Momentum Strategy: {e}")
        
    # 2. Run Machine Learning Strategy Backtest (Monte Carlo GBM)
    print("\n[Backtesting 2/4] Running MachineLearningStrategy (Monte Carlo)...")
    try:
        ml_res = engine.run(MachineLearningStrategy, model_type="MONTE_CARLO")
        if ml_res:
            results["Machine Learning"] = ml_res
            print(f"Completed! Return: {ml_res['net_return_pct']:+.2f}% | Trades: {ml_res['total_trades']}")
    except Exception as e:
        print(f"Error backtesting Machine Learning Strategy: {e}")

    # 3. Run Volatility Breakout Strategy Backtest
    print("\n[Backtesting 3/4] Running VolatilityBreakoutStrategy...")
    try:
        breakout_res = engine.run(VolatilityBreakoutStrategy)
        if breakout_res:
            results["Vol Breakout"] = breakout_res
            print(f"Completed! Return: {breakout_res['net_return_pct']:+.2f}% | Trades: {breakout_res['total_trades']}")
    except Exception as e:
        print(f"Error backtesting Volatility Breakout Strategy: {e}")

    # 4. Run Pairs Trading Strategy Backtest
    print("\n[Backtesting 4/4] Running PairsTradingStrategy (Statistical Arbitrage)...")
    try:
        pairs_res = engine.run(PairsTradingStrategy)
        if pairs_res:
            results["Pairs Trading"] = pairs_res
            print(f"Completed! Return: {pairs_res['net_return_pct']:+.2f}% | Trades: {pairs_res['total_trades']}")
    except Exception as e:
        print(f"Error backtesting Pairs Trading Strategy: {e}")

    # Output Side-by-Side Comparison
    if not results:
        print("\n[Error] No backtest results generated.")
        return
        
    print("\n" + "=" * 115)
    print("                                      STRATEGY SIMULATION COMPARISON")
    print("=" * 115)
    print(f"{'Strategy Metric':<30} | {'Momentum':<18} | {'Machine Learning':<18} | {'Vol Breakout':<18} | {'Pairs Trading':<18}")
    print("-" * 115)
    
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
        vals = []
        for strat in ["Momentum", "Machine Learning", "Vol Breakout", "Pairs Trading"]:
            val = formatter(results[strat]) if strat in results else "N/A"
            vals.append(val)
        print(f"{label:<30} | {vals[0]:<18} | {vals[1]:<18} | {vals[2]:<18} | {vals[3]:<18}")
        
    print("=" * 115)
    
    # Executive Recommendations
    print("\n--- Executive Summary & Recommendations ---")
    active_strats = [s for s in ["Momentum", "Machine Learning", "Vol Breakout", "Pairs Trading"] if s in results]
    if len(active_strats) > 1:
        best_strat = max(active_strats, key=lambda s: results[s]["net_return_pct"])
        best_return = results[best_strat]["net_return_pct"]
        print(f"🏆 The **{best_strat} Strategy** emerged as the top-performing system with a cumulative return of **{best_return:+.2f}%**.")
        
        # Check Sharpe
        best_sharpe_strat = max(active_strats, key=lambda s: results[s]["sharpe_ratio"])
        print(f"💡 The **{best_sharpe_strat} Strategy** offered the best risk-adjusted performance with a Sharpe Ratio of **{results[best_sharpe_strat]['sharpe_ratio']:.2f}**.")
        
        # Check Drawdown
        best_dd_strat = max(active_strats, key=lambda s: results[s]["max_drawdown_pct"]) # max drawdown is negative, so max value is closest to 0
        print(f"🛡️ The **{best_dd_strat} Strategy** demonstrated the strongest capital preservation, limiting drawdown to **{results[best_dd_strat]['max_drawdown_pct']:.2f}%**.")
        
    print("=" * 115)

if __name__ == "__main__":
    main()
