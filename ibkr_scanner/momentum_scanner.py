"""
Momentum Breakout Scanner with Technical Indicators
==================================================

Scans stocks for momentum breakout patterns using:
- MACD (Moving Average Convergence Divergence)
- ADX (Average Directional Index) 
- RSI (Relative Strength Index)
- Candlestick patterns (Hammer, Doji, Engulfing, etc.)
- Volume analysis
- Price breakouts

Requirements: pip install talib-binary pandas numpy
"""

from ib_async import *
import pandas as pd
import numpy as np
import talib
import argparse
import asyncio
from datetime import datetime

class MomentumScanner:
    def __init__(self, ib_client):
        self.ib = ib_client
        
    def calculate_technical_indicators(self, df):
        """Calculate all technical indicators"""
        if len(df) < 50:  # Need enough data for indicators
            return None
            
        # Convert to numpy arrays for talib
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        volume = df['volume'].values
        
        indicators = {}
        
        try:
            # MACD
            macd, macd_signal, macd_hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
            indicators['macd'] = macd[-1] if not np.isnan(macd[-1]) else 0
            indicators['macd_signal'] = macd_signal[-1] if not np.isnan(macd_signal[-1]) else 0
            indicators['macd_hist'] = macd_hist[-1] if not np.isnan(macd_hist[-1]) else 0
            indicators['macd_bullish'] = indicators['macd'] > indicators['macd_signal']
            
            # RSI
            rsi = talib.RSI(close, timeperiod=14)
            indicators['rsi'] = rsi[-1] if not np.isnan(rsi[-1]) else 50
            indicators['rsi_oversold'] = indicators['rsi'] < 30
            indicators['rsi_overbought'] = indicators['rsi'] > 70
            indicators['rsi_bullish'] = 30 < indicators['rsi'] < 70 and indicators['rsi'] > 50
            
            # ADX (Average Directional Index)
            adx = talib.ADX(high, low, close, timeperiod=14)
            indicators['adx'] = adx[-1] if not np.isnan(adx[-1]) else 0
            indicators['adx_strong'] = indicators['adx'] > 25  # Strong trend
            
            # Plus/Minus DI for trend direction
            plus_di = talib.PLUS_DI(high, low, close, timeperiod=14)
            minus_di = talib.MINUS_DI(high, low, close, timeperiod=14)
            indicators['plus_di'] = plus_di[-1] if not np.isnan(plus_di[-1]) else 0
            indicators['minus_di'] = minus_di[-1] if not np.isnan(minus_di[-1]) else 0
            indicators['di_bullish'] = indicators['plus_di'] > indicators['minus_di']
            
            # Bollinger Bands
            bb_upper, bb_middle, bb_lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
            indicators['bb_upper'] = bb_upper[-1] if not np.isnan(bb_upper[-1]) else close[-1]
            indicators['bb_lower'] = bb_lower[-1] if not np.isnan(bb_lower[-1]) else close[-1]
            indicators['bb_squeeze'] = (bb_upper[-1] - bb_lower[-1]) / close[-1] < 0.1  # Tight squeeze
            
            # Volume indicators
            indicators['volume_avg'] = np.mean(volume[-20:]) if len(volume) >= 20 else volume[-1]
            indicators['volume_surge'] = volume[-1] > indicators['volume_avg'] * 1.5
            
            # Price action
            indicators['price_change'] = (close[-1] - close[-2]) / close[-2] * 100 if len(close) > 1 else 0
            indicators['near_high'] = close[-1] > np.max(high[-20:]) * 0.98  # Within 2% of 20-day high
            
        except Exception as e:
            print(f"Error calculating indicators: {e}")
            return None
            
        return indicators
    
    def detect_candlestick_patterns(self, df):
        """Detect bullish candlestick patterns"""
        if len(df) < 10:
            return {}
            
        open_prices = df['open'].values
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        patterns = {}
        
        try:
            # Hammer
            hammer = talib.CDLHAMMER(open_prices, high, low, close)
            patterns['hammer'] = hammer[-1] > 0
            
            # Doji
            doji = talib.CDLDOJI(open_prices, high, low, close)
            patterns['doji'] = doji[-1] != 0
            
            # Bullish Engulfing
            engulfing = talib.CDLENGULFING(open_prices, high, low, close)
            patterns['bullish_engulfing'] = engulfing[-1] > 0
            
            # Morning Star
            morning_star = talib.CDLMORNINGSTAR(open_prices, high, low, close)
            patterns['morning_star'] = morning_star[-1] > 0
            
            # Piercing Pattern
            piercing = talib.CDLPIERCING(open_prices, high, low, close)
            patterns['piercing'] = piercing[-1] > 0
            
            # Three White Soldiers
            three_white = talib.CDL3WHITESOLDIERS(open_prices, high, low, close)
            patterns['three_white_soldiers'] = three_white[-1] > 0
            
            # Any bullish pattern
            patterns['any_bullish'] = any([
                patterns['hammer'], 
                patterns['bullish_engulfing'], 
                patterns['morning_star'],
                patterns['piercing'],
                patterns['three_white_soldiers']
            ])
            
        except Exception as e:
            print(f"Error detecting patterns: {e}")
            
        return patterns
    
    def score_momentum_breakout(self, indicators, patterns):
        """Score the momentum breakout potential (0-100)"""
        score = 0
        signals = []
        
        if not indicators:
            return 0, ["No indicator data"]
        
        # MACD signals (20 points max)
        if indicators['macd_bullish']:
            score += 10
            signals.append("MACD bullish cross")
        if indicators['macd_hist'] > 0:
            score += 5
            signals.append("MACD histogram positive")
        if indicators.get('macd', 0) > 0:
            score += 5
            signals.append("MACD above zero")
        
        # RSI signals (15 points max)
        if indicators['rsi_bullish']:
            score += 10
            signals.append("RSI bullish zone")
        elif not indicators['rsi_overbought']:
            score += 5
            signals.append("RSI not overbought")
        
        # ADX signals (20 points max)
        if indicators['adx_strong'] and indicators['di_bullish']:
            score += 15
            signals.append("Strong bullish trend (ADX)")
        elif indicators['di_bullish']:
            score += 10
            signals.append("Bullish direction (DI)")
        elif indicators['adx_strong']:
            score += 5
            signals.append("Strong trend")
        
        # Volume signals (15 points max)
        if indicators['volume_surge']:
            score += 15
            signals.append("Volume surge")
        
        # Price action (20 points max)
        if indicators['near_high']:
            score += 10
            signals.append("Near 20-day high")
        if indicators['price_change'] > 2:
            score += 10
            signals.append("Strong price move")
        
        # Candlestick patterns (10 points max)
        if patterns.get('any_bullish', False):
            score += 10
            pattern_names = [k for k, v in patterns.items() if v and k != 'any_bullish']
            signals.append(f"Bullish pattern: {', '.join(pattern_names)}")
        
        return min(score, 100), signals
    
    async def analyze_stock(self, symbol):
        """Analyze a single stock for momentum breakout"""
        try:
            # Create contract
            contract = Stock(symbol, 'SMART', 'USD')
            
            # Get historical data (need enough for indicators)
            bars = await self.ib.reqHistoricalDataAsync(
                contract, 
                endDateTime='', 
                durationStr='60 D',
                barSizeSetting='1 day', 
                whatToShow='TRADES', 
                useRTH=True
            )
            
            if not bars:
                return None
                
            # Convert to DataFrame
            df = util.df(bars)
            
            # Calculate indicators
            indicators = self.calculate_technical_indicators(df)
            patterns = self.detect_candlestick_patterns(df)
            
            if not indicators:
                return None
            
            # Score momentum
            score, signals = self.score_momentum_breakout(indicators, patterns)
            
            # Get current price
            current_price = df['close'].iloc[-1]
            
            return {
                'symbol': symbol,
                'price': current_price,
                'score': score,
                'signals': signals,
                'rsi': indicators['rsi'],
                'adx': indicators['adx'],
                'macd': indicators['macd'],
                'volume_ratio': indicators.get('volume_surge', False),
                'patterns': [k for k, v in patterns.items() if v and k != 'any_bullish']
            }
            
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")
            return None

