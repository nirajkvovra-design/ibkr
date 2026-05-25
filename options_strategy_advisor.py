#!/usr/bin/env python
"""
Options Strategy Advisor: Dynamic options strategy generator.
Translates options chain diagnostics (Max Pain, Walls, and Put/Call ratios)
into exact, low-capital option spread recommendations (Credit Spreads, Iron Butterflies).
Integrates with OptionsIntelligenceEngine for exact Greek exposures and Probability of Profit (PoP).
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add script directory to search path
sys.path.append(str(Path(__file__).parent.resolve()))
import option_analyzer
import config
from options_intelligence import OptionsIntelligenceEngine

# Set up encoding support for Windows CMD
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def recommend_options_strategy(symbol, expiration_date=None, max_collateral=500.0):
    """
    Analyzes options chain and recommends low-capital option strategies with exact Greeks and PoP.
    
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

    # Calculate days remaining
    try:
        exp_date = datetime.strptime(results['expiration_date'], '%Y-%m-%d')
        days_to_expiry = max(1.0, float((exp_date - datetime.now()).days))
    except Exception:
        days_to_expiry = 30.0  # Fallback to standard monthly expiration window
        
    # Instantiate Options Intelligence Engine
    engine = OptionsIntelligenceEngine()
    
    print("\n" + "="*85)
    print(f" INSTITUTIONAL OPTIONS STRATEGY ADVISOR FOR {symbol} ({results['expiration_date']})")
    print(f" Underlier Price: ${cp:.2f} | Days To Expiry: {int(days_to_expiry)}d | Max Pain Strike: ${mp:.2f}")
    print(f" Support (Put Wall): ${pw:.2f} | Resistance (Call Wall): ${cw:.2f} | PCR (Open Interest): {pcr_oi:.2f}")
    print("="*85)
    
    recommendations = []

    # Helper function to find option price, IV, bid, ask
    def get_option_metrics(df, strike_price):
        if df is None or df.empty:
            return 0.0, 0.25, 0.0, 0.0, strike_price
        idx = (df['strike'] - strike_price).abs().idxmin()
        row = df.loc[idx]
        bid = float(row.get('bid', 0.0))
        ask = float(row.get('ask', 0.0))
        last = float(row.get('lastPrice', 0.0))
        iv = float(row.get('impliedVolatility', 0.25))
        
        price = 0.5 * (bid + ask) if bid > 0 and ask > 0 else last
        if price <= 0:
            price = last if last > 0 else 0.01
            
        return price, iv, bid, ask, float(row['strike'])
    
    # ----------------------------------------------------
    # STRATEGY 1: Short Iron Butterfly (Neutral Pin)
    # ----------------------------------------------------
    is_neutral = 0.8 <= pcr_oi <= 1.25
    dist_to_mp = abs(cp - mp) / mp
    
    if cp > 150:
        wing_width = 5.0
    elif cp > 50:
        wing_width = 2.5
    else:
        wing_width = 1.0
        
    if wing_width * 100 > max_collateral:
        wing_width = max_collateral / 100.0
        
    short_strike = mp
    long_put_strike = short_strike - wing_width
    long_call_strike = short_strike + wing_width
    
    # Fetch real options chain data for the legs
    sc_price, sc_iv, _, _, actual_sc_strike = get_option_metrics(data['calls'], short_strike)
    sp_price, sp_iv, _, _, actual_sp_strike = get_option_metrics(data['puts'], short_strike)
    lc_price, lc_iv, _, _, actual_lc_strike = get_option_metrics(data['calls'], long_call_strike)
    lp_price, lp_iv, _, _, actual_lp_strike = get_option_metrics(data['puts'], long_put_strike)
    
    # Combined spread net credit
    est_credit_butterfly = max(0.1, (sc_price + sp_price) - (lc_price + lp_price))
    max_risk_butterfly = max(0.05, wing_width - est_credit_butterfly)
    
    # Calculate Greeks of short legs
    g_sc = engine.calculate_greeks(symbol, actual_sc_strike, days_to_expiry, cp, sc_iv, "CALL")
    g_sp = engine.calculate_greeks(symbol, actual_sp_strike, days_to_expiry, cp, sp_iv, "PUT")
    
    net_theta = g_sc["theta"] + g_sp["theta"]
    
    # Probability of Profit (break-evens)
    lower_be = actual_sc_strike - est_credit_butterfly
    upper_be = actual_sc_strike + est_credit_butterfly
    pop_butterfly = engine.calculate_probability_of_profit(
        cp, days_to_expiry, 0.5 * (sc_iv + sp_iv), lower_break_even=lower_be, upper_break_even=upper_be
    )
    
    butterfly_rec = {
        "name": "Short Iron Butterfly (Max Pain Neutral Pin)",
        "suitability": "HIGH" if (dist_to_mp < 0.04 and is_neutral) else "MEDIUM",
        "description": f"Sells an ATM Straddle at the Max Pain strike (${actual_sc_strike:.2f}) and buys OTM wings to limit risk. Profitable if {symbol} stays rangebound and converges to Max Pain.",
        "legs": [
            f"Sell 1x Call @ Strike ${actual_sc_strike:.2f} (Mid: ${sc_price:.2f}, IV: {sc_iv*100:.1f}%)",
            f"Sell 1x Put  @ Strike ${actual_sp_strike:.2f} (Mid: ${sp_price:.2f}, IV: {sp_iv*100:.1f}%)",
            f"Buy  1x Call @ Strike ${actual_lc_strike:.2f} (OTM Protection, Mid: ${lc_price:.2f})",
            f"Buy  1x Put  @ Strike ${actual_lp_strike:.2f} (OTM Protection, Mid: ${lp_price:.2f})"
        ],
        "metrics": {
            "net_credit_collected": f"${est_credit_butterfly * 100:.0f} (${est_credit_butterfly:.2f} per share)",
            "max_profit": f"${est_credit_butterfly * 100:.0f} (if stock pins exactly at ${actual_sc_strike:.2f})",
            "max_risk_collateral": f"${max_risk_butterfly * 100:.0f} (${max_risk_butterfly:.2f} per share)",
            "margin_requirement": f"${wing_width * 100:.0f} (Width of spread)",
            "breakeven_range": f"${lower_be:.2f} to ${upper_be:.2f}",
            "net_short_theta": f"${abs(net_theta)*100:.2f} decay/day",
            "probability_of_profit": f"{pop_butterfly:.1f}%"
        }
    }
    recommendations.append(butterfly_rec)
    
    # ----------------------------------------------------
    # STRATEGY 2: Bull Put Credit Spread (Bullish Income)
    # ----------------------------------------------------
    put_short_strike = pw if pw and pw < cp else round(cp * 0.95, 1)
    if put_short_strike >= cp:
        put_short_strike = round(cp * 0.96, 1)
        
    spread_width = 2.5 if cp > 80 else 1.0
    if spread_width * 100 > max_collateral:
        spread_width = max_collateral / 100.0
        
    put_long_strike = put_short_strike - spread_width
    
    # Fetch real options
    sp_price, sp_iv, _, _, actual_sp_strike = get_option_metrics(data['puts'], put_short_strike)
    lp_price, lp_iv, _, _, actual_lp_strike = get_option_metrics(data['puts'], put_long_strike)
    
    est_credit_put_spread = max(0.05, sp_price - lp_price)
    max_risk_put_spread = max(0.05, (actual_sp_strike - actual_lp_strike) - est_credit_put_spread)
    
    g_sp = engine.calculate_greeks(symbol, actual_sp_strike, days_to_expiry, cp, sp_iv, "PUT")
    be_point_put = actual_sp_strike - est_credit_put_spread
    pop_put_spread = engine.calculate_probability_of_profit(
        cp, days_to_expiry, sp_iv, lower_break_even=be_point_put
    )
    
    put_spread_rec = {
        "name": "Bull Put Credit Spread (Bullish Income)",
        "suitability": "HIGH" if (pcr_oi < 0.85 or cp > actual_sp_strike) else "MEDIUM",
        "description": f"Sells an OTM Put at the support wall (${actual_sp_strike:.2f}) and buys a lower Put for protection. Highly profitable if {symbol} stays above support wall.",
        "legs": [
            f"Sell 1x Put @ Strike ${actual_sp_strike:.2f} (Support, Mid: ${sp_price:.2f}, IV: {sp_iv*100:.1f}%)",
            f"Buy  1x Put @ Strike ${actual_lp_strike:.2f} (OTM Protection, Mid: ${lp_price:.2f})"
        ],
        "metrics": {
            "net_credit_collected": f"${est_credit_put_spread * 100:.0f} (${est_credit_put_spread:.2f} per share)",
            "max_profit": f"${est_credit_put_spread * 100:.0f} (if stock expires above ${actual_sp_strike:.2f})",
            "max_risk_collateral": f"${max_risk_put_spread * 100:.0f} (${max_risk_put_spread:.2f} per share)",
            "margin_requirement": f"${(actual_sp_strike - actual_lp_strike)*100:.0f} (Width of spread)",
            "breakeven_point": f"${be_point_put:.2f}",
            "short_leg_delta": f"{g_sp['delta']:.3f} (Short Put)",
            "short_leg_theta": f"${abs(g_sp['theta'])*100:.2f} decay/day",
            "probability_of_profit": f"{pop_put_spread:.1f}%"
        }
    }
    recommendations.append(put_spread_rec)
    
    # ----------------------------------------------------
    # STRATEGY 3: Bear Call Credit Spread (Bearish Income)
    # ----------------------------------------------------
    call_short_strike = cw if cw and cw > cp else round(cp * 1.05, 1)
    if call_short_strike <= cp:
        call_short_strike = round(cp * 1.04, 1)
        
    call_long_strike = call_short_strike + spread_width
    
    # Fetch real options
    sc_price, sc_iv, _, _, actual_sc_strike = get_option_metrics(data['calls'], call_short_strike)
    lc_price, lc_iv, _, _, actual_lc_strike = get_option_metrics(data['calls'], call_long_strike)
    
    est_credit_call_spread = max(0.05, sc_price - lc_price)
    max_risk_call_spread = max(0.05, (actual_lc_strike - actual_sc_strike) - est_credit_call_spread)
    
    g_sc = engine.calculate_greeks(symbol, actual_sc_strike, days_to_expiry, cp, sc_iv, "CALL")
    be_point_call = actual_sc_strike + est_credit_call_spread
    pop_call_spread = engine.calculate_probability_of_profit(
        cp, days_to_expiry, sc_iv, upper_break_even=be_point_call
    )
    
    call_spread_rec = {
        "name": "Bear Call Credit Spread (Bearish Income)",
        "suitability": "HIGH" if (pcr_oi > 1.25 or cp < actual_sc_strike) else "MEDIUM",
        "description": f"Sells an OTM Call at the resistance wall (${actual_sc_strike:.2f}) and buys a higher Call for protection. Highly profitable if {symbol} stays below resistance wall.",
        "legs": [
            f"Sell 1x Call @ Strike ${actual_sc_strike:.2f} (Resistance, Mid: ${sc_price:.2f}, IV: {sc_iv*100:.1f}%)",
            f"Buy  1x Call @ Strike ${actual_lc_strike:.2f} (OTM Protection, Mid: ${lc_price:.2f})"
        ],
        "metrics": {
            "net_credit_collected": f"${est_credit_call_spread * 100:.0f} (${est_credit_call_spread:.2f} per share)",
            "max_profit": f"${est_credit_call_spread * 100:.0f} (if stock expires below ${actual_sc_strike:.2f})",
            "max_risk_collateral": f"${max_risk_call_spread * 100:.0f} (${max_risk_call_spread:.2f} per share)",
            "margin_requirement": f"${(actual_lc_strike - actual_sc_strike)*100:.0f} (Width of spread)",
            "breakeven_point": f"${be_point_call:.2f}",
            "short_leg_delta": f"{g_sc['delta']:.3f} (Short Call)",
            "short_leg_theta": f"${abs(g_sc['theta'])*100:.2f} decay/day",
            "probability_of_profit": f"{pop_call_spread:.1f}%"
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
        print("   Strategy Quantitative Economics:")
        for key, val in rec['metrics'].items():
            k_name = key.replace("_", " ").title()
            print(f"     - {k_name:<24}: {val}")
            
    print("\n" + "="*85)
    print(" Institutional Options Risk Reminder:")
    print(" Theta is the short-seller's best friend. Premium decay accelerates dramatically")
    print(" during the final 30 days before expiration, providing high statistical edge.")
    print(" Always confirm short delta is kept low (<0.30) to preserve high win-rate.")
    print("="*85 + "\n")
    
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
