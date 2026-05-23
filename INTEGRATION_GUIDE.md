# Integration Guide: Enhanced News Sentiment Features

## Quick Start

The enhanced news sentiment module is now ready to use in your trading system. Here's how to integrate it:

## 1. Pre-Trade Watchlist Check

Add this to your trading engine initialization to check watchlist sentiment before trading:

```python
from news_sentiment import NewsSentiment
from stock_screener import StockScreener

# In your trading engine
analyzer = NewsSentiment()
screener = StockScreener()

# Get today's watchlist
watchlist = screener.get_watchlist('news_trending')

# Check overall sentiment
sentiment_summary = analyzer.get_watchlist_sentiment_summary(watchlist)
logger.info(f"Watchlist Status: {sentiment_summary['summary']}")
logger.info(f"Bullish: {sentiment_summary['bullish_percent']:.1f}%")

# Check for alerts
alerts = analyzer.generate_news_alerts(watchlist)
if alerts:
    for alert in alerts:
        logger.warning(f"ALERT: {alert['symbol']} - {alert['type']}")
```

## 2. Pre-Trade Stock Check

Add this before entering a position:

```python
def can_trade_symbol(symbol):
    """Check if it's safe to trade a symbol based on news"""
    analyzer = NewsSentiment()
    
    # Check earnings blackout
    if analyzer.check_earnings_blackout(symbol):
        logger.warning(f"{symbol} has recent earnings - skipping")
        return False
    
    # Check for risky news
    if not analyzer.should_trade_based_on_news(symbol):
        logger.warning(f"{symbol} has risky news - skipping")
        return False
    
    # Check sentiment
    sentiment = analyzer.get_news_sentiment(symbol)
    if sentiment == 'BEARISH':
        logger.warning(f"{symbol} sentiment is bearish - skipping")
        return False
    
    return True

# Usage
if can_trade_symbol('AAPL'):
    logger.info("✓ AAPL is safe to trade")
    # Place trade
```

## 3. Daily News Report

Add to your daily report generation:

```python
def generate_daily_news_report(watchlist):
    """Generate daily news and earnings report"""
    analyzer = NewsSentiment()
    
    # Export comprehensive summary
    summary = analyzer.export_watchlist_news_summary(watchlist)
    
    # Also get earnings calendar
    earnings = analyzer.get_earnings_news(watchlist, limit=10)
    
    logger.info("Daily News Report:")
    logger.info(f"  Sentiment: {summary['summary']}")
    logger.info(f"  Bullish %: {summary['bullish_percent']:.1f}%")
    logger.info(f"  Earnings: {len(earnings)} symbols with recent announcements")
    
    return summary, earnings
```

## 4. Risk Management Integration

Add earnings awareness to your risk manager:

```python
from news_sentiment import NewsSentiment

def can_hold_position(symbol, current_pnl):
    """Determine if we should hold or exit a position"""
    analyzer = NewsSentiment()
    
    # Check if earnings coming up
    if analyzer.check_earnings_blackout(symbol):
        if current_pnl > 0:
            logger.info(f"{symbol}: Earnings imminent, taking profits")
            return False  # Exit with profit before earnings
    
    # Check for high-impact news
    impact = analyzer.get_news_impact(symbol)
    if impact['impact_level'] == 'CRITICAL':
        if current_pnl > 0:
            logger.warning(f"{symbol}: Critical news, closing position")
            return False
    
    return True
```

## 5. Strategy Enhancement

Add news sentiment as a trading signal:

```python
from strategies import TradingStrategy
from news_sentiment import NewsSentiment

class NewsAwareStrategy(TradingStrategy):
    """Trading strategy that incorporates news sentiment"""
    
    def __init__(self):
        super().__init__()
        self.analyzer = NewsSentiment()
    
    def evaluate(self, symbol, data):
        """Evaluate if we should buy based on technical + news"""
        
        # Get technical signal
        technical_score = self._get_technical_score(symbol, data)
        
        # Get news sentiment
        sentiment = self.analyzer.get_news_sentiment(symbol)
        news_score = 1.0 if sentiment == 'BULLISH' else 0.5 if sentiment == 'NEUTRAL' else 0.0
        
        # Check earnings
        if self.analyzer.check_earnings_blackout(symbol):
            news_score = 0.0  # Don't trade around earnings
        
        # Combine scores
        combined_score = (technical_score * 0.6) + (news_score * 0.4)
        
        if combined_score > 0.7:
            return 'BUY'
        elif combined_score < 0.3:
            return 'SELL'
        else:
            return 'HOLD'
```

## 6. Monitoring Dashboard Data

Export data for external dashboard/alerts:

