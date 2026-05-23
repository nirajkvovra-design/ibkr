import logging
import numpy as np
import pandas as pd
from utils import get_logger

logger = get_logger(__name__)

# Lazy imports for optional ML libraries
tensorflow_available = False
sklearn_available = False

try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import Dense, LSTM, SimpleRNN
    tensorflow_available = True
except ImportError:
    logger.debug("TensorFlow is not available in the current environment. Deep learning models (LSTM/RNN) will run in fallback mode.")

try:
    from sklearn.preprocessing import MinMaxScaler
    sklearn_available = True
except ImportError:
    logger.debug("scikit-learn is not available in the current environment. Data normalization will run in fallback mode.")


class MonteCarloGBMModel:
    """
    Geometric Brownian Motion (GBM) Monte Carlo Simulator.
    Models future asset price trajectories using stochastic calculus.
    """

    @staticmethod
    def simulate_gbm(prices, forecast_period=10, num_simulations=500, days_per_year=252):
        """
        Simulate asset prices using GBM.
        
        S_t = S_{t-1} * exp( (mu - 0.5 * sigma^2) * dt + sigma * W_t )
        
        Returns:
            simulations: numpy array of shape (forecast_period, num_simulations)
            metrics: dict containing prediction statistics
        """
        if len(prices) < 2:
            raise ValueError("Insufficient price data to compute drift and volatility.")

        # Calculate daily log returns
        returns = np.log(prices / prices.shift(1)).dropna()
        
        # Calculate daily drift (mu) and daily volatility (sigma)
        mu = returns.mean()
        sigma = returns.std()
        
        if sigma == 0:
            sigma = 0.0001  # Prevent divide by zero / zero diffusion

        # Define time step dt (1 trading day)
        dt = 1.0 / days_per_year
        
        # Latest actual price
        latest_price = float(prices.iloc[-1])
        
        # Initialize simulation matrix
        simulations = np.zeros((forecast_period, num_simulations))
        simulations[0, :] = latest_price
        
        # Generate simulations
        for day in range(1, forecast_period):
            # Standard normal random variable (Brownian motion shock)
            shocks = np.random.normal(size=num_simulations)
            
            # Drift and diffusion terms
            drift = (mu - 0.5 * sigma**2)
            diffusion = sigma * shocks
            
            # Project to next day
            simulations[day, :] = simulations[day - 1, :] * np.exp(drift + diffusion)

        # Compute metrics
        final_prices = simulations[-1, :]
        expected_final_price = np.mean(final_prices)
        expected_return_pct = ((expected_final_price - latest_price) / latest_price) * 100
        
        # Probability that price ends higher than current price
        probability_of_profit = np.mean(final_prices > latest_price) * 100
        
        # Standard deviation / risk of the forecast
        forecast_std_pct = (np.std(final_prices) / latest_price) * 100

        metrics = {
            "latest_actual_price": latest_price,
            "expected_final_price": expected_final_price,
            "expected_return_pct": expected_return_pct,
            "probability_of_profit": probability_of_profit,
            "volatility_daily": sigma,
            "drift_daily": mu,
            "forecast_std_pct": forecast_std_pct
        }

        return simulations, metrics


