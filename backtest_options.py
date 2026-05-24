#!/usr/bin/env python
"""
Options Max Pain Strategy Backtester & Payoff Simulator.
Backtests option pinning strategies (Short Straddles and Short Iron Butterflies)
centered at the calculated Max Pain strike using historical daily close prices.
"""

import argparse
import sys
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

# Import option analyzer functions
sys.path.append(sys.path[0])
import option_analyzer

def get_option_premium_today(data, results, strategy="butterfly", wing_pct=0.05):
    """
    Retrieve today's premium for the option strategy centered at the Max Pain strike.
    """
    calls = data['calls']
    puts = data['puts']
    mp = results['max_pain_strike']
    cp = results['current_price']
    
    if not mp or not cp:
        return None
        
    # Find ATM call and put at Max Pain strike
    atm_call = calls.loc[calls['strike'] == mp]
    atm_put = puts.loc[puts['strike'] == mp]
    
    if atm_call.empty or atm_put.empty:
        # Fallback to nearest strikes
        nearest_call_strike = calls.iloc[(calls['strike'] - mp).abs().argsort()[:1]]['strike'].values[0]
        atm_call = calls.loc[calls['strike'] == nearest_call_strike]
        atm_put = puts.loc[puts['strike'] == nearest_call_strike]
        mp = nearest_call_strike
        
    # Get call/put bid/ask premiums
    call_bid = atm_call['bid'].values[0] if not pd.isna(atm_call['bid'].values[0]) and atm_call['bid'].values[0] > 0 else atm_call['lastPrice'].values[0]
    call_ask = atm_call['ask'].values[0] if not pd.isna(atm_call['ask'].values[0]) and atm_call['ask'].values[0] > 0 else atm_call['lastPrice'].values[0]
    
    put_bid = atm_put['bid'].values[0] if not pd.isna(atm_put['bid'].values[0]) and atm_put['bid'].values[0] > 0 else atm_put['lastPrice'].values[0]
    put_ask = atm_put['ask'].values[0] if not pd.isna(atm_put['ask'].values[0]) and atm_put['ask'].values[0] > 0 else atm_put['lastPrice'].values[0]
    
    # Straddle premium collected (using mid or bid price for realistic entry)
    call_prem = (call_bid + call_ask) / 2 if call_bid and call_ask else (call_bid or 1.0)
    put_prem = (put_bid + put_ask) / 2 if put_bid and put_ask else (put_bid or 1.0)
    
    straddle_credit = call_prem + put_prem
    
    if strategy.lower() == "straddle":
        return {
            'strategy': 'Short Straddle',
            'strike': mp,
            'credit': straddle_credit,
            'extrinsic': max(0.01 * mp, straddle_credit - abs(cp - mp)),
            'wing_width': None
        }
        
    # Iron Butterfly wings: buy OTM Call (strike + w) and Put (strike - w)
    wing_width = round(mp * wing_pct, 1)
    if wing_width < 1.0:
        wing_width = 1.0
        
    call_wing_strike = calls.iloc[(calls['strike'] - (mp + wing_width)).abs().argsort()[:1]]['strike'].values[0]
    put_wing_strike = puts.iloc[(puts['strike'] - (mp - wing_width)).abs().argsort()[:1]]['strike'].values[0]
    
    long_call_row = calls.loc[calls['strike'] == call_wing_strike]
    long_put_row = puts.loc[puts['strike'] == put_wing_strike]
    
    long_call_ask = long_call_row['ask'].values[0] if not long_call_row.empty and not pd.isna(long_call_row['ask'].values[0]) else long_call_row['lastPrice'].values[0] if not long_call_row.empty else 0.1
    long_put_ask = long_put_row['ask'].values[0] if not long_put_row.empty and not pd.isna(long_put_row['ask'].values[0]) else long_put_row['lastPrice'].values[0] if not long_put_row.empty else 0.1
    
    # Credit for Iron Butterfly
    butterfly_credit = straddle_credit - (long_call_ask + long_put_ask)
    if butterfly_credit <= 0:
        # Fallback to default sizing if spread is wide
        butterfly_credit = straddle_credit * 0.4
        
    # Intrinsic value today of butterfly
    intrinsic_today = abs(cp - mp) - max(0.0, abs(cp - mp) - wing_width)
    extrinsic = max(0.005 * mp, butterfly_credit - intrinsic_today)
    
    return {
        'strategy': 'Short Iron Butterfly',
        'strike': mp,
        'credit': butterfly_credit,
        'extrinsic': extrinsic,
        'wing_width': wing_width,
        'long_call_strike': call_wing_strike,
        'long_put_strike': put_wing_strike
    }