```python
def update_monitoring_dashboard():
    """Update external monitoring with news data"""
    analyzer = NewsSentiment()
    watchlist = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN']
    
    # Generate alerts
    alerts = analyzer.generate_news_alerts(watchlist)
    
    # Get news
    news = analyzer.get_watchlist_news(watchlist, limit=20)
    
    # Export data
    dashboard_data = {
        'timestamp': datetime.now().isoformat(),
        'alerts': alerts,
        'recent_news': news,
        'summary': analyzer.get_watchlist_sentiment_summary(watchlist)
    }
    
    # Send to monitoring system (Slack, Discord, Email, etc.)
    send_dashboard_update(dashboard_data)
```

## Configuration

### Key Settings in config.py

```python
# News and sentiment settings
REQUIRE_NEWS_CHECK = True              # Require news analysis before trading
REQUIRE_BULLISH_NEWS_FOR_BUY = True    # Only buy on bullish news
NEWS_REFRESH_MINUTES = 15              # News cache refresh interval
BLOCK_ON_NEWS_FAILURE = True           # Block trading if news fetch fails

# Earnings settings
EARNINGS_BLACKOUT_DAYS_BEFORE = 3      # Avoid trading 3 days before earnings
EARNINGS_BLACKOUT_DAYS_AFTER = 1       # Avoid trading 1 day after earnings

# Market news settings (broad market checks)
MARKET_REGIME_SYMBOLS = ["SPY", "QQQ"] # Symbols to check for market regime
```

## Testing

Run the test suite to verify all features work:

```bash
python test_news_enhancements.py
```

This will test:
1. Enhanced sentiment analysis
2. Earnings detection
3. Watchlist filtering
4. Sentiment summaries
5. Alert generation
6. Earnings blackout

## Files Added/Modified

### New Files
- `NEWS_SENTIMENT_ENHANCEMENTS.md` - Comprehensive documentation
- `test_news_enhancements.py` - Test suite for all new features
- `INTEGRATION_GUIDE.md` - This file

### Modified Files
- `news_sentiment.py` - Enhanced with new methods and capabilities

## Key New Methods

| Method | Purpose |
|--------|---------|
| `analyze_sentiment(text)` | Enhanced sentiment scoring with weights |
| `detect_earnings_announcement(article)` | Detect earnings and classify direction |
| `get_earnings_news(symbols)` | Get earnings news for symbol list |
| `get_watchlist_news(symbols)` | Filter news by watchlist |
| `get_watchlist_sentiment_summary(symbols)` | Get watchlist sentiment overview |
| `check_earnings_blackout(symbol)` | Check if in earnings blackout window |
| `generate_news_alerts(symbols)` | Generate alerts for important events |
| `export_watchlist_news_summary(symbols)` | Export full report to JSON |

## Common Patterns

### Pattern 1: Safe Trade Check
```python
analyzer = NewsSentiment()

def is_safe_to_trade(symbol):
    return (
        not analyzer.check_earnings_blackout(symbol) and
        analyzer.should_trade_based_on_news(symbol) and
        analyzer.get_news_sentiment(symbol) != 'BEARISH'
    )
```

### Pattern 2: Trade on News
```python
analyzer = NewsSentiment()

def should_buy(symbol):
    earnings = analyzer.get_earnings_news([symbol])
    if symbol in earnings:
        for news in earnings[symbol]:
            if news['direction'] == 'BEAT':
                return True
    return False
```

### Pattern 3: Risk Management
```python
analyzer = NewsSentiment()

def should_exit_position(symbol, current_pnl):
    impact = analyzer.get_news_impact(symbol)
    if impact['impact_level'] == 'CRITICAL' and current_pnl > 0:
        return True  # Exit on critical news
    return False
```

## Troubleshooting

### Issue: "TextBlob not installed"
**Solution**: `pip install textblob`

### Issue: "No earnings detected"
**Solution**: Check that news fetch is working: `analyzer.get_stock_news('AAPL')`

### Issue: "Sentiment always NEUTRAL"
**Solution**: Install TextBlob data: `python -m textblob.download_corpora`

### Issue: "Rate limited on news API"
**Solution**: Increase `NEWS_REFRESH_MINUTES` to cache longer

## Best Practices

1. **Cache appropriately**: Use the caching system to avoid excessive API calls
2. **Combine signals**: Use news as a filter, not the only signal
3. **Monitor earnings**: Always check earnings blackout before entering
4. **Generate alerts**: Set up alerts for high-impact events
5. **Review exports**: Export and review watchlist news daily
6. **Test first**: Use paper trading to validate news integration

## Next Steps

1. Run `test_news_enhancements.py` to verify functionality
2. Review `NEWS_SENTIMENT_ENHANCEMENTS.md` for detailed documentation
3. Integrate pre-trade news checks into your trading engine
4. Set up earnings blackout filtering
5. Configure watchlist news monitoring
6. Test with paper trading before live deployment

---

For questions or issues, refer to `NEWS_SENTIMENT_ENHANCEMENTS.md` for detailed examples and troubleshooting.