class LSTMForecaster:
    """
    LSTM Neural Network Forecaster.
    Trains dynamically on historical prices to predict short-term price moves.
    """

    @staticmethod
    def is_supported():
        return tensorflow_available and sklearn_available

    @staticmethod
    def forecast_next_price(prices, window_size=10, epochs=20, batch_size=32):
        """
        Dynamically builds and trains an LSTM model on the provided prices
        to predict the next day's closing price.
        """
        if not LSTMForecaster.is_supported():
            raise RuntimeError("LSTM Forecaster cannot run because TensorFlow or scikit-learn is missing.")

        if len(prices) < window_size + 5:
            raise ValueError(f"Insufficient price data. Needed at least {window_size + 5} prices.")

        # Convert prices to numpy array
        raw_prices = prices.values.reshape(-1, 1)

        # Scale data
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaled_data = scaler.fit_transform(raw_prices)

        # Create training sequences
        X, y = [], []
        for i in range(window_size, len(scaled_data)):
            X.append(scaled_data[i-window_size:i, 0])
            y.append(scaled_data[i, 0])
        
        X, y = np.array(X), np.array(y)
        
        # Reshape for LSTM input: (samples, time_steps, features)
        X = np.reshape(X, (X.shape[0], X.shape[1], 1))

        # Build LSTM Model
        model = Sequential([
            LSTM(units=32, return_sequences=True, input_shape=(window_size, 1)),
            LSTM(units=16, return_sequences=False),
            Dense(units=1)
        ])
        
        model.compile(optimizer='adam', loss='mean_squared_error')
        
        # Train model (suppress output for clean logs)
        model.fit(X, y, epochs=epochs, batch_size=batch_size, verbose=0)

        # Predict next day's price
        last_sequence = scaled_data[-window_size:]
        last_sequence = np.reshape(last_sequence, (1, window_size, 1))
        
        predicted_scaled = model.predict(last_sequence, verbose=0)
        predicted_price = float(scaler.inverse_transform(predicted_scaled)[0, 0])
        
        latest_price = float(prices.iloc[-1])
        expected_return_pct = ((predicted_price - latest_price) / latest_price) * 100

        metrics = {
            "latest_actual_price": latest_price,
            "expected_final_price": predicted_price,
            "expected_return_pct": expected_return_pct,
            "model_type": "LSTM"
        }

        return predicted_price, metrics


class RNNForecaster:
    """
    Simple RNN Neural Network Forecaster.
    Alternative sequence model using traditional recurrent layer architectures.
    """

    @staticmethod
    def is_supported():
        return tensorflow_available and sklearn_available

    @staticmethod
    def forecast_next_price(prices, window_size=10, epochs=20, batch_size=32):
        """
        Dynamically builds and trains an RNN model on the provided prices
        to predict the next day's closing price.
        """
        if not RNNForecaster.is_supported():
            raise RuntimeError("RNN Forecaster cannot run because TensorFlow or scikit-learn is missing.")

        if len(prices) < window_size + 5:
            raise ValueError(f"Insufficient price data. Needed at least {window_size + 5} prices.")

        # Convert prices to numpy array
        raw_prices = prices.values.reshape(-1, 1)

        # Scale data
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaled_data = scaler.fit_transform(raw_prices)

        # Create training sequences
        X, y = [], []
        for i in range(window_size, len(scaled_data)):
            X.append(scaled_data[i-window_size:i, 0])
            y.append(scaled_data[i, 0])
        
        X, y = np.array(X), np.array(y)
        
        # Reshape for RNN input: (samples, time_steps, features)
        X = np.reshape(X, (X.shape[0], X.shape[1], 1))

        # Build RNN Model
        model = Sequential([
            SimpleRNN(units=32, activation='relu', input_shape=(window_size, 1)),
            Dense(units=1)
        ])
        
        model.compile(optimizer='adam', loss='mean_squared_error')
        
        # Train model
        model.fit(X, y, epochs=epochs, batch_size=batch_size, verbose=0)

        # Predict next day's price
        last_sequence = scaled_data[-window_size:]
        last_sequence = np.reshape(last_sequence, (1, window_size, 1))
        
        predicted_scaled = model.predict(last_sequence, verbose=0)
        predicted_price = float(scaler.inverse_transform(predicted_scaled)[0, 0])
        
        latest_price = float(prices.iloc[-1])
        expected_return_pct = ((predicted_price - latest_price) / latest_price) * 100

        metrics = {
            "latest_actual_price": latest_price,
            "expected_final_price": predicted_price,
            "expected_return_pct": expected_return_pct,
            "model_type": "RNN"
        }

        return predicted_price, metrics