def run_pinning_backtest(symbol, strategy_name="butterfly", lookback_days=20):
    """
    Backtest option pinning strategy on historical daily stock close prices.
    """
    # 1. Fetch current options diagnostic data
    data = option_analyzer.fetch_option_data(symbol)
    if not data:
        print(f"Failed to fetch option chain for {symbol}")
        return None
        
    results = option_analyzer.analyze_options(data)
    if not results:
        print(f"Failed to analyze options for {symbol}")
        return None
        
    mp = results['max_pain_strike']
    cp = results['current_price']
    
    if not mp or not cp:
        print(f"Required calculations missing for {symbol}")
        return None
        
    # 2. Get today's strategy premiums
    strat_details = get_option_premium_today(data, results, strategy_name)
    if not strat_details:
        print("Failed to compute strategy premiums.")
        return None
        
    credit = strat_details['credit']
    extrinsic = strat_details['extrinsic']
    w = strat_details['wing_width']
    
    # 3. Fetch historical daily closing prices
    ticker = yf.Ticker(symbol)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days * 1.5)  # buffer for trading days
    
    try:
        history = ticker.history(start=start_date, end=end_date)
    except Exception as e:
        print(f"Error fetching history for {symbol}: {e}")
        return None
        
    if history.empty:
        print(f"No historical prices found for {symbol}")
        return None
        
    # Slice to exact lookback
    history = history.tail(lookback_days)
    
    # 4. Step through days to calculate theoretical entry pricing and expiring P&L
    sim_trades = []
    
    for dt, row in history.iterrows():
        p_t = float(row['Close'])
        date_str = dt.strftime("%Y-%m-%d")
        
        # Deviation on entry day
        dev_from_mp = p_t - mp
        abs_dev = abs(dev_from_mp)
        
        if strategy_name.lower() == "straddle":
            # Short Straddle P&L calculation:
            # Intrinsic value at entry t is |P_t - K|
            # Premium collected at entry t is intrinsic + extrinsic today
            premium_t = abs_dev + extrinsic
            # Expiration value is |cp - K| (expires today at current price cp)
            expire_val = abs(cp - mp)
            pnl = premium_t - expire_val
            max_risk = mp
            roi = (pnl / mp) * 100 if mp > 0 else 0
            
        else:
            # Short Iron Butterfly P&L calculation:
            # Intrinsic value at entry t is |P_t - K| - max(0, |P_t - K| - w)
            intrinsic_t = abs_dev - max(0.0, abs_dev - w)
            premium_t = intrinsic_t + extrinsic
            # Expiration value is |cp - K| - max(0, |cp - K| - w)
            expire_val = abs(cp - mp) - max(0.0, abs(cp - mp) - w)
            pnl = premium_t - expire_val
            # Max risk in Iron Butterfly is the wing width w (margin collateral)
            max_risk = w
            roi = (pnl / w) * 100 if w > 0 else 0
            
        sim_trades.append({
            'date': date_str,
            'stock_price': p_t,
            'deviation_pct': (dev_from_mp / mp) * 100,
            'est_premium': premium_t,
            'expire_value': expire_val,
            'pnl': pnl,
            'roi_pct': roi,
            'outcome': "PROFIT" if pnl > 0 else "LOSS"
        })
        
    # Aggregate backtest stats
    trades_df = pd.DataFrame(sim_trades)
    total_trades = len(trades_df)
    profitable_trades = len(trades_df[trades_df['pnl'] > 0])
    win_rate = (profitable_trades / total_trades) * 100 if total_trades > 0 else 0
    avg_roi = trades_df['roi_pct'].mean()
    max_gain = trades_df['pnl'].max()
    max_loss = trades_df['pnl'].min()
    
    return {
        'symbol': symbol.upper(),
        'expiration': results['expiration_date'],
        'strategy': strat_details['strategy'],
        'max_pain_strike': mp,
        'current_price': cp,
        'wing_width': w,
        'credit_today': credit,
        'win_rate_pct': win_rate,
        'avg_roi_pct': avg_roi,
        'max_gain': max_gain,
        'max_loss': max_loss,
        'trades': sim_trades,
        'df': trades_df
    }

