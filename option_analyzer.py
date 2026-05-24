#!/usr/bin/env python
"""
Option Analyzer: Fetches options chain data, calculates Max Pain, Put/Call ratios,
and option support/resistance walls, with full CLI printout and terminal visualization.
"""

import argparse
import sys
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

def fetch_option_data(symbol, expiration_date=None):
    """
    Fetch option chain data for a symbol and a specific expiration date.
    If no expiration_date is provided, the nearest one is selected.
    """
    ticker = yf.Ticker(symbol)
    
    # Get all available expirations
    try:
        expirations = ticker.options
    except Exception as e:
        print(f"Error fetching expiration dates for {symbol}: {e}")
        return None
        
    if not expirations:
        print(f"No option chains found for {symbol}")
        return None
        
    # Select expiration date
    if expiration_date is None:
        expiration_date = expirations[0]
    elif expiration_date not in expirations:
        # Find closest match or default to nearest
        print(f"Requested expiration {expiration_date} not found. Defaulting to nearest: {expirations[0]}")
        expiration_date = expirations[0]
        
    print(f"Fetching option chain for {symbol} with expiration {expiration_date}...")
    
    # Fetch option chain
    try:
        chain = ticker.option_chain(expiration_date)
        calls = chain.calls
        puts = chain.puts
    except Exception as e:
        print(f"Error fetching option chain for {symbol} / {expiration_date}: {e}")
        return None
        
    # Fetch current price
    current_price = None
    try:
        current_price = ticker.info.get('currentPrice') or ticker.info.get('regularMarketPrice')
    except Exception:
        pass
        
    if current_price is None:
        try:
            history = ticker.history(period="5d")
            if not history.empty:
                current_price = float(history['Close'].iloc[-1])
        except Exception:
            pass
            
    return {
        'symbol': symbol.upper(),
        'expiration_date': expiration_date,
        'all_expirations': expirations,
        'current_price': current_price,
        'calls': calls,
        'puts': puts
    }

def analyze_options(data):
    """
    Perform Max Pain, PCR, and support/resistance analysis on the fetched option data.
    """
    calls = data['calls']
    puts = data['puts']
    current_price = data['current_price']
    
    # Drop NaNs or zero open interest to speed up and clean calculations
    calls_clean = calls.dropna(subset=['strike', 'openInterest'])
    puts_clean = puts.dropna(subset=['strike', 'openInterest'])
    
    # Unique strike prices
    strikes = sorted(list(set(calls_clean['strike']) | set(puts_clean['strike'])))
    
    if not strikes:
        return None
        
    call_oi = calls_clean.set_index('strike')['openInterest'].to_dict()
    put_oi = puts_clean.set_index('strike')['openInterest'].to_dict()
    
    call_vol = calls_clean.set_index('strike')['volume'].to_dict()
    put_vol = puts_clean.set_index('strike')['volume'].to_dict()
    
    # 1. Calculate Max Pain
    pain_map = {}
    for S in strikes:
        total_pain = 0.0
        # Call pain: Calls with strike K < S expire in-the-money (value S - K)
        for K, oi in call_oi.items():
            if oi > 0 and S > K:
                total_pain += (S - K) * oi
                
        # Put pain: Puts with strike K > S expire in-the-money (value K - S)
        for K, oi in put_oi.items():
            if oi > 0 and K > S:
                total_pain += (K - S) * oi
                
        pain_map[S] = total_pain
        
    max_pain_strike = min(pain_map, key=pain_map.get) if pain_map else None
    
    # 2. Key Walls (Support and Resistance)
    # Call Wall: highest call open interest
    call_wall_row = calls_clean.loc[calls_clean['openInterest'].idxmax()] if not calls_clean.empty else None
    call_wall = float(call_wall_row['strike']) if call_wall_row is not None else None
    call_wall_oi = int(call_wall_row['openInterest']) if call_wall_row is not None else 0
    
    # Put Wall: highest put open interest
    put_wall_row = puts_clean.loc[puts_clean['openInterest'].idxmax()] if not puts_clean.empty else None
    put_wall = float(put_wall_row['strike']) if put_wall_row is not None else None
    put_wall_oi = int(put_wall_row['openInterest']) if put_wall_row is not None else 0
    
    # 3. Put/Call Ratios
    total_call_oi = sum(call_oi.values())
    total_put_oi = sum(put_oi.values())
    pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else 0.0
    
    total_call_vol = sum(v for v in call_vol.values() if not pd.isna(v))
    total_put_vol = sum(v for v in put_vol.values() if not pd.isna(v))
    pcr_vol = total_put_vol / total_call_vol if total_call_vol > 0 else 0.0
    
    # Filter strikes near current price for plotting/detailed analysis
    near_strikes = strikes
    if current_price:
        near_strikes = [s for s in strikes if current_price * 0.85 <= s <= current_price * 1.15]
        # Ensure we have at least some strikes, fallback to all if empty
        if not near_strikes:
            near_strikes = strikes
            
    # Create structured list of detailed strikes
    strikes_details = []
    for s in sorted(near_strikes):
        c_oi = int(call_oi.get(s, 0))
        p_oi = int(put_oi.get(s, 0))
        c_vol = int(call_vol.get(s, 0)) if not pd.isna(call_vol.get(s, 0)) else 0
        p_vol = int(put_vol.get(s, 0)) if not pd.isna(put_vol.get(s, 0)) else 0
        
        strikes_details.append({
            'strike': float(s),
            'call_oi': c_oi,
            'put_oi': p_oi,
            'call_vol': c_vol,
            'put_vol': p_vol,
            'total_pain': float(pain_map.get(s, 0.0))
        })
        
    return {
        'symbol': data['symbol'],
        'expiration_date': data['expiration_date'],
        'current_price': current_price,
        'max_pain_strike': max_pain_strike,
        'total_call_oi': int(total_call_oi),
        'total_put_oi': int(total_put_oi),
        'pcr_oi': round(pcr_oi, 3),
        'total_call_vol': int(total_call_vol),
        'total_put_vol': int(total_put_vol),
        'pcr_vol': round(pcr_vol, 3),
        'call_wall': call_wall,
        'call_wall_oi': call_wall_oi,
        'put_wall': put_wall,
        'put_wall_oi': put_wall_oi,
        'strikes': strikes_details
    }

