"""
News sentiment module - analyzes news and sentiment for stocks
Enhanced with earnings detection, watchlist filtering, and advanced sentiment analysis
"""

import yfinance as yf
import requests
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from utils import get_logger
import config
import json

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
    """Analyzes news and sentiment for stocks with earnings detection and watchlist filtering"""
    
    def __init__(self):
        self.sentiment_cache = {}
        self.news_cache = {}
        self.cache_time = {}
        self.earnings_cache = {}
        self.earnings_cache_time = {}
        
        # Positive keywords with importance weights
        self.positive_keywords = {
            'surge': 1.0, 'rally': 1.0, 'beat': 1.2, 'gain': 0.7, 'profit': 1.0, 'bullish': 1.2,
            'strong': 0.8, 'upgrade': 1.1, 'outperform': 1.0, 'buy': 0.9, 'rise': 0.7, 'jump': 0.8,
            'soar': 1.0, 'boom': 0.9, 'success': 0.9, 'record': 1.1, 'growth': 0.9, 'expansion': 0.9,
            'partnership': 0.8, 'deal': 0.8, 'acquisition': 0.8, 'breakthrough': 1.1, 'achieved': 0.7,
            'exceeded': 1.0, 'outpaced': 0.9, 'innovative': 0.8, 'strategic': 0.7, 'positive': 0.8,
            'strong demand': 1.2, 'market leader': 1.0, 'industry leader': 1.0, 'accelerate': 0.8
        }
        
        # Negative keywords with importance weights
        self.negative_keywords = {
            'crash': 1.2, 'drop': 0.8, 'miss': 1.1, 'loss': 0.9, 'bearish': 1.2, 'weak': 0.8,
            'downgrade': 1.1, 'underperform': 1.0, 'sell': 0.9, 'fall': 0.7, 'plunge': 1.0,
            'slump': 0.9, 'decline': 0.8, 'concern': 0.7, 'risk': 0.6, 'warning': 0.9, 'delay': 0.7,
            'lawsuit': 1.1, 'investigation': 1.0, 'recall': 1.1, 'failure': 1.0, 'scandal': 1.2,
            'export control': 1.2, 'restriction': 0.9, 'ban': 1.0, 'sanction': 1.1, 'capex cut': 1.0,
            'spending cut': 0.9, 'order cut': 1.0, 'cancel': 0.8, 'shortage': 0.7, 'margin pressure': 0.8,
            'accounting': 1.0, 'probe': 1.0, 'disappointing': 0.9, 'negative': 0.7, 'concern': 0.7,
            'competition': 0.6, 'challenged': 0.7, 'pressure': 0.6, 'headwind': 0.7,
            'dilution': 1.1, 'share dilution': 1.1, 'stock dilution': 1.1, 'secondary offering': 1.1,
            'share offering': 1.0, 'public offering': 0.9,
            'military escalation': 1.3, 'military action': 1.3, 'missile strike': 1.3, 'cyber attack': 1.2,
            'tariff': 1.1, 'trade war': 1.2, 'inflation shock': 1.2, 'interest rate spike': 1.1,
            'opec cut': 1.1, 'crude spike': 1.0, 'geopolitical shock': 1.3, 'nuclear escalation': 1.5,
            'war': 1.4
        }
        
        # Earnings-related keywords
        self.earnings_keywords = [
            'earnings', 'eps', 'earning per share', 'revenue', 'quarterly results',
            'q1 results', 'q2 results', 'q3 results', 'q4 results', 'fy results',
            'beats estimates', 'misses estimates', 'exceeds guidance', 'cut guidance',
            'fiscal quarter', 'quarterly report', '3rd quarter', '4th quarter'
        ]
        
        # Event-related keywords for impact detection
        self.high_impact_keywords = [
            'earnings', 'bankruptcy', 'acquisition', 'merger', 'ipo', 'recall',
            'lawsuit', 'ceo departure', 'management change', 'product launch',
            'regulatory approval', 'fda approval', 'layoff', 'dividend cut',
            'secondary offering', 'share dilution'
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
        Analyze sentiment of text using enhanced hybrid approach
        Returns: sentiment score between -1 (very negative) and 1 (very positive)
        """
        try:
            if not text:
                return 0
            
            text_lower = text.lower()
            
            # Keyword-based scoring with weights
            keyword_score = 0
            for keyword, weight in self.positive_keywords.items():
                if keyword in text_lower:
                    keyword_score += weight
            
            for keyword, weight in self.negative_keywords.items():
                if keyword in text_lower:
                    keyword_score -= weight
            
            # Normalize keyword score
            max_possible_keywords = max(
                sum(self.positive_keywords.values()),
                sum(self.negative_keywords.values())
            )
            keyword_score = keyword_score / max_possible_keywords if max_possible_keywords > 0 else 0
            
            # TextBlob sentiment analysis (if available)
            textblob_score = 0
            if TextBlob is not None:
                try:
                    blob = TextBlob(text)
                    polarity = blob.sentiment.polarity
                    subjectivity = blob.sentiment.subjectivity
                    # Weight by subjectivity - more objective = more credible
                    textblob_score = polarity * (0.5 + 0.5 * subjectivity)
                except Exception as e:
                    logger.debug(f"TextBlob error: {e}")
            
            # Combine scores (60% keyword, 40% textblob)
            final_score = (keyword_score * 0.6) + (textblob_score * 0.4)
            
            # Clamp to [-1, 1]
            return max(-1, min(1, final_score))
            
        except Exception as e:
            logger.debug(f"Error analyzing sentiment: {e}")
            return 0
    
    def detect_earnings_announcement(self, article):
        """
        Detect if news article is about earnings announcement
        Returns: tuple (is_earnings, direction, impact_score)
            - is_earnings: bool whether this is earnings news
            - direction: 'BEAT', 'MISS', 'IN_LINE', or None
            - impact_score: float indicating impact magnitude
        """
        try:
            title = article.get('title', '').lower()
            
            # Check if it's earnings-related
            is_earnings = any(keyword in title for keyword in self.earnings_keywords)
            
            if not is_earnings:
                return False, None, 0
            
            # Determine direction
            direction = None
            if any(word in title for word in ['beat', 'exceed', 'outpace']):
                direction = 'BEAT'
            elif any(word in title for word in ['miss', 'fall short', 'disappoint']):
                direction = 'MISS'
            elif any(word in title for word in ['inline', 'in line', 'matched', 'meet']):
                direction = 'IN_LINE'
            
            # Calculate impact score based on sentiment
            impact_score = self.analyze_sentiment(title)
            if direction == 'BEAT':
                impact_score = max(impact_score, 0.3)  # Minimum positive for beat
            elif direction == 'MISS':
                impact_score = min(impact_score, -0.3)  # Minimum negative for miss
            
            return True, direction, impact_score
            
        except Exception as e:
            logger.debug(f"Error detecting earnings: {e}")
            return False, None, 0
    
    def parse_earnings_date(self, article):
        """
        Try to extract earnings date from article
        Returns: datetime or None
        """
        try:
            text = article.get('title', '') + ' ' + article.get('published', '')
            
            # Pattern matching for dates
            date_patterns = [
                r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})',  # MM/DD/YYYY
                r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})',
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, text.lower())
                if match:
                    logger.debug(f"Found potential earnings date: {match.group()}")
                    # Would need more sophisticated parsing to fully extract date
                    return match.group()
            
            return None
        except Exception as e:
            logger.debug(f"Error parsing earnings date: {e}")
            return None
    
    def get_earnings_news(self, symbols, limit=10):
        """
        Get earnings-related news for a list of symbols
        Returns: dict with symbol -> list of earnings articles
        """
        try:
            earnings_news = {}
            
            for symbol in symbols:
                symbol_earnings = []
                news_items = self.get_stock_news(symbol, limit=limit)
                
                if not news_items:
                    continue
                
                for article in news_items:
                    is_earnings, direction, impact = self.detect_earnings_announcement(article)
                    if is_earnings:
                        earnings_date = self.parse_earnings_date(article)
                        symbol_earnings.append({
                            'symbol': symbol,
                            'title': article.get('title', ''),
                            'source': article.get('source', ''),
                            'link': article.get('link', ''),
                            'published': article.get('published', ''),
                            'direction': direction,
                            'impact_score': impact,
                            'earnings_date': earnings_date
                        })
                
                if symbol_earnings:
                    earnings_news[symbol] = symbol_earnings
            
            return earnings_news
            
        except Exception as e:
            logger.error(f"Error getting earnings news: {e}")
            return {}
    
    def get_watchlist_news(self, symbols, limit=20):
        """
        Get market news filtered by watchlist symbols
        Returns: list of news articles relevant to watchlist
        """
        try:
            watchlist_news = []
            seen_titles = set()
            
            for symbol in symbols:
                try:
                    news_items = self.get_stock_news(symbol, limit=5)
                    
                    if not news_items:
                        continue
                    
                    for article in news_items:
                        title = article.get('title', '')
                        
                        # Avoid duplicates
                        if title in seen_titles:
                            continue
                        
                        seen_titles.add(title)
                        
                        # Add symbol tag
                        article_with_symbol = article.copy()
                        article_with_symbol['symbol'] = symbol
                        
                        # Detect earnings
                        is_earnings, direction, impact = self.detect_earnings_announcement(article)
                        article_with_symbol['is_earnings'] = is_earnings
                        article_with_symbol['earnings_direction'] = direction
                        article_with_symbol['impact_score'] = impact
                        
                        # Add sentiment
                        sentiment = self.analyze_sentiment(title)
                        article_with_symbol['sentiment_score'] = sentiment
                        article_with_symbol['sentiment'] = self._score_to_sentiment(sentiment)
                        
                        watchlist_news.append(article_with_symbol)
                
                except Exception as e:
                    logger.warning(f"Error fetching news for {symbol}: {e}")
                    continue
            
            # Sort by recency and impact
            try:
                watchlist_news.sort(
                    key=lambda x: (
                        -abs(x.get('impact_score', 0)),
                        -abs(x.get('sentiment_score', 0))
                    )
                )
            except Exception as e:
                logger.debug(f"Error sorting watchlist news: {e}")
            
            return watchlist_news[:limit]
        
        except Exception as e:
            logger.error(f"Error getting watchlist news: {e}")
            return []
    
    def _score_to_sentiment(self, score):
        """Convert numeric score to sentiment label"""
        if score > 0.2:
            return 'BULLISH'
        elif score < -0.2:
            return 'BEARISH'
        else:
            return 'NEUTRAL'
    
    def get_news_sentiment(self, symbol, limit=5):
        """
        Get overall sentiment for a stock based on recent news
        Enhanced with better scoring
        
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
            earnings_signals = []
            
            for item in news_items:
                title = item.get('title', '')
                
                # Analyze sentiment
                score = self.analyze_sentiment(title)
                sentiment_scores.append(score)
                
                # Check for earnings
                is_earnings, direction, impact = self.detect_earnings_announcement(item)
                if is_earnings:
                    earnings_signals.append({
                        'direction': direction,
                        'impact': impact
                    })
                    # Give earnings news more weight
                    sentiment_scores.append(impact * 1.5)
                
                logger.debug(f"{symbol} - '{title[:60]}...' - Score: {score:.2f}")
            
            # Calculate average sentiment
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
            
            # Classify with more nuance
            if avg_sentiment > 0.3:
                result = 'BULLISH'
            elif avg_sentiment < -0.3:
                result = 'BEARISH'
            else:
                result = 'NEUTRAL'
            
            logger.info(f"{symbol} sentiment: {result} (score: {avg_sentiment:.2f}, earnings: {len(earnings_signals)})")
            return result
            
        except Exception as e:
            logger.error(f"Error getting sentiment for {symbol}: {e}")
            return 'NEUTRAL'
    
    def get_watchlist_sentiment_summary(self, symbols):
        """
        Get sentiment summary for entire watchlist
        Returns: dict with sentiment stats and top news
        """
        try:
            sentiments = {}
            earnings_upcoming = {}
            all_news = []
            
            for symbol in symbols:
                sentiment = self.get_news_sentiment(symbol, limit=3)
                sentiments[symbol] = sentiment
                
                # Get earnings news
                earnings = self.get_earnings_news([symbol], limit=2)
                if symbol in earnings:
                    earnings_upcoming[symbol] = earnings[symbol]
            
            # Get combined watchlist news
            watchlist_news = self.get_watchlist_news(symbols, limit=10)
            
            # Calculate stats
            bullish_count = sum(1 for v in sentiments.values() if v == 'BULLISH')
            bearish_count = sum(1 for v in sentiments.values() if v == 'BEARISH')
            neutral_count = len(sentiments) - bullish_count - bearish_count
            
            summary = {
                'timestamp': datetime.now().isoformat(),
                'watchlist_size': len(symbols),
                'bullish': bullish_count,
                'bearish': bearish_count,
                'neutral': neutral_count,
                'bullish_percent': (bullish_count / len(symbols) * 100) if symbols else 0,
                'sentiments': sentiments,
                'earnings_upcoming': earnings_upcoming,
                'top_news': watchlist_news[:5],
                'summary': f"{bullish_count} bullish, {bearish_count} bearish, {neutral_count} neutral"
            }
            
            logger.info(f"Watchlist sentiment: {summary['summary']}")
            return summary
            
        except Exception as e:
            logger.error(f"Error getting watchlist sentiment summary: {e}")
            return {'error': str(e)}
    
    def get_news_impact(self, symbol, news_items=None):
        """
        Analyze potential impact of recent news with enhanced detection
        Returns: impact score (-1 to 1) with details
        """
        try:
            if news_items is None:
                news_items = self.get_stock_news(symbol, limit=3)
            
            if not news_items:
                return {'score': 0, 'impact_level': 'LOW', 'events': []}
            
            impact_score = 0
            high_impact_events = []
            
            for item in news_items:
                title = item.get('title', '').lower()
                
                # Check for high-impact events
                for keyword in self.high_impact_keywords:
                    if keyword in title:
                        sentiment_score = self.analyze_sentiment(title)
                        
                        event_impact = {
                            'event': keyword,
                            'title': item.get('title', '')[:80],
                            'direction': 'POSITIVE' if sentiment_score > 0 else 'NEGATIVE' if sentiment_score < 0 else 'NEUTRAL',
                            'strength': abs(sentiment_score)
                        }
                        high_impact_events.append(event_impact)
                        
                        if sentiment_score > 0:
                            impact_score += 0.6 * abs(sentiment_score)
                        else:
                            impact_score -= 0.6 * abs(sentiment_score)
            
            # Determine impact level
            abs_impact = abs(impact_score)
            if abs_impact > 0.7:
                impact_level = 'CRITICAL'
            elif abs_impact > 0.4:
                impact_level = 'HIGH'
            elif abs_impact > 0.2:
                impact_level = 'MEDIUM'
            else:
                impact_level = 'LOW'
            
            return {
                'score': min(1, max(-1, impact_score)),
                'impact_level': impact_level,
                'events': high_impact_events
            }
            
        except Exception as e:
            logger.error(f"Error analyzing news impact: {e}")
            return {'score': 0, 'impact_level': 'UNKNOWN', 'events': []}
    
    def check_earnings_blackout(self, symbol, days_before=None, days_after=None):
        """
        Check if a stock has recent or upcoming earnings
        Returns: bool indicating if trading should be avoided
        """
        try:
            if days_before is None:
                days_before = config.EARNINGS_BLACKOUT_DAYS_BEFORE
            if days_after is None:
                days_after = config.EARNINGS_BLACKOUT_DAYS_AFTER
            
            # Check for recent earnings announcements in news
            news_items = self.get_stock_news(symbol, limit=10)
            if not news_items:
                return False
            
            now = datetime.now()
            
            for item in news_items:
                is_earnings, direction, _ = self.detect_earnings_announcement(item)
                if is_earnings:
                    # Found earnings - check if within blackout window
                    # This is a simple check; would need actual earnings dates for precision
                    logger.warning(f"{symbol} has recent earnings announcement: {item.get('title', '')[:60]}")
                    return True
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking earnings blackout: {e}")
            return False
    
    def should_trade_based_on_news(self, symbol):
        """
        Determine if we should trade based on news
        Enhanced with earnings detection
        
        Returns:
            True: Safe to trade (no negative news/earnings)
            False: Risky (significant negative news or events)
        """
        try:
            # Check for earnings events
            if self.check_earnings_blackout(symbol):
                logger.warning(f"Trading blocked for {symbol} due to earnings")
                return False
            
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
                'guidance cut', 'capex cut', 'order cancellation',
                'dilution', 'share dilution', 'stock dilution', 'secondary offering',
                'share offering', 'public offering', 'offering of shares',
                'issuing shares', 'issuance of shares'
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
    
    def export_watchlist_news_summary(self, symbols, output_file='watchlist_news_summary.json'):
        """
        Export comprehensive news and sentiment summary for watchlist
        Includes earnings, sentiment analysis, and high-impact news
        """
        try:
            summary = self.get_watchlist_sentiment_summary(symbols)
            
            # Add earnings data
            earnings_data = self.get_earnings_news(symbols, limit=10)
            summary['all_earnings_news'] = earnings_data
            
            # Add detailed watchlist news
            watchlist_news = self.get_watchlist_news(symbols, limit=20)
            summary['detailed_news'] = watchlist_news
            
            # Write to file
            with open(output_file, 'w') as f:
                json.dump(summary, f, indent=2, default=str)
            
            logger.info(f"Watchlist news summary exported to {output_file}")
            return summary
            
        except Exception as e:
            logger.error(f"Error exporting watchlist news: {e}")
            return None
    
    def generate_news_alerts(self, symbols, alert_threshold=0.7):
        """
        Generate alerts for important news events (earnings, high-impact events)
        Returns: list of alert dictionaries
        """
        try:
            alerts = []
            
            # Check for earnings
            earnings_news = self.get_earnings_news(symbols)
            for symbol, news_items in earnings_news.items():
                for item in news_items:
                    if abs(item['impact_score']) >= alert_threshold:
                        alerts.append({
                            'type': 'EARNINGS',
                            'symbol': symbol,
                            'severity': 'CRITICAL' if abs(item['impact_score']) > 0.85 else 'HIGH',
                            'direction': item['direction'],
                            'title': item['title'],
                            'timestamp': datetime.now().isoformat()
                        })
            
            # Check for high-impact news
            for symbol in symbols:
                impact_data = self.get_news_impact(symbol)
                if impact_data['impact_level'] in ['HIGH', 'CRITICAL']:
                    for event in impact_data.get('events', []):
                        alerts.append({
                            'type': 'HIGH_IMPACT_EVENT',
                            'symbol': symbol,
                            'severity': impact_data['impact_level'],
                            'event': event['event'],
                            'direction': event['direction'],
                            'title': event['title'],
                            'timestamp': datetime.now().isoformat()
                        })
            
            # Log alerts
            for alert in alerts:
                logger.warning(f"ALERT: {alert['symbol']} - {alert['type']} ({alert['severity']}): {alert['title']}")
            
            return alerts
            
        except Exception as e:
            logger.error(f"Error generating alerts: {e}")
            return []

    def get_geopolitical_risk_multiplier(self, headlines: Optional[List[Dict[str, Any]]] = None) -> float:
        """
        Evaluate rolling headlines to calculate a de-risking multiplier (0.2x to 1.0x).
        Lower values mean more severe geopolitical/macro conflict, indicating risk-off.
        """
        if headlines is None:
            headlines = self.get_market_news_context(limit=10)
        if not headlines:
            return 1.0

        severe_triggers = {
            "war": 0.4,
            "military escalation": 0.3,
            "missile strike": 0.3,
            "nuclear": 0.2,
            "trade war": 0.5,
            "tariff": 0.7,
            "cyber attack": 0.6,
            "opec cut": 0.7,
            "sanctions": 0.7
        }

        min_multiplier = 1.0
        for item in headlines:
            title = item.get("title", "").lower()
            for trigger, multiplier in severe_triggers.items():
                pattern = rf"\b{re.escape(trigger)}\b" if len(trigger) <= 4 else re.escape(trigger)
                if re.search(pattern, title):
                    logger.warning("[News Sentry] Geopolitical trigger '%s' detected in headline: '%s'. De-risking factor: %.2fx",
                                   trigger, item.get("title", "")[:80], multiplier)
                    if multiplier < min_multiplier:
                        min_multiplier = multiplier

        return min_multiplier

