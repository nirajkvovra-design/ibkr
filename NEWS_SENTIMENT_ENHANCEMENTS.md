# Enhanced News Sentiment Analysis

## Overview

The news sentiment module has been significantly enhanced with three powerful features:

1. **Enhanced Sentiment Analysis** - Advanced hybrid approach combining keyword weighting and NLP
2. **Earnings Announcement Detection** - Automatic detection and classification of earnings news
3. **Market News Filtering by Watchlist** - Filter and prioritize news relevant to your trading watchlist

---

## Feature 1: Enhanced Sentiment Analysis

### Improvements

- **Weighted Keywords**: Positive and negative keywords now have importance weights (0.6-1.2)
- **Hybrid Scoring**: Combines keyword-based analysis (60%) with TextBlob NLP (40%)
- **Subjectivity Weighting**: TextBlob sentiment scored by objectivity level
- **Better Thresholds**: Updated sentiment classification (±0.3 threshold vs old ±0.2)

### Usage

```python
from news_sentiment import NewsSentiment

analyzer = NewsSentiment()

# Analyze single text
sentiment_score = analyzer.analyze_sentiment("Apple beats earnings expectations")
# Returns: 0.5+ (positive) to -0.5 (negative)

# Get overall stock sentiment
sentiment = analyzer.get_news_sentiment("AAPL", limit=5)
# Returns: 'BULLISH', 'BEARISH', or 'NEUTRAL'
```

### Keyword Examples

**Positive Keywords (with weights)**:
- `beat` (1.2) - Earnings beat estimates
- `upgrade` (1.1) - Analyst upgrade
- `breakthrough` (1.1) - Major breakthrough
- `record` (1.1) - Record results

**Negative Keywords (with weights)**:
- `scandal` (1.2) - Major scandal
- `crash` (1.2) - Major decline
- `export control` (1.2) - Regulatory restriction
- `miss` (1.1) - Earnings miss

---

## Feature 2: Earnings Announcement Detection

### Methods

#### `detect_earnings_announcement(article)`
Detects if an article is about earnings and classifies the result.

```python
analyzer = NewsSentiment()
article = {'title': 'NVIDIA Beats Q4 Earnings Expectations', 'published': '2026-05-22'}

is_earnings, direction, impact_score = analyzer.detect_earnings_announcement(article)
# Returns:
# - is_earnings: True
# - direction: 'BEAT' (or 'MISS', 'IN_LINE')
# - impact_score: 0.65 (positive sentiment score)
```

#### `get_earnings_news(symbols, limit=10)`
Get all earnings-related news for a list of symbols.

```python
symbols = ['AAPL', 'MSFT', 'NVDA']
earnings_news = analyzer.get_earnings_news(symbols)

# Returns:
# {
#     'AAPL': [
#         {
#             'symbol': 'AAPL',
#             'title': 'Apple Beats Q2 Earnings...',
#             'direction': 'BEAT',
#             'impact_score': 0.72,
#             'earnings_date': '2026-05-22',
#             'source': 'Reuters',
#             'link': '...'
#         }
#     ],
#     ...
# }
```

#### `check_earnings_blackout(symbol, days_before=3, days_after=1)`
Check if a stock recently had earnings (within blackout window).

```python
in_blackout = analyzer.check_earnings_blackout('AAPL')
# Returns: True if earnings detected within the blackout period
# Useful for avoiding trading around earnings volatility
```

---

## Feature 3: Market News Filtering by Watchlist

### Methods

#### `get_watchlist_news(symbols, limit=20)`
Get the most important news for your entire watchlist.

```python
watchlist = ['AAPL', 'MSFT', 'NVDA', 'TSLA']
news = analyzer.get_watchlist_news(watchlist, limit=20)

# Returns: list of news articles with:
# - symbol: which watchlist stock it relates to
# - sentiment: 'BULLISH', 'BEARISH', 'NEUTRAL'
# - sentiment_score: -1.0 to 1.0
# - is_earnings: True/False
# - impact_score: importance level
# - title, source, link, published
```