def print_cli_analysis(results):
    """
    Print analysis results to the terminal with a beautiful ASCII bar chart.
    """
    if not results:
        print("No results to display.")
        return
        
    print("\n" + "="*60)
    print(f" OPTIONS DIAGNOSTIC: {results['symbol']} ({results['expiration_date']})")
    print("="*60)
    
    cp = results['current_price']
    mp = results['max_pain_strike']
    
    print(f" Current Stock Price: ${cp:.2f}" if cp else " Current Stock Price: N/A")
    print(f" Max Pain Strike:     ${mp:.2f}" if mp else " Max Pain Strike:     N/A")
    
    if cp and mp:
        diff_val = cp - mp
        diff_pct = (diff_val / mp) * 100
        direction = "above" if diff_val > 0 else "below"
        print(f" Price Deviation:     ${abs(diff_val):.2f} ({abs(diff_pct):.2f}%) {direction} Max Pain")
        
    print(f" Put/Call Ratio (OI): {results['pcr_oi']}  (Call OI: {results['total_call_oi']:,} | Put OI: {results['total_put_oi']:,})")
    print(f" Put/Call Ratio (Vol):{results['pcr_vol']}  (Call Vol: {results['total_call_vol']:,} | Put Vol: {results['total_put_vol']:,})")
    
    cw = results['call_wall']
    pw = results['put_wall']
    print(f" Call Wall (Resist):  ${cw:.2f} (OI: {results['call_wall_oi']:,})" if cw else " Call Wall (Resist):  N/A")
    print(f" Put Wall (Support):  ${pw:.2f} (OI: {results['put_wall_oi']:,})" if pw else " Put Wall (Support):  N/A")
    print("-"*60)
    print(" OPEN INTEREST DISTRIBUTION (STRIKES NEAR STOCK PRICE)")
    print("-"*60)
    print(f" {'PUT OI':>12} | {'STRIKE':^10} | {'CALL OI':<12}")
    print(f" {'='*12} | {'='*10} | {'='*12}")
    
    # Show strikes around the current price
    strikes = results['strikes']
    if cp:
        # Keep up to 12 strikes closest to current price for cleaner CLI view
        strikes = sorted(strikes, key=lambda x: abs(x['strike'] - cp))[:12]
        strikes = sorted(strikes, key=lambda x: x['strike'])
        
    # Determine max OI value for scaling the bar chart
    max_oi = max([max(s['call_oi'], s['put_oi']) for s in strikes]) if strikes else 1
    if max_oi == 0:
        max_oi = 1
        
    bar_max_width = 18
    
    for s in strikes:
        strike_val = s['strike']
        c_oi = s['call_oi']
        p_oi = s['put_oi']
        
        # Scaling bars
        c_bar_len = int((c_oi / max_oi) * bar_max_width)
        p_bar_len = int((p_oi / max_oi) * bar_max_width)
        
        c_bar = "#" * c_bar_len
        p_bar = "#" * p_bar_len
        
        # Labels for current price and max pain
        labels = []
        if cp and abs(strike_val - cp) < 0.01:
            labels.append("<- Price")
        if mp and strike_val == mp:
            labels.append("<- Max Pain")
        if cw and strike_val == cw:
            labels.append("<- Call Wall")
        if pw and strike_val == pw:
            labels.append("<- Put Wall")
            
        label_str = " " + " | ".join(labels) if labels else ""
        
        p_oi_str = f"{p_oi:,}"
        c_oi_str = f"{c_oi:,}"
        
        # We align Put bar to the right, Strike in center, Call bar to the left
        p_side = f"{p_oi_str:>7} {p_bar:>18}"
        c_side = f"{c_bar:<18} {c_oi_str:<7}"
        strike_lbl = f"${strike_val:^8.2f}"
        
        print(f"{p_side} | {strike_lbl} | {c_side}{label_str}")
        
    print("="*60)
    print(" Max Pain Pinning Theory suggests that on option expiration day,")
    print(" the stock price tends to gravitate toward the Max Pain point,")
    print(" which is where the maximum value of option contracts expire worthless.")
    print("="*60 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Analyze options open interest and calculate Max Pain.")
    parser.add_argument("--symbol", type=str, default="AAPL", help="Stock ticker symbol (e.g. AAPL)")
    parser.add_argument("--expiration", type=str, default=None, help="Option expiration date (YYYY-MM-DD), default closest")
    
    args = parser.parse_args()
    
    data = fetch_option_data(args.symbol, args.expiration)
    if not data:
        sys.exit(1)
        
    results = analyze_options(data)
    if not results:
        print("Analysis failed to produce results.")
        sys.exit(1)
        
    print_cli_analysis(results)

if __name__ == "__main__":
    main()
