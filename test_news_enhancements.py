#!/usr/bin/env python
"""
Test script for enhanced news sentiment analysis features
Demonstrates:
1. Enhanced sentiment analysis
2. Earnings announcement detection
3. Market news filtering by watchlist
"""

import sys
# Configure standard streams to support UTF-8 on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from news_sentiment import NewsSentiment
from stock_screener import StockScreener
from utils import get_logger
from datetime import datetime
import json

logger = get_logger(__name__)

def test_enhanced_sentiment():
    """Test enhanced sentiment analysis"""
    print("\n" + "="*60)
    print("TEST 1: Enhanced Sentiment Analysis")
    print("="*60)
    
    analyzer = NewsSentiment()
    
    test_texts = [
        "Apple beats earnings expectations with strong revenue growth",
        "Microsoft faces decline as competition intensifies in cloud market",
        "NVIDIA announces breakthrough AI chip with record performance",
        "Tesla misses guidance and cuts capex spending significantly",
    ]
    
    for text in test_texts:
        score = analyzer.analyze_sentiment(text)
        sentiment = 'BULLISH' if score > 0.2 else 'BEARISH' if score < -0.2 else 'NEUTRAL'
        print(f"  Text: {text[:60]}...")
        print(f"    Score: {score:.3f} | Sentiment: {sentiment}\n")

def test_earnings_detection():
    """Test earnings announcement detection"""
    print("\n" + "="*60)
    print("TEST 2: Earnings Announcement Detection")
    print("="*60)
    
    analyzer = NewsSentiment()
    
    test_articles = [
        {'title': 'Apple Beats Q2 Earnings Expectations', 'published': '2026-05-22'},
        {'title': 'Microsoft Misses Revenue Estimates in Q1 Report', 'published': '2026-05-22'},
        {'title': 'NVIDIA In-Line Results Show Steady Growth', 'published': '2026-05-22'},
        {'title': 'Tesla Acquires Autonomous Driving Startup', 'published': '2026-05-22'},
    ]
    
    for article in test_articles:
        is_earnings, direction, impact = analyzer.detect_earnings_announcement(article)
        print(f"  Article: {article['title']}")
        print(f"    Is Earnings: {is_earnings}")
        print(f"    Direction: {direction}")
        print(f"    Impact Score: {impact:.3f}\n")

def test_watchlist_filtering():
    """Test market news filtering by watchlist"""
    print("\n" + "="*60)
    print("TEST 3: Market News Filtering by Watchlist")
    print("="*60)
    
    analyzer = NewsSentiment()
    
    # Sample watchlist
    watchlist = ['AAPL', 'MSFT', 'NVDA', 'TSLA']
    
    print(f"  Watchlist: {', '.join(watchlist)}")
    print(f"  Fetching news for each symbol...\n")
    
    try:
        # Get watchlist news
        watchlist_news = analyzer.get_watchlist_news(watchlist, limit=10)
        
        print(f"  Found {len(watchlist_news)} relevant news items:\n")
        for i, news in enumerate(watchlist_news[:5], 1):
            print(f"  {i}. [{news['symbol']}] {news['title'][:70]}")
            print(f"     Sentiment: {news['sentiment']} (Score: {news['sentiment_score']:.3f})")
            if news['is_earnings']:
                print(f"     📊 EARNINGS - Direction: {news['earnings_direction']}")
            print()
    
    except Exception as e:
        print(f"  Note: Live news fetch may fail if markets are closed or API issues")
        print(f"  Error: {e}\n")

def test_watchlist_sentiment_summary():
    """Test watchlist sentiment summary"""
    print("\n" + "="*60)
    print("TEST 4: Watchlist Sentiment Summary")
    print("="*60)
    
    analyzer = NewsSentiment()
    
    watchlist = ['AAPL', 'MSFT', 'NVDA']
    
    print(f"  Analyzing watchlist: {', '.join(watchlist)}\n")
    
    try:
        summary = analyzer.get_watchlist_sentiment_summary(watchlist)
        
        print(f"  Sentiment Summary:")
        print(f"    {summary['summary']}")
        print(f"    Bullish Percent: {summary['bullish_percent']:.1f}%")
        print(f"\n  Individual Sentiments:")
        for symbol, sentiment in summary['sentiments'].items():
            print(f"    {symbol}: {sentiment}")
        
        if summary.get('earnings_upcoming'):
            print(f"\n  Upcoming Earnings:")
            for symbol, earnings_list in summary['earnings_upcoming'].items():
                print(f"    {symbol}: {len(earnings_list)} announcement(s)")
    
    except Exception as e:
        print(f"  Note: Summary may be limited if markets are closed")
        print(f"  Error: {e}\n")

def test_news_alerts():
    """Test news alert generation"""
    print("\n" + "="*60)
    print("TEST 5: News Alert Generation")
    print("="*60)
    
    analyzer = NewsSentiment()
    
    watchlist = ['AAPL', 'MSFT', 'NVDA']
    
    print(f"  Checking for alerts in watchlist: {', '.join(watchlist)}\n")
    
    try:
        alerts = analyzer.generate_news_alerts(watchlist, alert_threshold=0.7)
        
        if alerts:
            print(f"  Found {len(alerts)} alert(s):\n")
            for alert in alerts:
                print(f"  ⚠️  {alert['symbol']} - {alert['type']} ({alert['severity']})")
                print(f"     {alert['title'][:70]}")
                print()
        else:
            print("  No critical alerts generated\n")
    
    except Exception as e:
        print(f"  Note: Alerts depend on market data availability")
        print(f"  Error: {e}\n")

def test_earnings_blackout():
    """Test earnings blackout checking"""
    print("\n" + "="*60)
    print("TEST 6: Earnings Blackout Check")
    print("="*60)
    
    analyzer = NewsSentiment()
    
    test_symbols = ['AAPL', 'MSFT', 'GOOGL']
    
    print(f"  Checking earnings blackout for: {', '.join(test_symbols)}\n")
    
    for symbol in test_symbols:
        try:
            in_blackout = analyzer.check_earnings_blackout(symbol)
            status = "🚫 IN BLACKOUT" if in_blackout else "✓ Safe to trade"
            print(f"  {symbol}: {status}")
        except Exception as e:
            print(f"  {symbol}: Error - {e}")
    
    print()

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("ENHANCED NEWS SENTIMENT ANALYSIS - FEATURE TESTS")
    print("="*60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        test_enhanced_sentiment()
        test_earnings_detection()
        test_watchlist_filtering()
        test_watchlist_sentiment_summary()
        test_news_alerts()
        test_earnings_blackout()
        
    except Exception as e:
        logger.error(f"Test error: {e}", exc_info=True)
    
    print("\n" + "="*60)
    print("TESTS COMPLETE")
    print("="*60)
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

if __name__ == '__main__':
    main()
