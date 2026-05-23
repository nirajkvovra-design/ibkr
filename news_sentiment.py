"""
News sentiment module - analyzes news and sentiment for stocks
"""

import yfinance as yf
import requests
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from utils import get_logger
import config

try:
    import feedparser
except ImportError:
    feedparser = None

try:
    from textblob import TextBlob
except ImportError:
    TextBlob = None

logger = get_logger(__name__)

class NewsSentiment:
    """Analyzes news and sentiment for stocks"""
    
    def __init__(self):
        self.sentiment_cache = {}
        self.news_cache = {}
        self.cache_time = {}
        self.positive_keywords = [
            'surge', 'rally', 'beat', 'gain', 'profit', 'bullish',
            'strong', 'upgrade', 'outperform', 'buy', 'rise', 'jump',
            'soar', 'boom', 'success', 'record', 'growth', 'expansion',
            'partnership', 'deal', 'acquisition', 'breakthrough'
        ]
        
        self.negative_keywords = [
            'crash', 'drop', 'miss', 'loss', 'bearish', 'weak',
            'downgrade', 'underperform', 'sell', 'fall', 'plunge',
            'slump', 'decline', 'concern', 'risk', 'warning', 'delay',
            'lawsuit', 'investigation', 'recall', 'failure', 'scandal',
            'export control', 'restriction', 'ban', 'sanction', 'capex cut',
            'spending cut', 'order cut', 'cancel', 'shortage easing',
            'margin pressure', 'accounting', 'probe'
        ]
    
    def _normalize_news_article(self, article):
        """Support both legacy flat and current nested yfinance news payloads."""
        content = article.get('content')
        if isinstance(content, dict):
            title = content.get('title', '')
            provider = content.get('provider') or {}
            source = provider.get('displayName', '') if isinstance(provider, dict) else ''
            canonical = content.get('canonicalUrl') or {}
            link = canonical.get('url', '') if isinstance(canonical, dict) else ''
            if not link:
                link = content.get('previewUrl', '')
            published = content.get('pubDate') or content.get('displayTime') or ''
        else:
            title = article.get('title', '')
            source = article.get('source', '')
            link = article.get('link', '')
            published = article.get('providerPublishTime', '')

        return {
            'title': title or '',
            'source': source or '',
            'link': link or '',
            'published': published or '',
        }

    def get_stock_news(self, symbol, limit=10):
        """Fetch latest news for a stock"""
        try:
            cache_key = f"stock:{symbol}:{limit}"
            if self._cache_valid(cache_key):
                return self.news_cache[cache_key]

            ticker = yf.Ticker(symbol)
            news = ticker.news
            
            if not news:
                logger.debug(f"No news found for {symbol}")
                return []
            
            # Format news
            formatted_news = []
            for article in news[:limit]:
                formatted_news.append(self._normalize_news_article(article))
            
            self.news_cache[cache_key] = formatted_news
            self.cache_time[cache_key] = datetime.now()
            return formatted_news
            
        except Exception as e:
            logger.warning(f"Error fetching news for {symbol}: {e}")
            return None

    def _cache_valid(self, cache_key):
        if cache_key not in self.cache_time:
            return False
        age = datetime.now() - self.cache_time[cache_key]
        return age < timedelta(minutes=config.NEWS_REFRESH_MINUTES)
    
    def analyze_sentiment(self, text):
        """
        Analyze sentiment of text using TextBlob
        Returns: sentiment score between -1 (very negative) and 1 (very positive)
        """
        try:
            if not text:
                return 0
            if TextBlob is None:
                return 0
            
            # Use TextBlob for sentiment analysis
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity  # -1 to 1
            
            return polarity
            
        except Exception as e:
            logger.debug(f"Error analyzing sentiment: {e}")
            return 0
    
    def get_news_sentiment(self, symbol, limit=5):
        """
        Get overall sentiment for a stock based on recent news
        
        Returns:
            'BULLISH': Positive sentiment
            'BEARISH': Negative sentiment
            'NEUTRAL': Mixed or no clear sentiment
        """
        try:
            news_items = self.get_stock_news(symbol, limit=limit)
            
            if news_items is None:
                return 'UNKNOWN'

            if not news_items:
                logger.debug(f"No news items for sentiment analysis: {symbol}")
                return 'NEUTRAL'
            
            sentiment_scores = []
            
            for item in news_items:
                title = item.get('title', '').lower()
                
                # Simple keyword-based scoring
                score = 0
                
                # Check positive keywords
                for keyword in self.positive_keywords:
                    if keyword in title:
                        score += 1
                
                # Check negative keywords
                for keyword in self.negative_keywords:
                    if keyword in title:
                        score -= 1
                
                # Alternative: Use TextBlob
                blob_score = self.analyze_sentiment(title)
                
                # Combine scores
                final_score = (score + blob_score) / 2
                sentiment_scores.append(final_score)
                
                logger.debug(f"{symbol} - '{title[:50]}...' - Score: {final_score:.2f}")
            
            # Calculate average sentiment
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
            
            # Classify
            if avg_sentiment > 0.2:
                result = 'BULLISH'
            elif avg_sentiment < -0.2:
                result = 'BEARISH'
            else:
                result = 'NEUTRAL'
            
            logger.info(f"{symbol} sentiment: {result} (score: {avg_sentiment:.2f})")
            return result
            
        except Exception as e:
            logger.error(f"Error getting sentiment for {symbol}: {e}")
            return 'NEUTRAL'
    
    def get_news_impact(self, symbol, news_items=None):
        """
        Analyze potential impact of recent news
        Returns: impact score (-1 to 1)
        """
        try:
            if news_items is None:
                news_items = self.get_stock_news(symbol, limit=3)
            
            if not news_items:
                return 0
            
            impact_score = 0
            
            for item in news_items:
                title = item.get('title', '').lower()
                
                # High impact keywords
                high_impact_keywords = [
                    'earnings', 'bankruptcy', 'acquisition', 'merger',
                    'ipo', 'recall', 'lawsuit', 'ceo departure'
                ]
                
                if any(keyword in title for keyword in high_impact_keywords):
                    # Analyze direction
                    if any(kw in title for kw in self.positive_keywords):
                        impact_score += 0.5
                    elif any(kw in title for kw in self.negative_keywords):
                        impact_score -= 0.5
            
            return min(1, max(-1, impact_score))
            
        except Exception as e:
            logger.error(f"Error analyzing news impact: {e}")
            return 0
    
    def should_trade_based_on_news(self, symbol):
        """
        Determine if we should trade based on news
        
        Returns:
            True: Safe to trade (no negative news)
            False: Risky (significant negative news or events)
        """
        try:
            news_items = self.get_stock_news(symbol, limit=5)
            
            if news_items is None:
                return not config.BLOCK_ON_NEWS_FAILURE

            if not news_items:
                return True  # No news = safe
            
            # Check for high-risk events
            risky_keywords = [
                'bankruptcy', 'delisting', 'fraud', 'recall',
                'lawsuit', 'investigation', 'halt', 'trading halt',
                'export ban', 'export control', 'sanction', 'accounting probe',
                'guidance cut', 'capex cut', 'order cancellation'
            ]
            
            for item in news_items:
                title = item.get('title', '').lower()
                
                if any(keyword in title for keyword in risky_keywords):
                    logger.warning(f"Risky news for {symbol}: {item['title'][:50]}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking trade safety: {e}")
            return not config.BLOCK_ON_NEWS_FAILURE

    def get_market_news_context(self, limit=10):
        """Fetch broad market headlines for a frequent pre-trade sanity check."""
        try:
            cache_key = f"market:{limit}"
            if self._cache_valid(cache_key):
                return self.news_cache[cache_key]

            url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC,%5EIXIC,%5EDJI&region=US&lang=en-US"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            headlines = []
            if feedparser is not None:
                feed = feedparser.parse(response.content)
                for entry in feed.entries[:limit]:
                    headlines.append({
                        'title': entry.get('title', ''),
                        'source': entry.get('source', {}).get('title', 'Yahoo Finance'),
                        'link': entry.get('link', ''),
                        'published': entry.get('published', ''),
                    })
            else:
                root = ET.fromstring(response.content)
                for item in root.findall(".//item")[:limit]:
                    headlines.append({
                        'title': item.findtext("title", default=""),
                        'source': "Yahoo Finance",
                        'link': item.findtext("link", default=""),
                        'published': item.findtext("pubDate", default=""),
                    })

            self.news_cache[cache_key] = headlines
            self.cache_time[cache_key] = datetime.now()
            return headlines
        except Exception as e:
            logger.warning(f"Error fetching market news: {e}")
            return None

    def market_news_allows_trading(self):
        """Block trading on obvious broad-market shock headlines."""
        headlines = self.get_market_news_context()
        if headlines is None:
            return not config.BLOCK_ON_NEWS_FAILURE

        shock_keywords = [
            'crash', 'plunge', 'selloff', 'sell-off', 'circuit breaker',
            'trading halt', 'war', 'default', 'bank failure', 'emergency'
        ]
        for item in headlines:
            title = item.get('title', '').lower()
            if any(re.search(rf"\b{re.escape(keyword)}\b", title) for keyword in shock_keywords):
                logger.warning(f"Broad-market risk headline blocks trading: {item.get('title', '')[:90]}")
                return False
        return True
    
    def get_sector_sentiment(self, sector):
        """
        Get overall sentiment for a sector
        (This would require data for multiple stocks in a sector)
        """
        try:
            # Example: tech sector stocks
            sector_stocks = {
                'technology': ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'META'],
                'healthcare': ['JNJ', 'PFE', 'UNH', 'ABBV', 'TMO'],
                'financials': ['JPM', 'BAC', 'WFC', 'GS', 'MS'],
            }
            
            stocks = sector_stocks.get(sector.lower(), [])
            
            if not stocks:
                return 'NEUTRAL'
            
            sentiments = [self.get_news_sentiment(symbol) for symbol in stocks]
            
            bullish_count = sentiments.count('BULLISH')
            bearish_count = sentiments.count('BEARISH')
            
            if bullish_count > bearish_count:
                return 'BULLISH'
            elif bearish_count > bullish_count:
                return 'BEARISH'
            else:
                return 'NEUTRAL'
                
        except Exception as e:
            logger.error(f"Error getting sector sentiment: {e}")
            return 'NEUTRAL'
    
    def get_sentiment_report(self, symbols):
        """Generate sentiment report for multiple stocks"""
        try:
            report = {
                'timestamp': datetime.now().isoformat(),
                'stocks': {}
            }
            
            for symbol in symbols:
                report['stocks'][symbol] = {
                    'sentiment': self.get_news_sentiment(symbol),
                    'news_count': len(self.get_stock_news(symbol) or []),
                    'trade_safe': self.should_trade_based_on_news(symbol)
                }
            
            logger.info("Sentiment report generated")
            return report
            
        except Exception as e:
            logger.error(f"Error generating sentiment report: {e}")
            return None
