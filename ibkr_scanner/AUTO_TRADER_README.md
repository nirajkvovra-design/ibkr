# 🚀 AUTO DAY TRADER - Automated Trading System

## ⚠️ **IMPORTANT DISCLAIMER**
**This is automated trading software that can execute real trades with real money. Use at your own risk. Always test thoroughly in paper trading mode first.**

## 🎯 **What It Does**
The Auto Day Trader automatically executes trades based on your scanner results with:
- **Risk Management**: Maximum daily loss limits
- **Position Sizing**: Automatic position sizing per trade
- **Trailing Stops**: Dynamic profit protection
- **Real-time Monitoring**: Continuous position tracking
- **Auto-close**: Closes all positions at market close

## 🔧 **System Components**

### 1. **Scanner** (`technical_scanner.py`)
- Scans for trading opportunities
- Generates JSON results file
- Supports day trading presets

### 2. **Auto Trader** (`auto_day_trader.py`)
- Reads scanner results
- Executes trades automatically
- Manages risk and positions

### 3. **Runner Script** (`run_auto_trader.py`)
- Orchestrates the entire process
- User-friendly interface
- Safety confirmations

## 🚀 **Quick Start (SAFE MODE)**

### Step 1: Run Scanner
```bash
python technical_scanner.py --preset day_trading --interval 5min --max-results 10 --min-score 70
```

### Step 2: Preview Trades (NO EXECUTION)
```bash
python auto_day_trader.py --scanner-file scanner_results/scanner_results_YYYYMMDD_HHMMSS.json
```

### Step 3: Run Complete System
```bash
python run_auto_trader.py
```

## ⚙️ **Configuration Options**

### **Risk Management**
```bash
--max-daily-loss 3.0      # Maximum 3% loss per day
--position-size 2.0       # 2% of account per trade
--trailing-stop 2.0       # 2% trailing stop
--max-positions 5         # Maximum 5 concurrent positions
```

### **Trading Session**
```bash
--session-duration 390    # 6.5 hours (market open to close)
--auto-execute            # Actually place trades (DANGEROUS!)
```

### **Connection Settings**
```bash
--host 127.0.0.1         # IB TWS/Gateway host
--port 7497              # 7497=paper, 7496=live
--client-id 10           # Unique client ID
```

## 🛡️ **Safety Features**

### **1. Preview Mode (Default)**
- Shows what trades WOULD be placed
- No actual orders submitted
- Safe for testing and learning

### **2. Risk Limits**
- Daily loss limits automatically enforced
- Position size limits per trade
- Maximum concurrent positions

### **3. Auto-Close Protection**
- Closes all positions at market close
- Prevents overnight risk
- Enforces day trading rules

### **4. Trailing Stops**
- Automatically locks in profits
- Reduces downside risk
- Dynamic stop adjustment

## 📊 **Example Usage Scenarios**

### **Scenario 1: Conservative Day Trading**
```bash
python auto_day_trader.py \
  --scanner-file scanner_results/scanner_results_20241201_093000.json \
  --max-daily-loss 2.0 \
  --position-size 1.5 \
  --trailing-stop 1.5 \
  --max-positions 3
```

### **Scenario 2: Aggressive Day Trading**
```bash
python auto_day_trader.py \
  --scanner-file scanner_results/scanner_results_20241201_093000.json \
  --max-daily-loss 5.0 \
  --position-size 3.0 \
  --trailing-stop 2.5 \
  --max-positions 8
```

### **Scenario 3: Scalping (High Frequency)**
```bash
python auto_day_trader.py \
  --scanner-file scanner_results/scanner_results_20241201_093000.json \
  --max-daily-loss 3.0 \
  --position-size 1.0 \
  --trailing-stop 1.0 \
  --max-positions 10 \
  --session-duration 240  # 4 hours
```

## 🔍 **How It Works**

### **1. Scanner Phase**
```
Scanner → Technical Analysis → Score Ranking → JSON Results
```

