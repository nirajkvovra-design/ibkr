#!/usr/bin/env python
"""
Options Strategy Advisor: Dynamic options strategy generator.
Translates options chain diagnostics (Max Pain, Walls, and Put/Call ratios)
into exact, low-capital option spread recommendations (Credit Spreads, Iron Butterflies).
Tailored specifically for minimum capital trading setups.
"""

import sys
import argparse
from pathlib import Path

# Add script directory to search path
sys.path.append(str(Path(__file__).parent.resolve()))
import option_analyzer
import config

# Set up encoding support for Windows CMD
import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def recommend_options_strategy(symbol, expiration_date=None, max_collateral=500.0):
    """
    Analyzes options chain and recommends low-capital option strategies.
    
    Args:
        symbol: Stock ticker
        expiration_date: Target expiration YYYY-MM-DD
        max_collateral: Maximum capital/risk allowed per trade (default $500)
    """
    # 1. Fetch options chain
    data = option_analyzer.fetch_option_data(symbol, expiration_date)
    if not data:
        return None
        
    # 2. Analyze chain
    results = option_analyzer.analyze_options(data)
    if not results:
        return None
        
    cp = results['current_price']
    mp = results['max_pain_strike']
    pcr_oi = results['pcr_oi']
    cw = results['call_wall']
    pw = results['put_wall']
    
    if not cp or not mp:
        print(f"[-] Required metrics unavailable for {symbol}")
        return None
        
    print("\n" + "="*80)
    print(f" OPTIONS STRATEGY ADVISOR FOR {symbol} ({results['expiration_date']})")
    print(f" Current Price: ${cp:.2f} | Max Pain Pin: ${mp:.2f} | Put/Call Ratio (OI): {pcr_oi}")
    print(f" Resistance (Call Wall): ${cw:.2f} | Support (Put Wall): ${pw:.2f}")
    print("="*80)
    
    recommendations = []
    
    # ----------------------------------------------------
    # STRATEGY 1: Short Iron Butterfly (Neutral/Pinning play)
    # ----------------------------------------------------
    # Best when price is close to Max Pain and Put/Call Ratio is neutral
    is_neutral = 0.8 <= pcr_oi <= 1.25
    dist_to_mp = abs(cp - mp) / mp
    
    # We choose a wing width that fits within our maximum collateral budget
    # Settle on a standard spread width (e.g. $2.50 or $5.00 width depending on price)
    if cp > 150:
        wing_width = 5.0
    elif cp > 50:
        wing_width = 2.5
    else:
        wing_width = 1.0
        
    # Ensure wing width stays within user's max risk/collateral
    if wing_width * 100 > max_collateral:
        wing_width = max_collateral / 100.0
        
    short_strike = mp
    long_put_strike = short_strike - wing_width
    long_call_strike = short_strike + wing_width
    
    # Estimate premium credit collected (ATM straddle is typically ~6-10% of stock price)
    # For Iron Butterfly, we collect ATM credit and buy wings. Collect ~40-60% of wing width as net credit.
    est_credit_butterfly = round(wing_width * 0.50, 2)
    max_risk_butterfly = round(wing_width - est_credit_butterfly, 2)
    
    butterfly_rec = {
        "name": "Short Iron Butterfly (Max Pain Neutral Pin)",
        "suitability": "HIGH" if (dist_to_mp < 0.04 and is_neutral) else "MEDIUM",
        "description": f"Sells an ATM Straddle at the Max Pain strike (${short_strike:.2f}) and buys OTM wings to limit risk. Profitable if {symbol} stays rangebound and converges to Max Pain at expiration.",
        "legs": [
            f"Sell 1x Call @ Strike ${short_strike:.2f} (ATM)",
            f"Sell 1x Put @ Strike ${short_strike:.2f} (ATM)",
            f"Buy  1x Call @ Strike ${long_call_strike:.2f} (OTM Protection)",
            f"Buy  1x Put  @ Strike ${long_put_strike:.2f} (OTM Protection)"
        ],
        "metrics": {
            "net_credit_collected": f"${est_credit_butterfly * 100:.0f} (${est_credit_butterfly:.2f} per share)",
            "max_profit": f"${est_credit_butterfly * 100:.0f} (if stock pins exactly at ${short_strike:.2f})",
            "max_risk_collateral": f"${max_risk_butterfly * 100:.0f} (${max_risk_butterfly:.2f} per share)",
            "margin_requirement": f"${wing_width * 100:.0f} (Width of spread)",
            "breakeven_range": f"${short_strike - est_credit_butterfly:.2f} to ${short_strike + est_credit_butterfly:.2f}"
        }
    }
    recommendations.append(butterfly_rec)
    
    # ----------------------------------------------------
    # STRATEGY 2: Bull Put Credit Spread (Bullish Income play)
    # ----------------------------------------------------
    # Best when Put/Call ratio is low (bullish) or price is near support Put Wall
    # Sell Put at Support Strike, Buy Put below it.
    put_short_strike = pw if pw and pw < cp else round(cp * 0.95, 1)
    # Ensure it's slightly OTM
    if put_short_strike >= cp:
        put_short_strike = round(cp * 0.96, 1)
        
    spread_width = 2.5 if cp > 80 else 1.0
    if spread_width * 100 > max_collateral:
        spread_width = max_collateral / 100.0
        
    put_long_strike = put_short_strike - spread_width
    
    # Estimate OTM put credit (~15-25% of spread width)
    est_credit_put_spread = round(spread_width * 0.25, 2)
    max_risk_put_spread = round(spread_width - est_credit_put_spread, 2)
    
    put_spread_rec = {
        "name": "Bull Put Credit Spread (Bullish Income)",
        "suitability": "HIGH" if (pcr_oi < 0.85 or cp > put_short_strike) else "MEDIUM",
        "description": f"Sells an OTM Put at the support wall (${put_short_strike:.2f}) and buys a lower Put for protection. Highly profitable if {symbol} stays above the support wall at expiration.",
        "legs": [
            f"Sell 1x Put @ Strike ${put_short_strike:.2f} (Support Wall)",
            f"Buy  1x Put @ Strike ${put_long_strike:.2f} (OTM Protection)"
        ],
        "metrics": {
            "net_credit_collected": f"${est_credit_put_spread * 100:.0f} (${est_credit_put_spread:.2f} per share)",
            "max_profit": f"${est_credit_put_spread * 100:.0f} (if stock expires above ${put_short_strike:.2f})",
            "max_risk_collateral": f"${max_risk_put_spread * 100:.0f} (${max_risk_put_spread:.2f} per share)",
            "margin_requirement": f"${spread_width * 100:.0f} (Width of spread)",
            "breakeven_point": f"${put_short_strike - est_credit_put_spread:.2f}"
        }
    }
    recommendations.append(put_spread_rec)
    
    # ----------------------------------------------------
    # STRATEGY 3: Bear Call Credit Spread (Bearish Income play)
    # ----------------------------------------------------
    # Best when Put/Call ratio is high (bearish) or price is near resistance Call Wall
    # Sell Call at Resistance Strike, Buy Call above it.
    call_short_strike = cw if cw and cw > cp else round(cp * 1.05, 1)
    if call_short_strike <= cp:
        call_short_strike = round(cp * 1.04, 1)
        
    call_long_strike = call_short_strike + spread_width
    
    # Estimate OTM call credit
    est_credit_call_spread = round(spread_width * 0.25, 2)
    max_risk_call_spread = round(spread_width - est_credit_call_spread, 2)
    
    call_spread_rec = {
        "name": "Bear Call Credit Spread (Bearish Income)",
        "suitability": "HIGH" if (pcr_oi > 1.25 or cp < call_short_strike) else "MEDIUM",
        "description": f"Sells an OTM Call at the resistance wall (${call_short_strike:.2f}) and buys a higher Call for protection. Highly profitable if {symbol} stays below the resistance wall at expiration.",
        "legs": [
            f"Sell 1x Call @ Strike ${call_short_strike:.2f} (Resistance Wall)",
            f"Buy  1x Call @ Strike ${call_long_strike:.2f} (OTM Protection)"
        ],
        "metrics": {
            "net_credit_collected": f"${est_credit_call_spread * 100:.0f} (${est_credit_call_spread:.2f} per share)",
            "max_profit": f"${est_credit_call_spread * 100:.0f} (if stock expires below ${call_short_strike:.2f})",
            "max_risk_collateral": f"${max_risk_call_spread * 100:.0f} (${max_risk_call_spread:.2f} per share)",
            "margin_requirement": f"${spread_width * 100:.0f} (Width of spread)",
            "breakeven_point": f"${call_short_strike + est_credit_call_spread:.2f}"
        }
    }
    recommendations.append(call_spread_rec)
    
    # 3. Print Recommendations to console
    for i, rec in enumerate(recommendations, 1):
        suit_symbol = ">>> [HIGHLY SUITABLE]" if rec['suitability'] == "HIGH" else "    [SUITABLE]"
        print(f"\n{i}. {rec['name']}")
        print(f"   Suitability: {suit_symbol}")
        print(f"   Description: {rec['description']}")
        print("   Legs:")
        for leg in rec['legs']:
            print(f"     - {leg}")
        print("   Strategy Economics (1 Contract):")
        for key, val in rec['metrics'].items():
            k_name = key.replace("_", " ").title()
            print(f"     - {k_name:<22}: {val}")
            
    print("\n" + "="*80)
    print(" Option Spread Capital Efficiency Tip:")
    print(" Unlike buying naked calls/puts which decay rapidly due to Theta (time decay),")
    print(" credit spreads let you sell high-decay options to collect premium, protected")
    print(" by a long option. This caps your absolute risk and lets time decay work FOR you!")
    print("="*80 + "\n")
    
    return recommendations

def main():
    parser = argparse.ArgumentParser(description="Generate low-capital options spread recommendations.")
    parser.add_argument("--symbol", type=str, default="AAPL", help="Stock ticker symbol (e.g. AAPL)")
    parser.add_argument("--expiration", type=str, default=None, help="Option expiration YYYY-MM-DD")
    parser.add_argument("--max_risk", type=float, default=500.0, help="Maximum margin/collateral risk allowed in USD")
    
    args = parser.parse_args()
    recommend_options_strategy(args.symbol, args.expiration, args.max_risk)

if __name__ == "__main__":
    main()