#### `get_watchlist_sentiment_summary(symbols)`
Get a high-level sentiment analysis for your entire watchlist.

```python
watchlist = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN']
summary = analyzer.get_watchlist_sentiment_summary(watchlist)

# Returns:
# {
#     'timestamp': '2026-05-22T10:30:00',
#     'watchlist_size': 5,
#     'bullish': 3,
#     'bearish': 1,
#     'neutral': 1,
#     'bullish_percent': 60.0,
#     'sentiments': {
#         'AAPL': 'BULLISH',
#         'MSFT': 'BULLISH',
#         'NVDA': 'BULLISH',
#         'TSLA': 'NEUTRAL',
#         'AMZN': 'BEARISH'
#     },
#     'earnings_upcoming': {
#         'AAPL': [{ earnings data }]
#     },
#     'top_news': [ 5 most impactful news items ],
#     'summary': '3 bullish, 1 bearish, 1 neutral'
# }
```

#### `export_watchlist_news_summary(symbols, output_file='watchlist_news_summary.json')`
Export comprehensive news and earnings data to JSON file.

```python
watchlist = ['AAPL', 'MSFT', 'NVDA', 'TSLA']
summary = analyzer.export_watchlist_news_summary(watchlist)

# Exports to: watchlist_news_summary.json
# Contains: sentiment summary + detailed earnings + all watchlist news
```

---

## Feature 4: News Alerts

### Method

#### `generate_news_alerts(symbols, alert_threshold=0.7)`
Generate alerts for high-impact earnings and events.

```python
symbols = ['AAPL', 'MSFT', 'NVDA']
alerts = analyzer.generate_news_alerts(symbols, alert_threshold=0.7)

# Returns: list of alerts like
# [
#     {
#         'type': 'EARNINGS',
#         'symbol': 'AAPL',
#         'severity': 'CRITICAL',  # CRITICAL or HIGH
#         'direction': 'BEAT',      # BEAT, MISS, IN_LINE
#         'title': 'Apple Beats Q4 Earnings...',
#         'timestamp': '2026-05-22T10:30:00'
#     },
#     {
#         'type': 'HIGH_IMPACT_EVENT',
#         'symbol': 'MSFT',
#         'severity': 'HIGH',
#         'event': 'acquisition',
#         'direction': 'POSITIVE',
#         'title': 'Microsoft Acquires AI Company...',
#         'timestamp': '2026-05-22T10:25:00'
#     }
# ]
```

---

## Integration with Trading Engine

### Example: Pre-trade Watchlist Check

```python
from stock_screener import StockScreener
from news_sentiment import NewsSentiment

screener = StockScreener()
analyzer = NewsSentiment()

# Get watchlist
watchlist = screener.get_watchlist('news_trending')

# Check watchlist sentiment
watchlist_summary = analyzer.get_watchlist_sentiment_summary(watchlist)

print(f"Watchlist Status: {watchlist_summary['summary']}")
print(f"Bullish Percentage: {watchlist_summary['bullish_percent']:.1f}%")

# Generate alerts
alerts = analyzer.generate_news_alerts(watchlist, alert_threshold=0.7)
if alerts:
    print(f"\n⚠️  {len(alerts)} Important News Alerts:")
    for alert in alerts:
        print(f"  - {alert['symbol']}: {alert['type']} ({alert['severity']})")
        print(f"    {alert['title']}")

# Get top news
top_news = watchlist_summary['top_news']
for item in top_news:
    print(f"\n📰 {item['symbol']}: {item['title']}")
    print(f"   Sentiment: {item['sentiment']} (Score: {item['sentiment_score']:.2f})")
```

### Example: Earnings-Aware Trading

```python
from trading_engine import TradingEngine
from news_sentiment import NewsSentiment

analyzer = NewsSentiment()
engine = TradingEngine()

# Before entering a position
symbol = 'AAPL'

# Check if in earnings blackout
if analyzer.check_earnings_blackout(symbol):
    print(f"⚠️  {symbol} has recent earnings - skipping trade")
    exit()

# Check if safe to trade
if not analyzer.should_trade_based_on_news(symbol):
    print(f"⚠️  Risky news for {symbol} - skipping trade")
    exit()

# Proceed with trade
print(f"✓ {symbol} is safe to trade")
```

