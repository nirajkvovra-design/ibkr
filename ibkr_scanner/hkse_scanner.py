"""
Enhanced Stock Scanner with Technical Analysis
==============================================

Extends the basic stock scanner with momentum breakout detection using:
- MACD crossovers
- RSI levels  
- ADX trend strength
- Volume analysis
- Simple candlestick patterns
"""

from ib_async import *
import pandas as pd
import numpy as np
import argparse
import json
import os

def get_bar_size_setting(interval):
    """Convert interval string to IB bar size setting"""
    interval_map = {
        '1min': '1 min',
        '3min': '3 mins', 
        '5min': '5 mins',
        '15min': '15 mins',
        '30min': '30 mins',
        '1hour': '1 hour',
        '2hour': '2 hours',
        '4hour': '4 hours',
        '1day': '1 day',
        '1week': '1 week'
    }
    
    if interval in interval_map:
        return interval_map[interval]
    else:
        available = ', '.join(interval_map.keys())
        raise ValueError(f"Invalid interval '{interval}'. Available: {available}")

def get_duration_for_interval(interval, min_bars=100):
    """Get appropriate duration string based on interval to ensure enough data"""
    # Map interval to recommended duration for sufficient data
    duration_map = {
        '1min': '3 D',      # 3 days for 1-minute bars
        '3min': '5 D',      # 5 days for 3-minute bars
        '5min': '10 D',     # 10 days for 5-minute bars
        '15min': '20 D',    # 20 days for 15-minute bars
        '30min': '30 D',    # 30 days for 30-minute bars
        '1hour': '60 D',    # 60 days for 1-hour bars
        '2hour': '120 D',   # 120 days for 2-hour bars
        '4hour': '240 D',   # 240 days for 4-hour bars
        '1day': '365 D',    # 1 year for daily bars
        '1week': '2 Y'      # 2 years for weekly bars
    }
    
    return duration_map.get(interval, '60 D')

def load_preset_config(preset_name):
    """Load preset configuration from JSON file"""
    try:
        with open('scanner_configs.json', 'r') as f:
            configs = json.load(f)
        
        if preset_name in configs:
            return configs[preset_name]
        else:
            available = ', '.join(configs.keys())
            raise ValueError(f"Preset '{preset_name}' not found. Available presets: {available}")
    
    except FileNotFoundError:
        raise FileNotFoundError("scanner_configs.json not found. Please ensure the config file exists.")
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON in scanner_configs.json")

def list_available_presets():
    """List all available preset configurations"""
    try:
        with open('scanner_configs.json', 'r') as f:
            configs = json.load(f)
        
        print("\nAvailable Preset Configurations:")
        print("=" * 50)
        for name, config in configs.items():
            print(f"{name:15} - {config.get('description', 'No description')}")
        print("=" * 50)
        
        return list(configs.keys())
    
    except FileNotFoundError:
        print("scanner_configs.json not found.")
        return []

def calculate_sma(prices, period):
    """Simple Moving Average"""
    return prices.rolling(window=period).mean()

def calculate_ema(prices, period):
    """Exponential Moving Average"""
    return prices.ewm(span=period).mean()

