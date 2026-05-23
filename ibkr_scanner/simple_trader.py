"""
EDUCATIONAL TRADING BOT - FOR PAPER TRADING ONLY
===============================================

WARNING: This is for educational purposes only. 
- Start with PAPER TRADING (port 7497)
- Never risk money you can't afford to lose
- Past performance does not guarantee future results
- Trading involves substantial risk of loss

This implements a simple momentum strategy:
- Buy when stock breaks above recent high with volume
- Sell when price drops below stop loss or take profit
"""

from ib_async import *
import pandas as pd
import asyncio
from datetime import datetime, timedelta
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SimpleMomentumTrader:
    def __init__(self, host='127.0.0.1', port=7497, client_id=2):  # Default to paper trading
        self.ib = IB()
        self.host = host
        self.port = port
        self.client_id = client_id
        self.positions = {}
        self.watchlist = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']  # Example stocks
        
        # Strategy parameters
        self.max_position_size = 1000  # Max $ per position
        self.stop_loss_pct = 0.02      # 2% stop loss
        self.take_profit_pct = 0.04    # 4% take profit
        self.lookback_days = 5         # Days to look back for high
        self.volume_threshold = 1.5    # Volume must be 1.5x average
        
        # Risk management
        self.max_daily_loss = 500      # Max daily loss in $
        self.daily_pnl = 0
        
    async def connect(self):
        """Connect to IB"""
        try:
            await self.ib.connectAsync(self.host, self.port, clientId=self.client_id)
            logger.info(f"Connected to IB on {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from IB"""
        self.ib.disconnect()
        logger.info("Disconnected from IB")
    
    def create_stock_contract(self, symbol):
        """Create stock contract"""
        return Stock(symbol, 'SMART', 'USD')
    
    async def get_historical_data(self, contract, days=10):
        """Get historical data for analysis"""
        try:
            bars = await self.ib.reqHistoricalDataAsync(
                contract, 
                endDateTime='', 
                durationStr=f'{days} D',
                barSizeSetting='1 day', 
                whatToShow='TRADES', 
                useRTH=True
            )
            return util.df(bars) if bars else None
        except Exception as e:
            logger.error(f"Error getting historical data for {contract.symbol}: {e}")
            return None
    
    async def get_current_price(self, contract):
        """Get current market price"""
        try:
            ticker = self.ib.reqMktData(contract, '', False, False)
            await asyncio.sleep(2)  # Wait for data
            self.ib.cancelMktData(contract)
            
            if ticker.last and ticker.last > 0:
                return float(ticker.last)
            elif ticker.bid and ticker.ask:
                return (float(ticker.bid) + float(ticker.ask)) / 2
            return None
        except Exception as e:
            logger.error(f"Error getting price for {contract.symbol}: {e}")
            return None
    
    def analyze_momentum(self, df):
        """Analyze if stock shows momentum breakout"""
        if df is None or len(df) < self.lookback_days:
            return False, "Insufficient data"
        
        # Get recent high and volume
        recent_high = df['high'].tail(self.lookback_days).max()
        current_price = df['close'].iloc[-1]
        avg_volume = df['volume'].tail(10).mean()
        current_volume = df['volume'].iloc[-1]
        
        # Check for breakout conditions
        price_breakout = current_price > recent_high * 1.001  # Break above recent high
        volume_surge = current_volume > avg_volume * self.volume_threshold
        
        if price_breakout and volume_surge:
            return True, f"Breakout: Price ${current_price:.2f} > High ${recent_high:.2f}, Volume: {current_volume/avg_volume:.1f}x avg"
        
        return False, f"No breakout: Price ${current_price:.2f}, High ${recent_high:.2f}, Vol ratio: {current_volume/avg_volume:.1f}x"
    
    async def place_buy_order(self, contract, dollars):
        """Place a buy order"""
        try:
            current_price = await self.get_current_price(contract)
            if not current_price:
                return None
            
            # Calculate shares to buy
            shares = int(dollars / current_price)
            if shares < 1:
                logger.warning(f"Not enough buying power for {contract.symbol}")
                return None
            
            # Create market order
            order = MarketOrder('BUY', shares)
            trade = self.ib.placeOrder(contract, order)
            
            logger.info(f"BUY ORDER: {shares} shares of {contract.symbol} at ~${current_price:.2f}")
            
            # Store position info
            self.positions[contract.symbol] = {
                'shares': shares,
                'entry_price': current_price,
                'stop_loss': current_price * (1 - self.stop_loss_pct),
                'take_profit': current_price * (1 + self.take_profit_pct),
                'trade': trade
            }
            
            return trade
            
        except Exception as e:
            logger.error(f"Error placing buy order for {contract.symbol}: {e}")
            return None
    
    async def place_sell_order(self, contract, shares, reason):
        """Place a sell order"""
        try:
            order = MarketOrder('SELL', shares)
            trade = self.ib.placeOrder(contract, order)
            
            current_price = await self.get_current_price(contract)
            logger.info(f"SELL ORDER: {shares} shares of {contract.symbol} at ~${current_price:.2f} - {reason}")
            
            # Remove from positions
            if contract.symbol in self.positions:
                del self.positions[contract.symbol]
            
            return trade
            
        except Exception as e:
            logger.error(f"Error placing sell order for {contract.symbol}: {e}")
            return None
    
    async def check_exit_conditions(self):
        """Check if we should exit any positions"""
        for symbol, pos_info in list(self.positions.items()):
            contract = self.create_stock_contract(symbol)
            current_price = await self.get_current_price(contract)
            
            if not current_price:
                continue
            
            # Check stop loss
            if current_price <= pos_info['stop_loss']:
                await self.place_sell_order(contract, pos_info['shares'], "STOP LOSS")
                continue
            
            # Check take profit
            if current_price >= pos_info['take_profit']:
                await self.place_sell_order(contract, pos_info['shares'], "TAKE PROFIT")
                continue
            
            # Log current P&L
            pnl = (current_price - pos_info['entry_price']) * pos_info['shares']
            logger.info(f"{symbol}: Current ${current_price:.2f}, Entry ${pos_info['entry_price']:.2f}, P&L: ${pnl:.2f}")
    
    async def scan_for_opportunities(self):
        """Scan watchlist for trading opportunities"""
        for symbol in self.watchlist:
            # Skip if we already have a position
            if symbol in self.positions:
                continue
            
            # Skip if we've hit daily loss limit
            if self.daily_pnl <= -self.max_daily_loss:
                logger.warning("Daily loss limit reached. Stopping new trades.")
                break
            
            contract = self.create_stock_contract(symbol)
            df = await self.get_historical_data(contract)
            
            if df is not None:
                is_breakout, reason = self.analyze_momentum(df)
                logger.info(f"{symbol}: {reason}")
                
                if is_breakout:
                    await self.place_buy_order(contract, self.max_position_size)
                    await asyncio.sleep(1)  # Avoid rapid-fire orders
    
    async def run_strategy(self, duration_minutes=60):
        """Run the trading strategy"""
        logger.info("="*50)
        logger.info("STARTING SIMPLE MOMENTUM TRADER")
        logger.info("="*50)
        logger.info(f"Paper Trading Port: {self.port}")
        logger.info(f"Max Position Size: ${self.max_position_size}")
        logger.info(f"Stop Loss: {self.stop_loss_pct*100}%")
        logger.info(f"Take Profit: {self.take_profit_pct*100}%")
        logger.info(f"Watchlist: {', '.join(self.watchlist)}")
        logger.info("="*50)
        
        if not await self.connect():
            return
        
        try:
            end_time = datetime.now() + timedelta(minutes=duration_minutes)
            
            while datetime.now() < end_time:
                logger.info(f"\n--- Trading Loop at {datetime.now().strftime('%H:%M:%S')} ---")
                
                # Check exit conditions for existing positions
                await self.check_exit_conditions()
                
                # Scan for new opportunities
                await self.scan_for_opportunities()
                
                # Wait before next iteration
                logger.info("Waiting 60 seconds before next scan...")
                await asyncio.sleep(60)
                
        except KeyboardInterrupt:
            logger.info("Trading stopped by user")
        except Exception as e:
            logger.error(f"Error in trading loop: {e}")
        finally:
            self.disconnect()

async def main():
    # IMPORTANT: Always start with paper trading!
    trader = SimpleMomentumTrader(
        host='127.0.0.1',
        port=7497,  # Paper trading port
        client_id=2
    )
    
    # Run for 1 hour (you can adjust this)
    await trader.run_strategy(duration_minutes=60)

if __name__ == "__main__":
    print("="*60)
    print("EDUCATIONAL TRADING BOT - PAPER TRADING ONLY")
    print("="*60)
    print("⚠️  WARNING: This is for educational purposes only!")
    print("⚠️  Start with paper trading (port 7497)")
    print("⚠️  Never risk money you can't afford to lose")
    print("⚠️  Past performance ≠ future results")
    print("="*60)
    
    response = input("Type 'PAPER' to confirm you're using paper trading: ")
    if response.upper() == 'PAPER':
        asyncio.run(main())
    else:
        print("Please start with paper trading first!")
