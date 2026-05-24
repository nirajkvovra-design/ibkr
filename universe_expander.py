"""
Dynamic Stock Universe Expander
Automatically searches for newly listed tickers and stocks related to advanced technology themes
(Quantum computing, nuclear energy, robotics, semiconductor manufacturing, aerospace/SpaceX, AI).
Filters for high-frequency trading candidates meeting liquidity requirements.
"""

import json
import logging
import requests
from pathlib import Path
import config
from data_fetcher import DataFetcher

logger = logging.getLogger(__name__)

_SAVE_PATH = Path("dynamic_universe.json")

class UniverseExpander:
    """Discovers, validates, and records stock tickers dynamically based on thematic filters"""
    
    THEMES = [
        'quantum computing',
        'nuclear power',
        'uranium',
        'robotics',
        'semiconductor',
        'memory storage',
        'data center',
        'artificial intelligence',
        'spacex',
        'aerospace'
    ]

    def __init__(self, data_fetcher=None):
        self.data_fetcher = data_fetcher or DataFetcher()
        self.discovered_tickers = set()
        self.load_dynamic_tickers()

    def load_dynamic_tickers(self):
        """Load previously discovered tickers from local JSON file"""
        try:
            if _SAVE_PATH.exists():
                with _SAVE_PATH.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.discovered_tickers = set(data)
                        logger.info(f"[Universe Expander] Loaded {len(self.discovered_tickers)} existing dynamic tickers.")
        except Exception as e:
            logger.error(f"Error loading dynamic tickers: {e}")

    def save_dynamic_tickers(self):
        """Save discovered tickers to local JSON file"""
        try:
            with _SAVE_PATH.open("w", encoding="utf-8") as f:
                json.dump(sorted(list(self.discovered_tickers)), f, indent=4)
                logger.info(f"[Universe Expander] Saved {len(self.discovered_tickers)} dynamic tickers to {_SAVE_PATH}.")
        except Exception as e:
            logger.error(f"Error saving dynamic tickers: {e}")

    def expand_universe(self):
        """Query public search endpoints by theme, validate liquidity, and record new tickers"""
        logger.info("[Universe Expander] Launching dynamic theme search...")
        newly_added = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        for theme in self.THEMES:
            try:
                url = f"https://query2.finance.yahoo.com/v1/finance/search?q={theme}&quotesCount=15&newsCount=0"
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code != 200:
                    logger.warning(f"Failed to query theme '{theme}' (status {response.status_code})")
                    continue

                data = response.json()
                quotes = data.get("quotes", [])
                
                theme_added = []
                for q in quotes:
                    symbol = q.get("symbol", "").upper()
                    quote_type = q.get("quoteType", "")
                    exchange = q.get("exchange", "")
                    
                    if not symbol or quote_type != "EQUITY":
                        continue

                    # Filter out already discovered or predefined ones to avoid redundancy
                    if symbol in self.discovered_tickers:
                        continue
                        
                    # Predefined lists check
                    starter_symbols = set(config.STARTER_STOCKS) if config.STARTER_ACCOUNT_MODE else set()
                    allowed_symbols = set(config.ALLOWED_US_STOCKS) | set(config.AI_INFRA_STOCKS) | starter_symbols
                    if symbol in allowed_symbols:
                        continue

                    # Validate liquidity and trading parameters using DataFetcher
                    if self.data_fetcher.is_trade_free_us_stock_candidate(symbol):
                        self.discovered_tickers.add(symbol)
                        newly_added.append(symbol)
                        theme_added.append(symbol)

                if theme_added:
                    logger.info(f"[Universe Expander] Found new thematic tickers for '{theme}': {theme_added}")

            except Exception as e:
                logger.error(f"Error expanding theme '{theme}': {e}")

        if newly_added:
            logger.info(f"[Universe Expander] Expansion cycle completed. Added {len(newly_added)} new tickers: {newly_added}")
            self.save_dynamic_tickers()
        else:
            logger.info("[Universe Expander] Expansion cycle completed. No new high-frequency candidates discovered today.")

        return list(self.discovered_tickers)