def calculate_rsi(prices, period=14):
    """Relative Strength Index"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_cci(high, low, close, period=14):   #default period was 20
    """Commodity Channel Index"""
    tp = (high + low + close) / 3  # Typical Price
    sma_tp = tp.rolling(window=period).mean()
    mad = tp.rolling(window=period).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    cci = (tp - sma_tp) / (0.015 * mad)
    return cci

def calculate_stochastic(high, low, close, k_period=14, d_period=3):
    """Stochastic Oscillator (%K and %D)"""
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    
    k_percent = 100 * (close - lowest_low) / (highest_high - lowest_low)
    d_percent = k_percent.rolling(window=d_period).mean()
    
    return k_percent, d_percent

def calculate_williams_r(high, low, close, period=14):
    """Williams %R"""
    highest_high = high.rolling(window=period).max()
    lowest_low = low.rolling(window=period).min()
    
    williams_r = -100 * (highest_high - close) / (highest_high - lowest_low)
    return williams_r

def calculate_bollinger_bands(close, period=20, std_dev=2):
    """Bollinger Bands"""
    sma = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    
    # Calculate position within bands (0 = lower band, 1 = upper band)
    bb_position = (close - lower_band) / (upper_band - lower_band)
    
    # Calculate band width (volatility measure)
    bb_width = (upper_band - lower_band) / sma
    
    return upper_band, sma, lower_band, bb_position, bb_width

def detect_trendline_breakouts(df, lookback_period=20):
    """Detect trendline breakouts using recent highs and lows"""
    if len(df) < lookback_period + 5:
        return {
            'resistance_breakout': False,
            'support_breakout': False,
            'resistance_rejection': False,
            'support_breakdown': False,
            'resistance_level': None,
            'support_level': None
        }
    
    high = df['high']
    low = df['low']
    close = df['close']
    volume = df['volume']
    
    # Get recent data for trendline calculation
    recent_data = df.tail(lookback_period)
    current_close = close.iloc[-1]
    current_volume = volume.iloc[-1]
    avg_volume = volume.tail(10).mean()
    
    # Find resistance level (recent highs)
    resistance_highs = recent_data['high'].nlargest(3)  # Top 3 highs
    resistance_level = resistance_highs.mean()
    
    # Find support level (recent lows)  
    support_lows = recent_data['low'].nsmallest(3)  # Bottom 3 lows
    support_level = support_lows.mean()
    
    # Check for breakouts with volume confirmation
    resistance_breakout = (
        current_close > resistance_level * 1.001 and  # Break above resistance
        current_volume > avg_volume * 1.2  # With volume
    )
    
    support_breakout = (
        current_close < support_level * 0.999 and  # Break below support
        current_volume > avg_volume * 1.2  # With volume (bearish)
    )
    
    # Check for rejections (failed breakouts)
    resistance_rejection = (
        high.iloc[-1] > resistance_level * 1.001 and  # Touched resistance
        current_close < resistance_level * 0.998 and  # Closed below resistance
        current_volume > avg_volume * 1.1  # With volume
    )
    
    support_breakdown = (
        low.iloc[-1] < support_level * 0.999 and  # Touched support
        current_close < support_level * 0.995 and  # Closed below support
        current_volume > avg_volume * 1.1  # With volume
    )
    
    return {
        'resistance_breakout': resistance_breakout,
        'support_breakout': support_breakout,
        'resistance_rejection': resistance_rejection,
        'support_breakdown': support_breakdown,
        'resistance_level': resistance_level,
        'support_level': support_level,
        'current_close': current_close,
        'volume_ratio': current_volume / avg_volume if avg_volume > 0 else 1
    }

def calculate_macd(prices, fast=7, slow=13, signal=4):   #default fast was 12, slow was 26, signal was 9
    """MACD indicator"""
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    macd = ema_fast - ema_slow
    macd_signal = calculate_ema(macd, signal)
    macd_histogram = macd - macd_signal
    return macd, macd_signal, macd_histogram

def calculate_adx(high, low, close, period=7):   #default period was 14
    """Simplified ADX calculation"""
    # Calculate True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Calculate directional movement
    dm_plus = np.where((high - high.shift(1)) > (low.shift(1) - low), 
                       np.maximum(high - high.shift(1), 0), 0)
    dm_minus = np.where((low.shift(1) - low) > (high - high.shift(1)), 
                        np.maximum(low.shift(1) - low, 0), 0)
    
    # Smooth the values
    tr_smooth = pd.Series(tr).rolling(window=period).mean()
    dm_plus_smooth = pd.Series(dm_plus).rolling(window=period).mean()
    dm_minus_smooth = pd.Series(dm_minus).rolling(window=period).mean()
    
    # Calculate DI+ and DI-
    di_plus = 100 * dm_plus_smooth / tr_smooth
    di_minus = 100 * dm_minus_smooth / tr_smooth
    
    # Calculate ADX
    dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus)
    adx = dx.rolling(window=period).mean()
    
    return adx, di_plus, di_minus

def detect_hammer(open_p, high, low, close):
    """Detect hammer candlestick pattern"""
    body = abs(close - open_p)
    upper_shadow = high - max(close, open_p)
    lower_shadow = min(close, open_p) - low
    
    # Hammer: small body, long lower shadow, small upper shadow
    return (lower_shadow > 2 * body) and (upper_shadow < body)

def detect_doji(open_p, high, low, close):
    """Detect doji candlestick pattern"""
    body = abs(close - open_p)
    total_range = high - low
    
    # Doji: very small body relative to range
    return body < 0.1 * total_range

def detect_engulfing(df):
    """Detect bullish engulfing pattern"""
    if len(df) < 2:
        return False
    
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    
    # Previous candle is bearish, current is bullish and engulfs previous
    prev_bearish = prev['close'] < prev['open']
    curr_bullish = curr['close'] > curr['open']
    engulfs = curr['open'] < prev['close'] and curr['close'] > prev['open']
    
    return prev_bearish and curr_bullish and engulfs

def analyze_momentum_breakout(df, settings):
    """Analyze stock for momentum breakout signals with custom settings"""
    min_data_points = max(settings['macd_slow'], settings['rsi_period'], 
                         settings['adx_period'], settings['cci_period'],
                         settings.get('stoch_k_period', 14), settings.get('williams_r_period', 14),
                         settings.get('bb_period', 20)) + 10
    
    if len(df) < min_data_points:  # Need enough data for all indicators
        return None
    
    close = df['close']
    high = df['high']
    low = df['low']
    open_p = df['open']
    volume = df['volume']
    
    # Calculate indicators with custom settings
    rsi = calculate_rsi(close, settings['rsi_period'])
    cci = calculate_cci(high, low, close, settings['cci_period'])
    macd, macd_signal, macd_hist = calculate_macd(close, settings['macd_fast'], 
                                                  settings['macd_slow'], settings['macd_signal'])
    adx, di_plus, di_minus = calculate_adx(high, low, close, settings['adx_period'])
    
    # Oscillator indicators
    stoch_k, stoch_d = calculate_stochastic(high, low, close, 
                                           settings.get('stoch_k_period', 14), 
                                           settings.get('stoch_d_period', 3))
    williams_r = calculate_williams_r(high, low, close, settings.get('williams_r_period', 14))
    
    # Bollinger Bands
    bb_upper, bb_sma, bb_lower, bb_position, bb_width = calculate_bollinger_bands(
        close, settings.get('bb_period', 20), settings.get('bb_std_dev', 2))
    
    # Trendline breakout analysis
    trendline_analysis = detect_trendline_breakouts(df, settings.get('trendline_lookback', 20))
    
    # Current values
    current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
    current_cci = cci.iloc[-1] if not pd.isna(cci.iloc[-1]) else 0
    current_macd = macd.iloc[-1] if not pd.isna(macd.iloc[-1]) else 0
    current_macd_signal = macd_signal.iloc[-1] if not pd.isna(macd_signal.iloc[-1]) else 0
    current_adx = adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 0
    current_di_plus = di_plus.iloc[-1] if not pd.isna(di_plus.iloc[-1]) else 0
    current_di_minus = di_minus.iloc[-1] if not pd.isna(di_minus.iloc[-1]) else 0
    current_stoch_k = stoch_k.iloc[-1] if not pd.isna(stoch_k.iloc[-1]) else 50
    current_stoch_d = stoch_d.iloc[-1] if not pd.isna(stoch_d.iloc[-1]) else 50
    current_williams_r = williams_r.iloc[-1] if not pd.isna(williams_r.iloc[-1]) else -50
    current_bb_position = bb_position.iloc[-1] if not pd.isna(bb_position.iloc[-1]) else 0.5
    current_bb_width = bb_width.iloc[-1] if not pd.isna(bb_width.iloc[-1]) else 0.1
    
    # Volume analysis
    avg_volume = volume.tail(20).mean()
    volume_surge = volume.iloc[-1] > avg_volume * 1.5
    
    # Price action
    recent_high = high.tail(20).max()
    near_high = close.iloc[-1] > recent_high * 0.98
    price_change = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100
    
    # Candlestick patterns
    hammer = detect_hammer(open_p.iloc[-1], high.iloc[-1], low.iloc[-1], close.iloc[-1])
    doji = detect_doji(open_p.iloc[-1], high.iloc[-1], low.iloc[-1], close.iloc[-1])
    engulfing = detect_engulfing(df.tail(2))
    
    # Score calculation (0-100) with custom thresholds
    score = 0
    signals = []
    
    # MACD signals (25 points)
    if current_macd > current_macd_signal:
        score += 15
        signals.append("MACD bullish")
    if current_macd > 0:
        score += 10
        signals.append("MACD positive")
    
    # RSI signals (20 points)
    if settings['rsi_oversold'] < current_rsi < settings['rsi_overbought']:
        score += 15
        signals.append("RSI favorable")
    if current_rsi > 50:
        score += 5
        signals.append("RSI bullish")
    
    # CCI signals (12 points)
    if settings['cci_oversold'] < current_cci < settings['cci_overbought']:
        score += 8
        signals.append("CCI favorable")
    if current_cci > 0:
        score += 4
        signals.append("CCI bullish")
    
    # Stochastic signals (12 points)
    stoch_oversold = settings.get('stoch_oversold', 20)
    stoch_overbought = settings.get('stoch_overbought', 80)
    if stoch_oversold < current_stoch_k < stoch_overbought:
        score += 8
        signals.append("Stoch favorable")
    if current_stoch_k > current_stoch_d:
        score += 4
        signals.append("Stoch bullish")
    
    # Williams %R signals (11 points)
    williams_oversold = settings.get('williams_oversold', -80)
    williams_overbought = settings.get('williams_overbought', -20)
    if williams_oversold < current_williams_r < williams_overbought:
        score += 7
        signals.append("Will%R favorable")
    if current_williams_r > -50:
        score += 4
        signals.append("Will%R bullish")
    
    # ADX signals (20 points)
    if current_adx > settings['adx_threshold']:
        score += 8
        signals.append("Strong trend")
    if current_di_plus > current_di_minus:
        score += 12
        signals.append("Bullish direction")
    
    # Bollinger Bands signals (12 points)
    if current_bb_position > 0.8:  # Near upper band
        score += 8
        signals.append("BB upper break")
    elif current_bb_position < 0.2:  # Near lower band - potential reversal
        score += 4
        signals.append("BB oversold")
    elif 0.3 < current_bb_position < 0.7:  # Middle range
        score += 2
        signals.append("BB neutral")
    
    # BB squeeze detection (low volatility = potential breakout)
    if current_bb_width < 0.05:  # Tight squeeze
        score += 6
        signals.append("BB squeeze")
    
    # Trendline breakout signals (15 points)
    if trendline_analysis['resistance_breakout']:
        score += 15
        signals.append("Resistance breakout")
    elif trendline_analysis['support_breakout']:
        score -= 10  # Bearish signal
        signals.append("Support breakdown")
    
    # Volume confirmation for breakouts
    volume_ratio = trendline_analysis.get('volume_ratio', 1)
    if volume_ratio > 1.5:
        score += 5
        signals.append("Volume confirmed")
    
    # Volume signals (12 points)
    if volume_surge:
        score += 12
        signals.append("Volume surge")
    
    # Price action (10 points)
    if near_high:
        score += 7
        signals.append("Near highs")
    if price_change > 2:
        score += 3
        signals.append("Strong move")
    
    # Patterns (bonus points)
    if hammer:
        score += 5
        signals.append("Hammer")
    if engulfing:
        score += 5
        signals.append("Engulfing")
    
    return {
        'score': min(score, 100),
        'signals': signals,
        'rsi': current_rsi,
        'cci': current_cci,
        'stoch_k': current_stoch_k,
        'williams_r': current_williams_r,
        'bb_position': current_bb_position,
        'bb_width': current_bb_width,
        'macd': current_macd,
        'adx': current_adx,
        'volume_surge': volume_surge,
        'near_high': near_high,
        'resistance_breakout': trendline_analysis['resistance_breakout'],
        'support_breakout': trendline_analysis['support_breakout'],
        'volume_ratio': volume_ratio
    }

def analyze_short_opportunities(df, settings):
    """Analyze stock for short opportunities with bearish signals"""
    min_data_points = max(settings['macd_slow'], settings['rsi_period'], 
                         settings['adx_period'], settings['cci_period'],
                         settings.get('stoch_k_period', 14), settings.get('williams_r_period', 14),
                         settings.get('bb_period', 20)) + 10
    
    if len(df) < min_data_points:
        return None
    
    close = df['close']
    high = df['high']
    low = df['low']
    open_p = df['open']
    volume = df['volume']
    
    # Calculate indicators with custom settings
    rsi = calculate_rsi(close, settings['rsi_period'])
    cci = calculate_cci(high, low, close, settings['cci_period'])
    macd, macd_signal, macd_hist = calculate_macd(close, settings['macd_fast'], 
                                                  settings['macd_slow'], settings['macd_signal'])
    adx, di_plus, di_minus = calculate_adx(high, low, close, settings['adx_period'])
    
    # Oscillator indicators
    stoch_k, stoch_d = calculate_stochastic(high, low, close, 
                                           settings.get('stoch_k_period', 14), 
                                           settings.get('stoch_d_period', 3))
    williams_r = calculate_williams_r(high, low, close, settings.get('williams_r_period', 14))
    
    # Bollinger Bands
    bb_upper, bb_sma, bb_lower, bb_position, bb_width = calculate_bollinger_bands(
        close, settings.get('bb_period', 20), settings.get('bb_std_dev', 2))
    
    # Trendline breakout analysis
    trendline_analysis = detect_trendline_breakouts(df, settings.get('trendline_lookback', 20))
    
    # Current values
    current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
    current_cci = cci.iloc[-1] if not pd.isna(cci.iloc[-1]) else 0
    current_macd = macd.iloc[-1] if not pd.isna(macd.iloc[-1]) else 0
    current_macd_signal = macd_signal.iloc[-1] if not pd.isna(macd_signal.iloc[-1]) else 0
    current_adx = adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 0
    current_di_plus = di_plus.iloc[-1] if not pd.isna(di_plus.iloc[-1]) else 0
    current_di_minus = di_minus.iloc[-1] if not pd.isna(di_minus.iloc[-1]) else 0
    current_stoch_k = stoch_k.iloc[-1] if not pd.isna(stoch_k.iloc[-1]) else 50
    current_stoch_d = stoch_d.iloc[-1] if not pd.isna(stoch_d.iloc[-1]) else 50
    current_williams_r = williams_r.iloc[-1] if not pd.isna(williams_r.iloc[-1]) else -50
    current_bb_position = bb_position.iloc[-1] if not pd.isna(bb_position.iloc[-1]) else 0.5
    current_bb_width = bb_width.iloc[-1] if not pd.isna(bb_width.iloc[-1]) else 0.1
    
    # Volume analysis
    avg_volume = volume.tail(20).mean()
    volume_surge = volume.iloc[-1] > avg_volume * 1.5
    
    # Price action
    recent_low = low.tail(20).min()
    near_low = close.iloc[-1] < recent_low * 1.02
    price_change = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100
    
    # Score calculation (0-100) for bearish signals
    score = 0
    signals = []
    
    # MACD signals (25 points) - Bearish
    if current_macd < current_macd_signal:
        score += 15
        signals.append("MACD bearish")
    if current_macd < 0:
        score += 10
        signals.append("MACD negative")
    
    # RSI signals (20 points) - Overbought
    if current_rsi > settings['rsi_overbought']:
        score += 15
        signals.append("RSI overbought")
    elif current_rsi > 70:
        score += 10
        signals.append("RSI high")
    elif current_rsi < 50:
        score += 5
        signals.append("RSI bearish")
    
    # CCI signals (12 points) - Overbought
    if current_cci > settings['cci_overbought']:
        score += 12
        signals.append("CCI overbought")
    elif current_cci > 100:
        score += 8
        signals.append("CCI high")
    elif current_cci < 0:
        score += 4
        signals.append("CCI bearish")
    
    # Stochastic signals (12 points) - Overbought
    stoch_oversold = settings.get('stoch_oversold', 20)
    stoch_overbought = settings.get('stoch_overbought', 80)
    if current_stoch_k > stoch_overbought:
        score += 12
        signals.append("Stoch overbought")
    elif current_stoch_k > 80:
        score += 8
        signals.append("Stoch high")
    elif current_stoch_k < current_stoch_d:
        score += 4
        signals.append("Stoch bearish")
    
    # Williams %R signals (11 points) - Overbought
    williams_oversold = settings.get('williams_oversold', -80)
    williams_overbought = settings.get('williams_overbought', -20)
    if current_williams_r > williams_overbought:
        score += 11
        signals.append("Will%R overbought")
    elif current_williams_r > -30:
        score += 7
        signals.append("Will%R high")
    elif current_williams_r < -50:
        score += 4
        signals.append("Will%R bearish")
    
    # ADX signals (20 points) - Bearish direction
    if current_adx > settings['adx_threshold']:
        score += 8
        signals.append("Strong trend")
    if current_di_minus > current_di_plus:
        score += 12
        signals.append("Bearish direction")
    
    # Bollinger Bands signals (12 points) - Upper band rejection
    if current_bb_position > 0.9:  # Near upper band
        score += 12
        signals.append("BB upper rejection")
    elif current_bb_position > 0.8:  # Upper band area
        score += 8
        signals.append("BB upper area")
    elif current_bb_position < 0.2:  # Lower band - avoid
        score -= 10
        signals.append("BB oversold")
    
    # Trendline breakdown signals (15 points)
    if trendline_analysis['support_breakout']:
        score += 15
        signals.append("Support breakdown")
    elif trendline_analysis['resistance_rejection']:
        score += 10
        signals.append("Resistance rejection")
    
    # Volume confirmation for breakdowns
    volume_ratio = trendline_analysis.get('volume_ratio', 1)
    if volume_ratio > 1.5:
        score += 5
        signals.append("Volume confirmed")
    
    # Volume signals (12 points) - Distribution
    if volume_surge:
        score += 8
        signals.append("Volume surge")
    if volume.iloc[-1] > volume.tail(5).mean() * 1.3:
        score += 4
        signals.append("Above avg volume")
    
    # Price action (10 points) - Bearish
    if near_low:
        score -= 5  # Near lows is bad for shorts
        signals.append("Near lows")
    if price_change < -2:
        score += 8
        signals.append("Strong decline")
    elif price_change < 0:
        score += 4
        signals.append("Declining")
    
    # Additional bearish patterns
    if detect_doji(open_p.iloc[-1], high.iloc[-1], low.iloc[-1], close.iloc[-1]):
        score += 3
        signals.append("Doji")
    
    # Check for bearish engulfing
    if len(df) >= 2:
        prev = df.iloc[-2]
        curr = df.iloc[-1]
        bearish_engulfing = (prev['close'] > prev['open'] and  # Previous bullish
                            curr['close'] < curr['open'] and    # Current bearish
                            curr['open'] > prev['close'] and    # Current opens above previous close
                            curr['close'] < prev['open'])       # Current closes below previous open
        if bearish_engulfing:
            score += 5
            signals.append("Bearish engulfing")
    
    return {
        'score': min(max(score, 0), 100),  # Clamp between 0-100
        'signals': signals,
        'rsi': current_rsi,
        'cci': current_cci,
        'stoch_k': current_stoch_k,
        'williams_r': current_williams_r,
        'bb_position': current_bb_position,
        'bb_width': current_bb_width,
        'macd': current_macd,
        'adx': current_adx,
        'volume_surge': volume_surge,
        'near_low': near_low,
        'support_breakout': trendline_analysis.get('support_breakout', False),
        'resistance_rejection': trendline_analysis.get('resistance_rejection', False),
        'volume_ratio': volume_ratio
    }

def print_technical_item(item, analysis, compact=True):
    """Print scan item with technical analysis"""
    cd = item.contractDetails
    c = cd.contract
    primary_exch = (
        getattr(c, "primaryExchange", "")
        or (cd.validExchanges.split(",")[0] if getattr(cd, "validExchanges", "") else "")
        or getattr(cd, "marketName", "")
    )
    
    if analysis:
        score = analysis['score']
        rsi = analysis['rsi']
        cci = analysis['cci']
        stoch_k = analysis['stoch_k']
        williams_r = analysis['williams_r']
        adx = analysis['adx']
        signals = ', '.join(analysis['signals'][:2])  # First 2 signals to fit width
        
        if compact:
            print(f"[{item.rank:>3}] {c.symbol:<8} Score:{score:>3} RSI:{rsi:>5.1f} Stoch:{stoch_k:>5.1f} Will%R:{williams_r:>6.1f} {signals}")
        else:
            print(f"[{item.rank:>3}] {c.symbol:<8} Score:{score:>3}")
            print(f"      RSI:{rsi:>5.1f} CCI:{cci:>6.1f} Stoch:{stoch_k:>5.1f} Will%R:{williams_r:>6.1f} ADX:{adx:>5.1f}")
            print(f"      Signals: {', '.join(analysis['signals'])}")
    else:
        print(f"[{item.rank:>3}] {c.symbol:<8} Score: -- RSI: --   Stoch: --  Will%R: --   Insufficient data")

def print_short_item(item, analysis, compact=True):
    """Print scan item with short opportunity analysis"""
    cd = item.contractDetails
    c = cd.contract
    primary_exch = (
        getattr(c, "primaryExchange", "")
        or (cd.validExchanges.split(",")[0] if getattr(cd, "validExchanges", "") else "")
        or getattr(cd, "marketName", "")
    )
    
    if analysis:
        score = analysis['score']
        rsi = analysis['rsi']
        cci = analysis['cci']
        stoch_k = analysis['stoch_k']
        williams_r = analysis['williams_r']
        adx = analysis['adx']
        signals = ', '.join(analysis['signals'][:2])  # First 2 signals to fit width
        
        if compact:
            print(f"[{item.rank:>3}] {c.symbol:<8} Score:{score:>3} RSI:{rsi:>5.1f} Stoch:{stoch_k:>5.1f} Will%R:{williams_r:>6.1f} {signals}")
        else:
            print(f"[{item.rank:>3}] {c.symbol:<8} Score:{score:>3}")
            print(f"      RSI:{rsi:>5.1f} CCI:{cci:>6.1f} Stoch:{stoch_k:>5.1f} Will%R:{williams_r:>6.1f} ADX:{adx:>5.1f}")
            print(f"      Signals: {', '.join(analysis['signals'])}")
    else:
        print(f"[{item.rank:>3}] {c.symbol:<8} Score: -- RSI: --   Stoch: --  Will%R: --   Insufficient data")

def main():
    parser = argparse.ArgumentParser(description="Customizable Technical Analysis HKSE Stock Scanner for Long & Short Opportunities",
                                   formatter_class=argparse.RawDescriptionHelpFormatter,
                                   epilog="""