def print_results(results, min_score=50):
    """Print formatted results"""
    print("\n" + "="*80)
    print("MOMENTUM BREAKOUT SCANNER RESULTS")
    print("="*80)
    print(f"{'Rank':<4} {'Symbol':<8} {'Price':<8} {'Score':<6} {'RSI':<6} {'ADX':<6} {'Signals'}")
    print("-"*80)
    
    # Filter and sort by score
    filtered = [r for r in results if r and r['score'] >= min_score]
    sorted_results = sorted(filtered, key=lambda x: x['score'], reverse=True)
    
    for i, result in enumerate(sorted_results[:20], 1):  # Top 20
        signals_str = ', '.join(result['signals'][:3])  # First 3 signals
        if len(result['signals']) > 3:
            signals_str += "..."
            
        print(f"{i:<4} {result['symbol']:<8} ${result['price']:<7.2f} {result['score']:<6} "
              f"{result['rsi']:<6.1f} {result['adx']:<6.1f} {signals_str}")
    
    print(f"\nFound {len(sorted_results)} stocks with score >= {min_score}")

async def scan_momentum_breakouts(symbols, ib_client, min_score=50):
    """Scan multiple symbols for momentum breakouts"""
    scanner = MomentumScanner(ib_client)
    
    print(f"Scanning {len(symbols)} symbols for momentum breakouts...")
    
    # Analyze stocks in batches to avoid overwhelming the API
    batch_size = 5
    results = []
    
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        print(f"Processing batch {i//batch_size + 1}: {', '.join(batch)}")
        
        # Process batch concurrently
        tasks = [scanner.analyze_stock(symbol) for symbol in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and None results
        valid_results = [r for r in batch_results if isinstance(r, dict)]
        results.extend(valid_results)
        
        # Small delay between batches
        await asyncio.sleep(1)
    
    return results

def get_default_watchlist():
    """Get a default list of popular stocks to scan"""
    return [
        # Tech giants
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA', 'AMD', 'INTC', 'CRM',
        # Growth stocks
        'NFLX', 'ROKU', 'SQ', 'PYPL', 'SNOW', 'PLTR', 'COIN', 'RBLX', 'U', 'NET',
        # Traditional stocks
        'JPM', 'BAC', 'WMT', 'PG', 'JNJ', 'V', 'MA', 'DIS', 'KO', 'PEP',
        # Energy & Materials
        'XOM', 'CVX', 'OXY', 'COP', 'FCX', 'NEM', 'AA', 'X',
        # Biotech
        'MRNA', 'PFE', 'JNJ', 'ABBV', 'BMY', 'LLY', 'UNH', 'CVS'
    ]

async def main():
    parser = argparse.ArgumentParser(description="Momentum Breakout Scanner with Technical Indicators")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7496, help="7497 paper, 7496 live")
    parser.add_argument("--client-id", type=int, default=3)
    parser.add_argument("--symbols", nargs='+', help="Specific symbols to scan (optional)")
    parser.add_argument("--min-score", type=int, default=50, help="Minimum momentum score (0-100)")
    parser.add_argument("--min-price", type=float, default=5.0, help="Minimum stock price")
    args = parser.parse_args()
    
    # Connect to IB
    ib = IB()
    try:
        await ib.connectAsync(args.host, args.port, clientId=args.client_id)
        print(f"Connected to IB on {args.host}:{args.port}")
        
        # Get symbols to scan
        if args.symbols:
            symbols = args.symbols
        else:
            symbols = get_default_watchlist()
        
        # Run the scan
        results = await scan_momentum_breakouts(symbols, ib, args.min_score)
        
        # Print results
        print_results(results, args.min_score)
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    print("="*60)
    print("MOMENTUM BREAKOUT SCANNER")
    print("="*60)
    print("Analyzing stocks using MACD, RSI, ADX, and candlestick patterns")
    print("Requires: pip install talib-binary")
    print("="*60)
    
    asyncio.run(main())

