"""
Stock screener module - finds tradeable stocks based on technical and fundamental criteria
"""

import yfinance as yf
import pandas as pd
from pandas import isna as pd_isna
from datetime import datetime, timedelta
from utils import get_logger
from data_fetcher import DataFetcher
import config
from news_sentiment import NewsSentiment

logger = get_logger(__name__)

class StockScreener:
    """Screens and ranks stocks for trading"""
    
    def __init__(self):
        self.data_fetcher = DataFetcher()
        self.sentiment_analyzer = NewsSentiment()
        if config.STARTER_ACCOUNT_MODE:
            self.default_stocks = config.STARTER_STOCKS
        elif config.USE_AI_INFRA_UNIVERSE:
            self.default_stocks = config.AI_INFRA_STOCKS
        else:
            self.default_stocks = config.ALLOWED_US_STOCKS

        # Dynamically expand the watchlist with discovered high-tech/IPO stock tickers
        try:
            from universe_expander import UniverseExpander
            self.universe_expander = UniverseExpander(self.data_fetcher)
            dynamic_tickers = list(self.universe_expander.discovered_tickers)
            if dynamic_tickers:
                logger.info(f"[Screener Universe] Merging {len(dynamic_tickers)} dynamic thematic tickers into watchlist pool.")
                self.default_stocks = list(set(self.default_stocks + dynamic_tickers))
        except Exception as e:
            logger.error(f"Error merging dynamic tickers in StockScreener: {e}")
        
    def get_watchlist(self, method='technical'):
        """
        Get list of stocks to trade
        
        Methods:
        - 'technical': Based on technical indicators
        - 'fundamental': Based on fundamental analysis
        - 'hybrid': Combination of both
        - 'default': Use predefined list
        """
        try:
            if method == 'news_trending':
                symbols = self._screen_news_trending()
                if not symbols:
                    logger.info("News-trending empty; falling back to default watchlist")
                    return self._screen_default()
                return symbols
            elif method == 'market_winners':
                symbols = self._screen_market_winners()
                if not symbols:
                    logger.info("Market-winners empty; falling back to default watchlist")
                    return self._screen_default()
                return symbols
            elif method == 'ipo':
                return self._screen_ipo_momentum()
            elif method == 'technical':
                return self._screen_technical()
            elif method == 'fundamental':
                return self._screen_fundamental()
            elif method == 'hybrid':
                return self._screen_hybrid()
            else:
                return self._screen_default()
                
        except Exception as e:
            logger.error(f"Error screening stocks: {e}")
            return self._screen_default()
    
    def _screen_default(self):
        """Return default watchlist"""
        final_symbols = [
            symbol for symbol in self.default_stocks
            if self.data_fetcher.is_trade_free_us_stock_candidate(symbol)
        ][:config.MAX_WATCHLIST_SIZE]
        logger.info(f"Using default watchlist: {final_symbols}")
        return final_symbols

    def _screen_news_trending(self):
        """Rank US stocks by bullish news plus upward price/volume movement."""
        logger.info("Starting news-trending screening...")
        candidates = []

        for symbol in self.default_stocks:
            try:
                if symbol in config.EXCLUDED_EVENT_SENSITIVE_STOCKS:
                    continue
                if not self.data_fetcher.is_trade_free_us_stock_candidate(symbol):
                    continue

                calendar_risk = self.data_fetcher.get_calendar_risk(symbol)
                if calendar_risk['blocked']:
                    logger.info(f"Skipping {symbol}: {calendar_risk['reason']}")
                    continue

                sentiment = self.sentiment_analyzer.get_news_sentiment(symbol, limit=5)
                if config.REQUIRE_BULLISH_NEWS_FOR_BUY and sentiment != 'BULLISH':
                    continue
                if not self.sentiment_analyzer.should_trade_based_on_news(symbol):
                    continue

                data = self.data_fetcher.get_stock_data(symbol, period='3mo', interval='1d')
                if data is None or len(data) < 20:
                    continue

                latest = data.iloc[-1]
                close = float(latest['Close'])
                previous_close = float(data.iloc[-2]['Close'])
                five_day_close = float(data.iloc[-6]['Close']) if len(data) >= 6 else previous_close
                volume_ratio = latest.get('Volume_Ratio', 1)
                sma_20 = latest.get('SMA_20')
                macd = latest.get('MACD')
                macd_signal = latest.get('MACD_Signal')

                one_day_change = (close - previous_close) / previous_close
                five_day_change = (close - five_day_close) / five_day_close
                if one_day_change < config.MIN_BUY_1D_CHANGE or five_day_change < config.MIN_BUY_5D_CHANGE:
                    continue
                if config.STARTER_ACCOUNT_MODE and close > config.STARTER_MAX_PRICE:
                    continue

                score = 0
                reasons = []
                if sentiment == 'BULLISH':
                    score += 4
                    reasons.append("bullish news")
                if one_day_change >= 0.01:
                    score += 2
                    reasons.append(f"1d +{one_day_change * 100:.1f}%")
                if five_day_change >= config.MOMENTUM_THRESHOLD:
                    score += 2
                    reasons.append(f"5d +{five_day_change * 100:.1f}%")
                if volume_ratio is not None and not pd_isna(volume_ratio) and float(volume_ratio) >= config.MIN_BUY_VOLUME_RATIO:
                    score += 1
                    reasons.append(f"volume {volume_ratio:.1f}x")
                if sma_20 is not None and close > float(sma_20):
                    score += 1
                    reasons.append("above SMA20")
                if macd is not None and macd_signal is not None and macd > macd_signal:
                    score += 1
                    reasons.append("MACD up")

                if score >= config.NEWS_TRENDING_MIN_SCORE:
                    candidates.append({
                        'symbol': symbol,
                        'score': score,
                        'price': close,
                        'reasons': reasons
                    })
            except Exception as e:
                logger.debug(f"Error news-trending screening {symbol}: {e}")

        candidates.sort(key=lambda x: x['score'], reverse=True)
        final_symbols = [candidate['symbol'] for candidate in candidates[:config.MAX_WATCHLIST_SIZE]]
        logger.info(f"News-trending screening found {len(final_symbols)} candidates: {final_symbols}")
        return final_symbols
    
    def _screen_technical(self):
        """
        Screen stocks based on technical indicators
        Looks for: momentum, RSI, volume, moving averages
        """
        logger.info("Starting technical screening...")
        
        candidates = []
        
        for symbol in self.default_stocks:
            try:
                # Get data
                data = self.data_fetcher.get_stock_data(symbol, period='1mo', interval='1d')
                
                if data is None or len(data) < 20:
                    continue
                
                latest = data.iloc[-1]
                
                # Technical criteria
                score = 0
                reasons = []
                
                # Criterion 1: RSI (30-70 range is good for entry)
                rsi = latest.get('RSI')
                if rsi is not None and 35 < rsi < 65:
                    score += 1
                    reasons.append(f"RSI good ({rsi:.1f})")
                
                # Criterion 2: Price above 20-day MA (uptrend)
                price = latest['Close']
                sma_20 = latest.get('SMA_20')
                if sma_20 is not None and price > sma_20:
                    score += 1
                    reasons.append(f"Price above SMA20")
                
                # Criterion 3: Volume above average
                volume_ratio = latest.get('Volume_Ratio')
                if volume_ratio is not None and volume_ratio > 1.0:
                    score += 1
                    reasons.append(f"High volume ({volume_ratio:.2f}x)")
                
                # Criterion 4: MACD positive
                macd = latest.get('MACD')
                macd_signal = latest.get('MACD_Signal')
                if macd is not None and macd_signal is not None and macd > macd_signal:
                    score += 1
                    reasons.append("MACD bullish")
                
                # Criterion 5: Price not in overbought territory
                sma_200 = latest.get('SMA_200')
                price_pct = ((price - sma_200) / sma_200 * 100) if sma_200 else 0
                if price_pct < 20:  # Not too extended above 200 MA
                    score += 1
                    reasons.append("Price not overbought")
                
                # Add to candidates if score >= 3
                if score >= 3:
                    candidates.append({
                        'symbol': symbol,
                        'score': score,
                        'price': price,
                        'reasons': reasons
                    })
                    logger.debug(f"{symbol}: score={score}, {', '.join(reasons)}")
                
            except Exception as e:
                logger.debug(f"Error screening {symbol}: {e}")
                continue
        
        # Sort by score descending
        candidates.sort(key=lambda x: x['score'], reverse=True)
        
        # Log results
        final_symbols = [c['symbol'] for c in candidates[:10]]
        logger.info(f"Technical screening found {len(final_symbols)} candidates: {final_symbols}")
        
        return final_symbols if final_symbols else self._screen_default()
    
    def _screen_fundamental(self):
        """
        Screen stocks based on fundamental metrics
        Looks for: P/E ratio, market cap, earnings
        """
        logger.info("Starting fundamental screening...")
        
        candidates = []
        
        for symbol in self.default_stocks:
            try:
                fundamentals = self.data_fetcher.get_fundamental_data(symbol)
                
                if fundamentals is None:
                    continue
                
                score = 0
                reasons = []
                
                # Criterion 1: Reasonable P/E ratio (10-30)
                pe = fundamentals.get('pe_ratio')
                if pe is not None and 10 < pe < 30:
                    score += 1
                    reasons.append(f"Good P/E ({pe:.1f})")
                
                # Criterion 2: Positive earnings
                eps = fundamentals.get('eps')
                if eps is not None and eps > 0:
                    score += 1
                    reasons.append(f"Positive EPS")
                
                # Criterion 3: Market cap > $1B
                market_cap = fundamentals.get('market_cap')
                if market_cap is not None and market_cap > 1_000_000_000:
                    score += 1
                    reasons.append(f"Large cap")
                
                # Criterion 4: Decent volume
                avg_volume = fundamentals.get('avg_volume')
                if avg_volume is not None and avg_volume > config.VOLUME_THRESHOLD:
                    score += 1
                    reasons.append(f"Good volume")
                
                if score >= 2:
                    candidates.append({
                        'symbol': symbol,
                        'score': score,
                        'reasons': reasons
                    })
                    logger.debug(f"{symbol}: score={score}, {', '.join(reasons)}")
                
            except Exception as e:
                logger.debug(f"Error screening {symbol}: {e}")
                continue
        
        candidates.sort(key=lambda x: x['score'], reverse=True)
        final_symbols = [c['symbol'] for c in candidates[:10]]
        logger.info(f"Fundamental screening found {len(final_symbols)} candidates: {final_symbols}")
        
        return final_symbols if final_symbols else self._screen_default()
    
    def _screen_hybrid(self):
        """Combine technical and fundamental screening"""
        logger.info("Starting hybrid screening...")
        
        # Get both lists
        technical = self._screen_technical()
        fundamental = self._screen_fundamental()
        
        # Combine: prefer stocks in both lists, then add from each
        combined = []
        
        # First: stocks in both lists (high priority)
        for symbol in technical:
            if symbol in fundamental:
                combined.append(symbol)
        
        # Then: add remaining from technical
        for symbol in technical:
            if symbol not in combined and len(combined) < 15:
                combined.append(symbol)
        
        # Then: add remaining from fundamental
        for symbol in fundamental:
            if symbol not in combined and len(combined) < 15:
                combined.append(symbol)
        
        logger.info(f"Hybrid screening result: {combined[:15]}")
        return combined[:15]
    
    def rank_stocks(self, symbols):
        """
        Rank a list of stocks by various metrics
        Returns sorted list
        """
        try:
            ranked = []
            
            for symbol in symbols:
                score = 0
                
                # Get technical data
                data = self.data_fetcher.get_stock_data(symbol, period='1mo')
                if data is not None and len(data) > 0:
                    latest = data.iloc[-1]
                    
                    # Score components
                    rsi = latest.get('RSI')
                    if rsi is not None:
                        if 40 < rsi < 60:
                            score += 2
                        elif 30 < rsi < 70:
                            score += 1
                    
                    momentum = self.data_fetcher.calculate_momentum(data)
                    if 0.01 < momentum < 0.05:  # 1-5% momentum
                        score += 2
                    
                    volume_ratio = latest.get('Volume_Ratio')
                    if volume_ratio is not None and volume_ratio > 1.2:
                        score += 1
                
                ranked.append({'symbol': symbol, 'score': score})
            
            # Sort by score
            ranked.sort(key=lambda x: x['score'], reverse=True)
            return [r['symbol'] for r in ranked]
            
        except Exception as e:
            logger.error(f"Error ranking stocks: {e}")
            return symbols
    
    def get_screener_report(self):
        """Generate a report of screening results"""
        try:
            technical = self._screen_technical()
            fundamental = self._screen_fundamental()
            
            report = {
                'timestamp': datetime.now().isoformat(),
                'technical_picks': technical[:10],
                'fundamental_picks': fundamental[:10],
                'recommended': self._screen_hybrid()[:15]
            }
            
            logger.info("Screening report generated")
            return report
            
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return None

    def _screen_ipo_momentum(self):
        """
        Scan recently listed companies (IPOs) showing stock chart breakouts.
        Checks built-in recent listings pool along with configured lists.
        """
        logger.info("Starting IPO momentum breakout screening...")
        candidates = []

        # High-potential recent listings pool
        recent_listings = ["RDDT", "ARM", "ALAB", "BIRK", "CART", "KVUE"]
        
        # Combine with default watchlist for thoroughness
        scan_pool = list(set(recent_listings + self.default_stocks))

        for symbol in scan_pool:
            try:
                if symbol in config.EXCLUDED_EVENT_SENSITIVE_STOCKS:
                    continue
                if not self.data_fetcher.is_trade_free_us_stock_candidate(symbol):
                    continue

                # Fetch 6-month historical prices
                data = self.data_fetcher.get_stock_data(symbol, period='6mo', interval='1d')
                if data is None or len(data) < config.IPO_MIN_BASE_DAYS:
                    continue

                history_days = len(data)
                # Ensure it meets listing age filters (IPOs only)
                if history_days > config.IPO_MAX_HISTORY_DAYS:
                    continue

                # Ignore early listing frenzy
                if history_days <= 3:
                    continue

                close = data['Close']
                high = data['High']
                volume_ratio = data.get('Volume_Ratio', 1.0)

                latest_close = float(close.iloc[-1])
                listing_high = high.iloc[2:-1].max()

                # Score based on chart breakout and volume expansion
                score = 0
                reasons = []

                if latest_close >= listing_high:
                    score += 4
                    reasons.append("Base High Breakout")
                if volume_ratio is not None and float(volume_ratio) >= config.IPO_BREAKOUT_VOLUME_RATIO:
                    score += 2
                    reasons.append(f"Volume Expansion ({volume_ratio:.2f}x)")

                ema_10 = close.ewm(span=10, adjust=False).mean()
                latest_ema = float(ema_10.iloc[-1])
                if latest_close >= latest_ema:
                    score += 1
                    reasons.append("Above 10D-EMA Support")

                if score >= 3:
                    candidates.append({
                        'symbol': symbol,
                        'score': score,
                        'price': latest_close,
                        'reasons': reasons
                    })
                    logger.info(f"IPO Candidate Found [{symbol}]: Price=${latest_close:.2f} | Score={score} ({', '.join(reasons)})")

            except Exception as e:
                logger.debug(f"Error screening IPO candidate {symbol}: {e}")
                continue

        candidates.sort(key=lambda x: x['score'], reverse=True)
        final_symbols = [c['symbol'] for c in candidates[:config.MAX_WATCHLIST_SIZE]]
        
        if not final_symbols:
            # Fallback to recent listings list if no active breakout is triggering today
            final_symbols = [s for s in recent_listings if self.data_fetcher.is_trade_free_us_stock_candidate(s)][:config.MAX_WATCHLIST_SIZE]
            logger.info(f"No active IPO breakouts triggered today. Using recent listings fallback: {final_symbols}")
            
        logger.info(f"IPO screening finalized: {final_symbols}")
        return final_symbols

    def _screen_market_winners(self):
        """
        Screen the stock universe for optimal winners based on the daily market regime:
        - BULLISH: High-beta growth and breakout momentum leaders.
        - NEUTRAL: Stable value stocks and range-bound blue chips.
        - BEARISH: Outliers showing absolute strength and strong defensive performance.
        """
        try:
            regime = self.data_fetcher.get_market_regime()
            logger.info(f"[Market Winners Screener] Screening winners for {regime} market regime...")
            
            candidates = []
            
            for symbol in self.default_stocks:
                try:
                    if symbol in config.EXCLUDED_EVENT_SENSITIVE_STOCKS:
                        continue
                    if not self.data_fetcher.is_trade_free_us_stock_candidate(symbol):
                        continue
                    
                    calendar_risk = self.data_fetcher.get_calendar_risk(symbol)
                    if calendar_risk['blocked']:
                        continue
                        
                    data = self.data_fetcher.get_stock_data(symbol, period='3mo', interval='1d')
                    if data is None or len(data) < 20:
                        continue
                        
                    latest = data.iloc[-1]
                    close = float(latest['Close'])
                    prev_close = float(data.iloc[-2]['Close'])
                    sma_20 = latest.get('SMA_20')
                    sma_50 = latest.get('SMA_50')
                    sma_200 = latest.get('SMA_200')
                    volume_ratio = latest.get('Volume_Ratio', 1.0)
                    rsi = latest.get('RSI')
                    
                    # Calculate returns
                    one_day_change = (close - prev_close) / prev_close
                    five_day_close = float(data.iloc[-6]['Close']) if len(data) >= 6 else prev_close
                    five_day_change = (close - five_day_close) / five_day_close
                    
                    score = 0
                    reasons = []
                    
                    if regime == 'BULLISH':
                        # Look for high-momentum breakout winners
                        if sma_20 and close > float(sma_20):
                            score += 2
                            reasons.append("above SMA20")
                        if sma_50 and close > float(sma_50):
                            score += 1
                            reasons.append("above SMA50")
                        if sma_200 and close > float(sma_200):
                            score += 1
                            reasons.append("above SMA200")
                        if volume_ratio is not None and not pd_isna(volume_ratio) and float(volume_ratio) >= 1.2:
                            score += 2
                            reasons.append(f"vol ratio {volume_ratio:.2f}x")
                        if rsi is not None and 50 < rsi < 70:
                            score += 2
                            reasons.append(f"strong RSI {rsi:.1f}")
                        if five_day_change >= 0.02:
                            score += 3
                            reasons.append(f"5d return +{five_day_change*100:.1f}%")
                        elif five_day_change > 0:
                            score += 1
                            reasons.append("5d positive")
                        if one_day_change >= 0.005:
                            score += 1
                            reasons.append(f"1d return +{one_day_change*100:.1f}%")
                            
                    elif regime == 'NEUTRAL':
                        # Look for stable range-bound blue chips or healthy value
                        fundamentals = self.data_fetcher.get_fundamental_data(symbol)
                        pe = fundamentals.get('pe_ratio') if fundamentals else None
                        
                        if rsi is not None and 40 <= rsi <= 60:
                            score += 3
                            reasons.append(f"stable RSI {rsi:.1f}")
                        if pe is not None and 10 < pe < 30:
                            score += 2
                            reasons.append(f"value PE {pe:.1f}")
                        if sma_50:
                            dist_to_sma = abs(close - float(sma_50)) / float(sma_50)
                            if dist_to_sma < 0.03:
                                score += 2
                                reasons.append("stable near SMA50")
                        if five_day_change >= 0:
                            score += 1
                            reasons.append("5d stable")
                            
                    elif regime == 'BEARISH':
                        # Look for absolute defensive strength (outperforming broad market)
                        if five_day_change > 0.005:
                            score += 4
                            reasons.append(f"outperforming: 5d +{five_day_change*100:.1f}%")
                        elif five_day_change >= 0:
                            score += 2
                            reasons.append("outperforming: 5d flat/positive")
                        if sma_20 and close > float(sma_20):
                            score += 3
                            reasons.append("strong above SMA20")
                        if rsi is not None and rsi > 45:
                            score += 1
                            reasons.append(f"healthy RSI {rsi:.1f}")
                        if volume_ratio is not None and not pd_isna(volume_ratio) and float(volume_ratio) >= 1.1:
                            score += 1
                            reasons.append("volume accumulation")
                            
                    if score > 0:
                        candidates.append({
                            'symbol': symbol,
                            'score': score,
                            'price': close,
                            'reasons': reasons
                        })
                except Exception as ex:
                    logger.debug(f"Error screening {symbol} in winners: {ex}")
                    
            candidates.sort(key=lambda x: x['score'], reverse=True)
            final_symbols = [candidate['symbol'] for candidate in candidates[:config.MAX_WATCHLIST_SIZE]]
            
            logger.info(f"[Market Winners Screener] Found {len(final_symbols)} candidates for {regime} market: {final_symbols}")
            for c in candidates[:config.MAX_WATCHLIST_SIZE]:
                logger.info(f"  - {c['symbol']}: Score={c['score']} | Price=${c['price']:.2f} | Reasons: {', '.join(c['reasons'])}")
                
            return final_symbols if final_symbols else self._screen_default()
            
        except Exception as e:
            logger.error(f"Error in screen_market_winners: {e}")
            return self._screen_default()

    def get_market_winners_watchlist(self):
        """
        Runs the market winners screen and returns a detailed list of dictionaries 
        containing ticker details, prices, daily changes, and score metrics.
        """
        try:
            regime = self.data_fetcher.get_market_regime()
            logger.info(f"[Detailed Watchlist] Running market winners screen for {regime}...")
            
            candidates = []
            
            for symbol in self.default_stocks:
                try:
                    if symbol in config.EXCLUDED_EVENT_SENSITIVE_STOCKS:
                        continue
                    if not self.data_fetcher.is_trade_free_us_stock_candidate(symbol):
                        continue
                    
                    calendar_risk = self.data_fetcher.get_calendar_risk(symbol)
                    if calendar_risk['blocked']:
                        continue
                        
                    data = self.data_fetcher.get_stock_data(symbol, period='3mo', interval='1d')
                    if data is None or len(data) < 20:
                        continue
                        
                    latest = data.iloc[-1]
                    close = float(latest['Close'])
                    prev_close = float(data.iloc[-2]['Close'])
                    sma_20 = latest.get('SMA_20')
                    sma_50 = latest.get('SMA_50')
                    sma_200 = latest.get('SMA_200')
                    volume_ratio = latest.get('Volume_Ratio', 1.0)
                    rsi = latest.get('RSI')
                    
                    # Calculate returns
                    one_day_change = (close - prev_close) / prev_close
                    five_day_close = float(data.iloc[-6]['Close']) if len(data) >= 6 else prev_close
                    five_day_change = (close - five_day_close) / five_day_close
                    
                    score = 0
                    reasons = []
                    
                    if regime == 'BULLISH':
                        if sma_20 and close > float(sma_20):
                            score += 2
                            reasons.append("above SMA20")
                        if sma_50 and close > float(sma_50):
                            score += 1
                            reasons.append("above SMA50")
                        if sma_200 and close > float(sma_200):
                            score += 1
                            reasons.append("above SMA200")
                        if volume_ratio is not None and not pd_isna(volume_ratio) and float(volume_ratio) >= 1.2:
                            score += 2
                            reasons.append(f"vol ratio {volume_ratio:.2f}x")
                        if rsi is not None and 50 < rsi < 70:
                            score += 2
                            reasons.append(f"strong RSI {rsi:.1f}")
                        if five_day_change >= 0.02:
                            score += 3
                            reasons.append(f"5d return +{five_day_change*100:.1f}%")
                        elif five_day_change > 0:
                            score += 1
                            reasons.append("5d positive")
                        if one_day_change >= 0.005:
                            score += 1
                            reasons.append(f"1d return +{one_day_change*100:.1f}%")
                            
                    elif regime == 'NEUTRAL':
                        fundamentals = self.data_fetcher.get_fundamental_data(symbol)
                        pe = fundamentals.get('pe_ratio') if fundamentals else None
                        
                        if rsi is not None and 40 <= rsi <= 60:
                            score += 3
                            reasons.append(f"stable RSI {rsi:.1f}")
                        if pe is not None and 10 < pe < 30:
                            score += 2
                            reasons.append(f"value PE {pe:.1f}")
                        if sma_50:
                            dist_to_sma = abs(close - float(sma_50)) / float(sma_50)
                            if dist_to_sma < 0.03:
                                score += 2
                                reasons.append("stable near SMA50")
                        if five_day_change >= 0:
                            score += 1
                            reasons.append("5d stable")
                            
                    elif regime == 'BEARISH':
                        if five_day_change > 0.005:
                            score += 4
                            reasons.append(f"outperforming: 5d +{five_day_change*100:.1f}%")
                        elif five_day_change >= 0:
                            score += 2
                            reasons.append("outperforming: 5d flat/positive")
                        if sma_20 and close > float(sma_20):
                            score += 3
                            reasons.append("strong above SMA20")
                        if rsi is not None and rsi > 45:
                            score += 1
                            reasons.append(f"healthy RSI {rsi:.1f}")
                        if volume_ratio is not None and not pd_isna(volume_ratio) and float(volume_ratio) >= 1.1:
                            score += 1
                            reasons.append("volume accumulation")
                            
                    if score > 0:
                        candidates.append({
                            'symbol': symbol,
                            'score': score,
                            'price': round(close, 2),
                            'change_1d': round(one_day_change * 100, 2),
                            'change_5d': round(five_day_change * 100, 2),
                            'volume_ratio': round(float(volume_ratio), 2) if volume_ratio is not None and not pd_isna(volume_ratio) else 1.0,
                            'rsi': round(float(rsi), 1) if rsi is not None and not pd_isna(rsi) else None,
                            'reasons': reasons
                        })
                except Exception as ex:
                    logger.debug(f"Error screening {symbol} in detailed watchlist: {ex}")
                    
            candidates.sort(key=lambda x: x['score'], reverse=True)
            return candidates[:config.MAX_WATCHLIST_SIZE]
            
        except Exception as e:
            logger.error(f"Error in get_market_winners_watchlist: {e}")
            return []