INDICATOR CUSTOMIZATION EXAMPLES:
  Default settings:     python hkse_scanner.py
  Fast MACD:           python hkse_scanner.py --macd-fast 8 --macd-slow 21 --macd-signal 5
  Sensitive RSI:       python hkse_scanner.py --rsi-period 9 --rsi-oversold 25 --rsi-overbought 75
  Strict ADX:          python hkse_scanner.py --adx-period 10 --adx-threshold 30
  Conservative CCI:    python hkse_scanner.py --cci-period 30 --cci-oversold -150 --cci-overbought 150
  
POPULAR SETTINGS COMBINATIONS:
  Day Trading:         --macd-fast 5 --macd-slow 13 --rsi-period 9 --adx-threshold 30
  Swing Trading:       --macd-fast 12 --macd-slow 26 --rsi-period 14 --adx-threshold 25
  Position Trading:    --macd-fast 19 --macd-slow 39 --rsi-period 21 --adx-threshold 20

OUTPUT:
  The scanner now provides TWO lists:
  1. LONG OPPORTUNITIES: HKSE stocks with bullish momentum signals
  2. SHORT OPPORTUNITIES: HKSE stocks with bearish reversal signals

USAGE:
  python hkse_scanner.py                    # Basic HKSE scan
  python hkse_scanner.py --max-results 20  # More results
  python hkse_scanner.py --min-score 70    # Higher quality signals