---

## Configuration

### Earnings Blackout Settings (in config.py)

```python
EARNINGS_BLACKOUT_DAYS_BEFORE = 3   # Days before earnings to avoid trading
EARNINGS_BLACKOUT_DAYS_AFTER = 1    # Days after earnings to avoid trading
REQUIRE_NEWS_CHECK = True            # Require news analysis before trading
REQUIRE_BULLISH_NEWS_FOR_BUY = True  # Only buy if news sentiment is bullish
NEWS_REFRESH_MINUTES = 15            # How often to refresh news cache
```

---

## Key Improvements Summary

| Feature | Improvement |
|---------|-------------|
| **Sentiment Analysis** | Weighted keywords + NLP + subjectivity scoring |
| **Earnings Detection** | Automatic detection + direction classification (BEAT/MISS) |
| **Impact Detection** | Enhanced high-impact event detection with severity levels |
| **Watchlist Filtering** | Smart filtering of news relevant to your positions |
| **Alerts** | Automatic alert generation for critical events |
| **Export** | JSON export for analysis and monitoring |

---

## Best Practices

1. **Use Watchlist Filtering**: Always filter news by your active watchlist to avoid noise
2. **Monitor Earnings Calendar**: Check `check_earnings_blackout()` before entering positions
3. **Check Pre-Trade**: Use `should_trade_based_on_news()` as part of your pre-trade checklist
4. **Review Alerts**: Set up alerts for earnings and high-impact events
5. **Export Daily**: Export watchlist summaries for record-keeping and analysis

---

## Example: Complete Monitoring Setup

```python
from news_sentiment import NewsSentiment
from stock_screener import StockScreener
import json
from datetime import datetime

# Initialize
analyzer = NewsSentiment()
screener = StockScreener()

# Get today's watchlist
watchlist = screener.get_watchlist('news_trending')

# Generate comprehensive report
print("=" * 60)
print(f"WATCHLIST NEWS REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 60)

# 1. Watchlist sentiment summary
summary = analyzer.get_watchlist_sentiment_summary(watchlist)
print(f"\n📊 SENTIMENT OVERVIEW:")
print(f"   {summary['summary']}")
print(f"   Bullish: {summary['bullish_percent']:.1f}%")

# 2. Important earnings news
print(f"\n📈 EARNINGS ANNOUNCEMENTS:")
earnings = analyzer.get_earnings_news(watchlist)
if earnings:
    for symbol, news in earnings.items():
        for item in news[:2]:  # Top 2 per symbol
            print(f"   {symbol}: {item['direction']} - {item['title'][:60]}")
else:
    print("   No recent earnings announcements")

# 3. High-impact events
print(f"\n⚠️  HIGH-IMPACT EVENTS:")
alerts = analyzer.generate_news_alerts(watchlist)
if alerts:
    for alert in alerts[:5]:  # Top 5 alerts
        print(f"   {alert['symbol']}: {alert['type']} ({alert['severity']})")
else:
    print("   No critical events detected")

# 4. Export for archival
analyzer.export_watchlist_news_summary(watchlist)
print(f"\n✓ Full report exported to: watchlist_news_summary.json")
```

---

## Troubleshooting

### "No TextBlob module" warning
- Install TextBlob: `pip install textblob`
- If sentiment analysis seems off, install NLTK data: `python -m textblob.download_corpora`

### News cache not updating
- Check `NEWS_REFRESH_MINUTES` in config
- Cache automatically refreshes after specified interval
- Force refresh by clearing cache in code

### Earnings not detected
- Check if earnings keywords match your news sources
- Add custom keywords to `self.earnings_keywords` if needed
- Verify news fetching works: `analyzer.get_stock_news('SYMBOL')`