### **2. Auto-Trader Phase**
```
Load Results → Risk Check → Execute Trades → Monitor Positions
```

### **3. Position Management**
```
Entry → Trailing Stop → Profit Lock → Auto-Close
```

## 📈 **Risk Management Strategy**

### **Entry Rules**
- Minimum score: 70/100
- Maximum positions: 5 (configurable)
- Position size: 2% of account (configurable)

### **Exit Rules**
- Trailing stop: 2% (configurable)
- Market close: Auto-close all positions
- Daily loss limit: 3% (configurable)

### **Position Sizing**
```
Account: $100,000
Position Size: 2% = $2,000
Stock Price: $50
Shares: $2,000 ÷ $50 = 40 shares
```

## 🚨 **Safety Checklist**

### **Before Running**
- [ ] IB TWS/Gateway connected
- [ ] Paper trading account active
- [ ] Scanner results generated
- [ ] Risk parameters set
- [ ] Emergency stop plan ready

### **During Trading**
- [ ] Monitor positions regularly
- [ ] Check daily P&L
- [ ] Verify stop orders active
- [ ] Watch for system errors

### **After Trading**
- [ ] Review all trades
- [ ] Check position closures
- [ ] Analyze performance
- [ ] Adjust parameters if needed

## 🔧 **Troubleshooting**

### **Common Issues**

#### **1. Connection Failed**
```bash
# Check IB TWS/Gateway
# Verify port settings
# Ensure unique client ID
```

#### **2. No Scanner Results**
```bash
# Run scanner first
# Check file permissions
# Verify JSON format
```

#### **3. Orders Not Filling**
```bash
# Check market hours
# Verify account permissions
# Check order types
```

#### **4. Trailing Stops Not Working**
```bash
# Verify stop order placement
# Check order status
# Monitor price updates
```

## 📚 **Advanced Features**

### **1. Custom Risk Models**
```python
# Modify auto_day_trader.py
class CustomRiskModel:
    def calculate_position_size(self, account_value, volatility):
        # Your custom logic here
        pass
```

### **2. Multi-Strategy Support**
```bash
# Run multiple scanners
python technical_scanner.py --preset day_trading
python technical_scanner.py --preset swing_trading
python auto_day_trader.py --scanner-file combined_results.json
```

### **3. Performance Analytics**
```python
# Add to auto_day_trader.py
def generate_performance_report(self):
    # Calculate Sharpe ratio, drawdown, etc.
    pass
```

## 🎯 **Best Practices**

### **1. Start Small**
- Begin with paper trading
- Use small position sizes
- Test thoroughly before live

### **2. Monitor Constantly**
- Check positions every 15 minutes
- Monitor daily P&L
- Watch for system issues

### **3. Regular Reviews**
- Weekly performance analysis
- Monthly parameter adjustment
- Quarterly strategy review

### **4. Risk Management**
- Never exceed daily loss limits
- Diversify across multiple stocks
- Use appropriate position sizing

## 📞 **Support & Maintenance**

### **Regular Tasks**
- Update scanner parameters
- Review risk settings
- Monitor system performance
- Backup configuration files

### **Emergency Procedures**
- Stop all trading immediately
- Close all positions manually
- Check system logs
- Contact support if needed

## 🚀 **Next Steps**

1. **Test in Paper Trading**: Run the system with paper money first
2. **Start Small**: Begin with conservative risk parameters
3. **Monitor Performance**: Track results and adjust parameters
4. **Scale Gradually**: Increase position sizes as you gain confidence
5. **Continuous Learning**: Study market conditions and adjust strategies

## ⚠️ **Final Warning**

**Automated trading involves significant risk. You can lose money rapidly. Always:**
- Test thoroughly in paper trading
- Start with small amounts
- Monitor the system constantly
- Have emergency stop procedures
- Never risk more than you can afford to lose

**Use this system at your own risk and responsibility.**