""")
    
    # Preset configuration
    parser.add_argument("--preset", type=str, help="Load preset configuration (day_trading, swing_trading, position_trading, crypto_style, conservative)")
    parser.add_argument("--list-presets", action="store_true", help="List available preset configurations and exit")
    
    # Connection settings
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7497, help="7497 paper, 7496 live")
    parser.add_argument("--client-id", type=int, default=4)
    
    # Scanner settings
    parser.add_argument("--instrument", default="STK")

    parser.add_argument("--scan-code", default="MOST_ACTIVE",
                        help="Examples: TOP_PERC_GAIN, MOST_ACTIVE, HOT_BY_VOLUME")
    parser.add_argument("--min-price", type=float, default=5.0,
                        help="Minimum stock price")
    parser.add_argument("--min-score", type=int, default=50,
                        help="Minimum momentum score (0-100)")
    parser.add_argument("--max-results", type=int, default=20,
                        help="Maximum number of results to analyze")
    

    
    # Chart settings CHANGE CHART INTERVAL HERE
    chart_group = parser.add_argument_group('Chart Settings')
    chart_group.add_argument("--interval", default="30min",
                           help="Chart interval: 1min, 3min, 5min, 15min, 30min, 1hour, 2hour, 4hour, 1day, 1week (default: 1day)")
    chart_group.add_argument("--custom-duration", type=str,
                           help="Custom duration string (e.g., '30 D', '2 Y'). Overrides auto-duration based on interval")
    
    # MACD Settings
    macd_group = parser.add_argument_group('MACD Settings')
    macd_group.add_argument("--macd-fast", type=int, default=12,
                           help="MACD fast EMA period (default: 12)")
    macd_group.add_argument("--macd-slow", type=int, default=26,
                           help="MACD slow EMA period (default: 26)")
    macd_group.add_argument("--macd-signal", type=int, default=9,
                           help="MACD signal line period (default: 9)")
    
    # RSI Settings
    rsi_group = parser.add_argument_group('RSI Settings')
    rsi_group.add_argument("--rsi-period", type=int, default=14,
                          help="RSI calculation period (default: 14)")
    rsi_group.add_argument("--rsi-oversold", type=float, default=30,
                          help="RSI oversold threshold (default: 30)")
    rsi_group.add_argument("--rsi-overbought", type=float, default=70,
                          help="RSI overbought threshold (default: 70)")
    
    # CCI Settings
    cci_group = parser.add_argument_group('CCI Settings')
    cci_group.add_argument("--cci-period", type=int, default=20,
                          help="CCI calculation period (default: 20)")
    cci_group.add_argument("--cci-oversold", type=float, default=-100,
                          help="CCI oversold threshold (default: -100)")
    cci_group.add_argument("--cci-overbought", type=float, default=100,
                          help="CCI overbought threshold (default: 100)")
    
    # ADX Settings
    adx_group = parser.add_argument_group('ADX Settings')
    adx_group.add_argument("--adx-period", type=int, default=14,
                          help="ADX calculation period (default: 14)")
    adx_group.add_argument("--adx-threshold", type=float, default=25,
                          help="ADX strong trend threshold (default: 25)")
    
    # Stochastic Settings
    stoch_group = parser.add_argument_group('Stochastic Settings')
    stoch_group.add_argument("--stoch-k-period", type=int, default=14,
                           help="Stochastic %%K period (default: 14)")
    stoch_group.add_argument("--stoch-d-period", type=int, default=3,
                           help="Stochastic %%D period (default: 3)")
    stoch_group.add_argument("--stoch-oversold", type=float, default=20,
                           help="Stochastic oversold threshold (default: 20)")
    stoch_group.add_argument("--stoch-overbought", type=float, default=80,
                           help="Stochastic overbought threshold (default: 80)")
    
    # Williams %R Settings
    williams_group = parser.add_argument_group('Williams %R Settings')
    williams_group.add_argument("--williams-r-period", type=int, default=14,
                              help="Williams %%R period (default: 14)")
    williams_group.add_argument("--williams-oversold", type=float, default=-80,
                              help="Williams %%R oversold threshold (default: -80)")
    williams_group.add_argument("--williams-overbought", type=float, default=-20,
                              help="Williams %%R overbought threshold (default: -20)")
    
    # Bollinger Bands Settings
    bb_group = parser.add_argument_group('Bollinger Bands Settings')
    bb_group.add_argument("--bb-period", type=int, default=20,
                         help="Bollinger Bands period (default: 20)")
    bb_group.add_argument("--bb-std-dev", type=float, default=2.0,
                         help="Bollinger Bands standard deviations (default: 2.0)")
    
    # Trendline Settings
    trendline_group = parser.add_argument_group('Trendline Settings')
    trendline_group.add_argument("--trendline-lookback", type=int, default=20,
                               help="Trendline lookback period (default: 20)")
    
    # Display options
    display_group = parser.add_argument_group('Display Options')
    display_group.add_argument("--verbose", action="store_true",
                             help="Show detailed indicator values for each stock")
    
    args = parser.parse_args()
    
    # Handle preset listing
    if args.list_presets:
        list_available_presets()
        return
    
    # Load preset configuration if specified
    if args.preset:
        try:
            preset_config = load_preset_config(args.preset)
            print(f"Loading preset configuration: {args.preset}")
            print(f"Description: {preset_config.get('description', 'No description')}")
        except (FileNotFoundError, ValueError) as e:
            print(f"Error loading preset: {e}")
            return
    else:
        preset_config = {}
    
    # Create settings dictionary (preset values override defaults, command line overrides preset)
    settings = {
        'macd_fast': getattr(args, 'macd_fast', None) or preset_config.get('macd_fast', 12),
        'macd_slow': getattr(args, 'macd_slow', None) or preset_config.get('macd_slow', 26),
        'macd_signal': getattr(args, 'macd_signal', None) or preset_config.get('macd_signal', 9),
        'rsi_period': getattr(args, 'rsi_period', None) or preset_config.get('rsi_period', 14),
        'rsi_oversold': getattr(args, 'rsi_oversold', None) or preset_config.get('rsi_oversold', 30),
        'rsi_overbought': getattr(args, 'rsi_overbought', None) or preset_config.get('rsi_overbought', 70),
        'cci_period': getattr(args, 'cci_period', None) or preset_config.get('cci_period', 20),
        'cci_oversold': getattr(args, 'cci_oversold', None) or preset_config.get('cci_oversold', -100),
        'cci_overbought': getattr(args, 'cci_overbought', None) or preset_config.get('cci_overbought', 100),
        'adx_period': getattr(args, 'adx_period', None) or preset_config.get('adx_period', 14),
        'adx_threshold': getattr(args, 'adx_threshold', None) or preset_config.get('adx_threshold', 25),
        'stoch_k_period': getattr(args, 'stoch_k_period', None) or preset_config.get('stoch_k_period', 14),
        'stoch_d_period': getattr(args, 'stoch_d_period', None) or preset_config.get('stoch_d_period', 3),
        'stoch_oversold': getattr(args, 'stoch_oversold', None) or preset_config.get('stoch_oversold', 20),
        'stoch_overbought': getattr(args, 'stoch_overbought', None) or preset_config.get('stoch_overbought', 80),
        'williams_r_period': getattr(args, 'williams_r_period', None) or preset_config.get('williams_r_period', 14),
        'williams_oversold': getattr(args, 'williams_oversold', None) or preset_config.get('williams_oversold', -80),
        'williams_overbought': getattr(args, 'williams_overbought', None) or preset_config.get('williams_overbought', -20),
        'bb_period': getattr(args, 'bb_period', None) or preset_config.get('bb_period', 20),
        'bb_std_dev': getattr(args, 'bb_std_dev', None) or preset_config.get('bb_std_dev', 2.0),
        'trendline_lookback': getattr(args, 'trendline_lookback', None) or preset_config.get('trendline_lookback', 20)
    }
    
    # Validate and get chart settings
    try:
        bar_size = get_bar_size_setting(args.interval)
        duration = args.custom_duration if args.custom_duration else get_duration_for_interval(args.interval)
    except ValueError as e:
        print(f"Error: {e}")
        return

    ib = IB()
    ib.connect(args.host, args.port, clientId=args.client_id)
    
    print("="*90)
    print("HONG KONG STOCK EXCHANGE TECHNICAL SCANNER - LONG & SHORT OPPORTUNITIES")
    print("="*90)
    print(f"Chart: {args.interval} | Duration: {duration}")
    print(f"MACD: {settings['macd_fast']}/{settings['macd_slow']}/{settings['macd_signal']} | " +
          f"RSI: {settings['rsi_period']} ({settings['rsi_oversold']}-{settings['rsi_overbought']}) | " +
          f"BB: {settings['bb_period']}/{settings['bb_std_dev']}σ | " +
          f"ADX: {settings['adx_period']} (>{settings['adx_threshold']})")
    print(f"Stoch: {settings['stoch_k_period']}/{settings['stoch_d_period']} | " +
          f"Williams %R: {settings['williams_r_period']} | " +
          f"Trendlines: {settings['trendline_lookback']} bars")
    print("="*90)

    # Create HKSE scanner subscription - try multiple location codes
    hkse_locations = ["STK.HK.SEHK", "STK.HK", "STK.HKSE", "STK.HONGKONG", "STK.ASIA"]
    
    items = []
    working_location = None
    
    for location in hkse_locations:
        try:
            print(f"Trying HKSE location code: {location}")
            sub = ScannerSubscription(
                instrument=args.instrument,
                locationCode=location,
                scanCode=args.scan_code
            )
            
            if args.min_price:
                sub.abovePrice = args.min_price
            
            # Test this location
            test_items = ib.reqScannerData(sub)
            if len(test_items) > 0:
                items = test_items
                working_location = location
                print(f"✅ Success! Found {len(items)} stocks with location: {location}")
                break
            else:
                print(f"  ⚠️  Location {location} returned 0 stocks")
        except Exception as e:
            print(f"  ❌ Location {location} failed: {str(e)[:100]}")
    
    if not working_location:
        print("\n❌ All HKSE location codes failed!")
        print("This means:")
        print("  - Your IB account may not have HKSE market data access")
        print("  - HKSE scanner service may not be enabled")
        print("  - Market may be closed (HKSE hours: 9:30 AM - 4:00 PM HKT)")
        print("  - Try using the US scanner instead: python technical_scanner.py")
        return
    
    print(f"\nScanner criteria: {args.scan_code}")
    if args.min_price:
        print(f"Minimum price filter: ${args.min_price}")

    # Get scan results for HKSE stocks (already obtained above)
    
    print(f"\nFound {len(items)} total HKSE stocks from scanner")
    if len(items) == 0:
        print("⚠️  WARNING: No HKSE stocks returned from scanner!")
        print("This could mean:")
        print("  - No HKSE stocks meet the scanner criteria")
        print("  - Scanner location code 'STK.HK.MAIN' is incorrect")
        print("  - Market is closed or no data available")
        print("  - Scanner subscription needs different parameters")
        return
    
    print(f"Analyzing top {min(len(items), args.max_results)} HKSE stocks...")
    if args.verbose:
        print("Detailed Analysis Mode:")
        print("-" * 90)
    else:
        print(f"{'Rank':<5} {'Symbol':<8} {'Score':<7} {'RSI':<9} {'Stoch':<9} {'Will%R':<10} {'Signals'}")
        print("-" * 90)
    
    qualified_stocks = []
    short_opportunities = []
    
    # Analyze each HKSE stock for both long and short opportunities
    for i, item in enumerate(items[:args.max_results]):
        try:
            # Create HKSE contract
            contract = Stock(item.contractDetails.contract.symbol, 'SEHK', 'HKD')
            
            # Get historical data with custom interval
            bars = ib.reqHistoricalData(
                contract, 
                endDateTime='', 
                durationStr=duration,
                barSizeSetting=bar_size, 
                whatToShow='TRADES', 
                useRTH=True
            )
            
            if bars:
                df = util.df(bars)
                
                # Analyze for long opportunities
                long_analysis = analyze_momentum_breakout(df, settings)
                
                # Analyze for short opportunities
                short_analysis = analyze_short_opportunities(df, settings)
                
                # Print long analysis
                print_technical_item(item, long_analysis, compact=not args.verbose)
                
                # Collect qualified long stocks
                if long_analysis and long_analysis['score'] >= args.min_score:
                    qualified_stocks.append({
                        'symbol': item.contractDetails.contract.symbol,
                        'rank': item.rank,
                        'score': long_analysis['score'],
                        'signals': long_analysis['signals']
                    })
                elif long_analysis:
                    print(f"  📊 {item.contractDetails.contract.symbol}: Long score {long_analysis['score']} (below threshold {args.min_score})")
                
                # Collect qualified short opportunities
                if short_analysis and short_analysis['score'] >= args.min_score:
                    short_opportunities.append({
                        'symbol': item.contractDetails.contract.symbol,
                        'rank': item.rank,
                        'score': short_analysis['score'],
                        'signals': short_analysis['signals']
                    })
                elif short_analysis:
                    print(f"  📊 {item.contractDetails.contract.symbol}: Short score {short_analysis['score']} (below threshold {args.min_score})")
            else:
                print_technical_item(item, None)
                
        except Exception as e:
            print(f"[{item.rank:>3}] {item.contractDetails.contract.symbol:<8} Error: {str(e)[:50]}")
    
    # Filter out stocks that appear in both lists (conflicting signals)
    long_symbols = {stock['symbol'] for stock in qualified_stocks}
    short_symbols = {stock['symbol'] for stock in short_opportunities}
    conflicting_symbols = long_symbols.intersection(short_symbols)
    
    # Remove conflicting stocks from both lists
    qualified_stocks = [stock for stock in qualified_stocks if stock['symbol'] not in conflicting_symbols]
    short_opportunities = [stock for stock in short_opportunities if stock['symbol'] not in conflicting_symbols]
    
    # Summary
    print("\n" + "="*90)
    print(f"SCAN SUMMARY:")
    print(f"  Total HKSE stocks scanned: {len(items)}")
    print(f"  Stocks with long analysis: {len([s for s in items if s])}")
    print(f"  Stocks with short analysis: {len([s for s in items if s])}")
    print(f"  Long opportunities found: {len(qualified_stocks)}")
    print(f"  Short opportunities found: {len(short_opportunities)}")
    print("="*90)
    
    print(f"\nQUALIFIED LONG OPPORTUNITIES (Score >= {args.min_score}) - EXCLUDING CONFLICTING SIGNALS")
    print("="*90)
    
    if qualified_stocks:
        for stock in sorted(qualified_stocks, key=lambda x: x['score'], reverse=True):
            signals_str = ', '.join(stock['signals'][:4])
            print(f"{stock['symbol']:<8} Score: {stock['score']:>3} - {signals_str}")
    else:
        print("No HKSE stocks met the minimum long momentum score criteria.")
    
    print("\n" + "="*90)
    print(f"QUALIFIED SHORT OPPORTUNITIES (Score >= {args.min_score})")
    print("="*90)
    
    if short_opportunities:
        for stock in sorted(short_opportunities, key=lambda x: x['score'], reverse=True):
            signals_str = ', '.join(stock['signals'][:4])
            print(f"{stock['symbol']:<8} Score: {stock['score']:>3} - {signals_str}")
    else:
        print("No HKSE stocks met the minimum short opportunity score criteria.")
    
    # Show excluded stocks with conflicting signals
    if conflicting_symbols:
        print("\n" + "="*90)
        print(f"EXCLUDED STOCKS WITH CONFLICTING SIGNALS ({len(conflicting_symbols)} stocks)")
        print("="*90)
        print("These HKSE stocks showed both long and short signals and were excluded for clarity.")
        print("Consider waiting for clearer directional signals before trading these stocks.")
        print("-" * 90)
        for symbol in sorted(conflicting_symbols):
            print(f"{symbol}")
    else:
        print("\n" + "="*90)
        print("NO CONFLICTING SIGNALS DETECTED")
        print("="*90)
        print("All qualified HKSE stocks showed clear directional signals.")
    
    ib.disconnect()

if __name__ == "__main__":
    main()