def print_backtest_report(report):
    """
    Print a beautiful executive backtesting report and price convergence chart.
    """
    if not report:
        print("No report data available.")
        return
        
    print("\n" + "="*80)
    print(f" EXECUTIVE BACKTEST: OPTIONS MAX PAIN PINNING STRATEGY ({report['symbol']})")
    print("="*80)
    print(f" Target Expiration Date:  {report['expiration']}")
    print(f" Simulated Strategy:      {report['strategy']}")
    print(f" Max Pain Strike (Pin):   ${report['max_pain_strike']:.2f}")
    print(f" Current Stock Price:     ${report['current_price']:.2f}")
    
    w = report['wing_width']
    if w:
        print(f" Strategy Parameters:     ATM Strike ${report['max_pain_strike']:.2f} | Wings: +-${w:.1f} (${report['max_pain_strike']-w:.1f} / ${report['max_pain_strike']+w:.1f})")
    else:
        print(f" Strategy Parameters:     ATM Strike ${report['max_pain_strike']:.2f}")
        
    print(f" Today's Base Credit:     ${report['credit_today']:.2f} per contract")
    print("-"*80)
    print(" BACKTEST PERFORMANCE SUMMARY")
    print("-"*80)
    print(f" Entry Period Lookback:   {len(report['trades'])} trading days")
    print(f" Pinning Win Rate:        {report['win_rate_pct']:.1f}% ({len(report['trades'])-len(report['df'][report['df']['pnl']<=0])} Wins | {len(report['df'][report['df']['pnl']<=0])} Losses)")
    print(f" Average Return (ROI):    {report['avg_roi_pct']:+.1f}%")
    print(f" Best Case Outcome:       {report['max_gain']:+.2f} per contract")
    print(f" Worst Case Outcome:      {report['max_loss']:+.2f} per contract")
    print("-"*80)
    print(" ENTRY PERIOD SIMULATION DETAILS")
    print("-"*80)
    print(f" {'ENTRY DATE':<12} | {'STOCK CLOSE':<12} | {'DEV FROM PIN':<13} | {'EST CREDIT':<11} | {'PAYOUT':<8} | {'P&L':<8} | {'ROI':<7}")
    print(f" {'='*12} | {'='*12} | {'='*13} | {'='*11} | {'='*8} | {'='*8} | {'='*7}")
    
    # Print list of trades (keep to last 10 for terminal brevity)
    trades = report['trades']
    show_trades = trades[-10:] if len(trades) > 10 else trades
    
    for t in show_trades:
        pnl_color = "+" if t['pnl'] > 0 else ""
        outcome_indicator = "Profit" if t['pnl'] > 0 else "Loss"
        
        print(f" {t['date']:<12} | ${t['stock_price']:<11.2f} | {t['deviation_pct']:+11.1f}% | ${t['est_premium']:<9.2f} | ${t['expire_value']:<6.2f} | {pnl_color}${t['pnl']:<6.2f} | {t['roi_pct']:+5.1f}%")
        
    if len(trades) > 10:
        print(f" ... ({len(trades)-10} older trading days summarized in aggregates) ...")
        
    print("-"*80)
    print(" HISTORICAL PRICE CONVERGENCE CHART (STOCK CLOSE VS PIN STRIKE)")
    print("-"*80)
    
    # Render beautiful ASCII price chart
    prices = [t['stock_price'] for t in trades]
    min_p = min(prices + [report['max_pain_strike']])
    max_p = max(prices + [report['max_pain_strike']])
    p_range = max_p - min_p if max_p - min_p > 0 else 1.0
    
    chart_height = 8
    chart_width = 45
    
    # Build empty canvas
    canvas = [[" " for _ in range(chart_width)] for _ in range(chart_height)]
    
    # Scaling index to timeline width
    num_pts = len(prices)
    for idx, p in enumerate(prices):
        # Map x coordinate
        x = int((idx / (num_pts - 1)) * (chart_width - 1)) if num_pts > 1 else 0
        # Map y coordinate (reversed y axis)
        y_pct = (p - min_p) / p_range
        y = int((1.0 - y_pct) * (chart_height - 1))
        
        canvas[y][x] = "*"
        
    # Draw Max Pain line (marked with '-' or 'P' at the end)
    mp = report['max_pain_strike']
    mp_y_pct = (mp - min_p) / p_range
    mp_y = int((1.0 - mp_y_pct) * (chart_height - 1))
    
    for x in range(chart_width):
        if canvas[mp_y][x] == "*":
            canvas[mp_y][x] = "X"  # crossover
        else:
            canvas[mp_y][x] = "-"
            
    # Print the canvas with price labels
    for y_idx in range(chart_height):
        # Calculate row price label
        row_price = max_p - (y_idx / (chart_height - 1)) * p_range
        indicator = " PIN -> " if y_idx == mp_y else "        "
        
        row_str = "".join(canvas[y_idx])
        print(f" {row_price:>8.2f} {indicator} | {row_str}")
        
    timeline_lbl = " " * 22 + "T-20 Days" + " " * 8 + "T-0 (Expiration Today)"
    print(f" {' '*18} +-{'-'*chart_width}")
    print(timeline_lbl)
    
    print("="*80)
    print(" Interpretation:")
    print(" Asterisks (*) represent the historical stock closing prices leading up to today.")
    print(" Dashes (-) represent the Max Pain Strike. An 'X' marks where price crossed the Pin.")
    print(" Profitable entries occur when the stock price converges closer to the Pin at expiration.")
    print("="*80 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Backtest Option Pinning strategy centered at Max Pain.")
    parser.add_argument("--symbol", type=str, default="AAPL", help="Stock ticker symbol (e.g. AAPL)")
    parser.add_argument("--strategy", type=str, default="butterfly", choices=["butterfly", "straddle"], help="Option strategy (butterfly or straddle)")
    parser.add_argument("--lookback", type=int, default=20, help="Number of historical trading days to simulate")
    
    args = parser.parse_args()
    
    print(f"Running pinning strategy simulation for {args.symbol}...")
    report = run_pinning_backtest(args.symbol, args.strategy, args.lookback)
    
    if report:
        print_backtest_report(report)
    else:
        print("Backtest simulation failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
