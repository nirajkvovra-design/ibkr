import os
import sys
import logging
import pandas as pd
from datetime import datetime

# Setup local imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config
from utils import setup_logging, get_logger
from strategies import MachineLearningStrategy
from data_fetcher import DataFetcher
import ml_models

# Ensure logging goes to console
setup_logging()
logger = get_logger("test_ml_strategy")

class DummyIBConnection:
    """Dummy IB Connection class for testing strategies offline"""
    def __init__(self):
        self.connected = True
        self.positions = {}
        
    def get_positions(self):
        return self.positions
        
    def get_available_funds_for_buys(self):
        return 10000.0
        
    def has_active_order(self, symbol, side):
        return False
        
    def place_order(self, symbol, side, quantity, order_type="LMT", limit_price=0, metadata=None):
        logger.info(f"[Offline Place Order] {side} {quantity} shares of {symbol} at limit ${limit_price:.2f}")
        return 99999

def test_forecasting_pipeline(tickers=None):
    if tickers is None:
        tickers = ["INTC", "BAC", "F"]

    logger.info("=" * 60)
    logger.info("Starting Offline Machine Learning Strategy Test")
    logger.info("=" * 60)
    
    # 1. Instantiate Dummy Connection and Strategy
    ib_dummy = DummyIBConnection()
    strategy = MachineLearningStrategy(ib_dummy, risk_manager=None)
    
    # Force strategy selection in config for testing
    config.SELECTED_STRATEGY = "ML"
    
    logger.info(f"Watchlist tickers under test: {tickers}")
    
    # Test each model type sequentially
    model_types = ["MONTE_CARLO"]
    if ml_models.LSTMForecaster.is_supported():
        model_types.extend(["LSTM", "RNN"])
    else:
        logger.info("TensorFlow or scikit-learn not found. Skipping neural network (LSTM/RNN) verification. Using Monte Carlo GBM.")
    
    for model_type in model_types:
        logger.info("\n" + "-" * 50)
        logger.info(f"Testing ML Model Type: {model_type}")
        logger.info("-" * 50)
        
        config.ML_MODEL_TYPE = model_type
        
        # Override config variables for fast execution in test
        if model_type in ("LSTM", "RNN"):
            config.ML_NEURAL_EPOCHS = 10  # fast training for demo
            
        logger.info(f"Generating signals for {tickers}...")
        signals = strategy.generate_signals(tickers)
        
        logger.info("\n--- Test Results ---")
        for symbol, signal in signals.items():
            logger.info(f"Symbol: {symbol:<6} | Generated Signal: {signal}")
            
if __name__ == "__main__":
    # Test with starter stocks under the $120 price cap (like Intel, Bank of America, Ford)
    test_tickers = ["INTC", "BAC", "F"]
    
    try:
        test_forecasting_pipeline(test_tickers)
        logger.info("\n" + "=" * 60)
        logger.info("Verification pipeline ran successfully!")
        logger.info("=" * 60)
    except Exception as e:
        logger.exception(f"Verification pipeline failed with exception: {e}")
