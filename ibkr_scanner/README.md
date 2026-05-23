# 🚀 IB Scanner - Interactive Brokers Trading Scanner & Auto Trader

A comprehensive Python-based trading system that scans for technical analysis opportunities and can automatically execute trades through Interactive Brokers (IB).

## ⚠️ **IMPORTANT DISCLAIMER**

**This software is for educational and research purposes. Trading involves significant risk and you can lose money. Always test thoroughly in paper trading mode first. Use at your own risk.**

## 🎯 **Features**

### 📊 **Technical Scanner**
- **Multi-timeframe Analysis**: 1min to 1week intervals
- **Advanced Indicators**: MACD, RSI, CCI, ADX, Stochastic, Williams %R, Bollinger Bands
- **Trendline Analysis**: Automatic support/resistance detection
- **Preset Configurations**: Day trading, swing trading, position trading, crypto-style, conservative
- **Dual Signal Detection**: Both long and short opportunities
- **Real-time Scoring**: 0-100 momentum scoring system

### 🤖 **Auto Trader**
- **Risk Management**: Daily loss limits, position sizing, trailing stops
- **Process Separation**: Scanner and trader run in separate processes to avoid IB connection conflicts
- **Paper/Live Trading**: Easy switching between paper (7497) and live (7496) trading
- **Position Management**: Automatic position monitoring and closure
- **Safety Features**: Preview mode, emergency stops, auto-close at market end

### 🌍 **Market Support**
- **US Stocks**: Major exchanges with real-time data
- **HKSE**: Hong Kong Stock Exchange support
- **Multiple Scanners**: Technical, momentum, and specialized scanners

## 🚀 **Quick Start**

### Prerequisites
- Python 3.8+
- Interactive Brokers TWS or IB Gateway
- Active IB account (paper or live)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/ib_scanner.git
cd ib_scanner
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure IB Connection**
   - Start TWS or IB Gateway
   - Enable API connections in TWS settings
   - Note your port: 7497 (paper) or 7496 (live)

### Basic Usage

#### 1. **Run Scanner Only**
```bash
# Paper trading with day trading preset
python technical_scanner.py --paper --preset day_trading

# Live trading with custom settings
python technical_scanner.py --live --interval 5min --min-score 70
```

#### 2. **Run Complete Auto Trading System**
```bash
# Preview mode (safe - no real trades)
python run_separated_trader.py --paper

# Auto-execute trades (real money - be careful!)
python run_separated_trader.py --live --auto-execute
```

## 📋 **System Components**

| Component | Description | File |
|-----------|-------------|------|
| **Technical Scanner** | Main scanning engine with technical analysis | `technical_scanner.py` |
| **Auto Day Trader** | Automated trading execution | `auto_day_trader.py` |
| **Separated Trader** | Process-separated trading system | `run_separated_trader.py` |
| **HKSE Scanner** | Hong Kong market scanner | `hkse_scanner.py` |
| **Momentum Scanner** | Momentum-based scanning | `momentum_scanner.py` |
| **Stock Scanner** | Basic stock scanning | `stock_scanner.py` |
| **Configuration** | Trading presets and settings | `scanner_configs.json` |

## ⚙️ **Configuration**

### Trading Presets

The system includes 5 pre-configured trading strategies:

- **Day Trading**: Fast signals for intraday trading
- **Swing Trading**: Balanced signals for 2-5 day holds
- **Position Trading**: Slower signals for longer-term positions
- **Crypto Style**: Sensitive settings for volatile assets
- **Conservative**: Reduced false signals for safer trading

### Connection Settings

```bash
# Paper Trading (Recommended for testing)
python technical_scanner.py --paper

# Live Trading (Real money - use with caution)
python technical_scanner.py --live

# Custom host and client ID
python technical_scanner.py --host 127.0.0.1 --client-id 5
```

### Scanner Parameters

```bash
# Time intervals
--interval 1min|5min|15min|30min|1hour|1day

# Minimum score threshold
--min-score 50    # Lower = more results
--min-score 80    # Higher = fewer, higher quality results

# Maximum results
--max-results 20  # Number of stocks to analyze

# Price filter
--min-price 5.0   # Minimum stock price
```

## 🛡️ **Safety Features**

### Risk Management
- **Daily Loss Limits**: Automatic stop at configured loss percentage
- **Position Sizing**: Configurable percentage of account per trade
- **Trailing Stops**: Dynamic profit protection
- **Maximum Positions**: Limit concurrent open positions

### Safety Modes
- **Preview Mode**: Shows what trades would be placed without executing
- **Paper Trading**: Test with virtual money
- **Auto-Close**: Closes all positions at market close
- **Emergency Stop**: Manual override to stop all trading

## 📊 **Example Workflows**

### Conservative Day Trading
```bash
# 1. Run scanner with conservative settings
python technical_scanner.py --paper --preset day_trading --interval 5min --min-score 75

# 2. Preview auto trader
python run_separated_trader.py --paper --max-daily-loss 2.0 --position-size 1.5

# 3. Execute trades (when ready)
python run_separated_trader.py --paper --auto-execute --max-daily-loss 2.0 --position-size 1.5
```

### Swing Trading
```bash
# 1. Run scanner for swing opportunities
python technical_scanner.py --paper --preset swing_trading --interval 1hour --min-score 60

# 2. Execute swing trades
python run_separated_trader.py --paper --auto-execute --max-positions 3 --trailing-stop 3.0
```

## 🔧 **Advanced Usage**

### Custom Indicator Settings
```bash
# Fast MACD for day trading
python technical_scanner.py --paper --macd-fast 5 --macd-slow 13 --macd-signal 4

# Sensitive RSI
python technical_scanner.py --paper --rsi-period 9 --rsi-oversold 25 --rsi-overbought 75

# Strict ADX for strong trends
python technical_scanner.py --paper --adx-period 10 --adx-threshold 30
```

### Multiple Market Scanning
```bash
# US Stocks
python technical_scanner.py --paper --location-code STK.US.MAJOR

# Hong Kong Stocks
python hkse_scanner.py --paper
```

## 📁 **Project Structure**

```
ib_scanner/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── LICENSE                      # License information
├── .gitignore                   # Git ignore rules
├── scanner_configs.json         # Trading presets
├── technical_scanner.py         # Main technical scanner
├── auto_day_trader.py           # Auto trading engine
├── run_separated_trader.py      # Process-separated trader
├── hkse_scanner.py              # Hong Kong market scanner
├── momentum_scanner.py          # Momentum-based scanner
├── stock_scanner.py             # Basic stock scanner
├── scanner_results/             # Scanner output files
│   └── scanner_results_*.json
├── AUTO_TRADER_README.md        # Auto trader documentation
└── SEPARATED_TRADER_README.md   # Separated trader documentation
```

## 🚨 **Important Notes**

### Before Using
- [ ] Test thoroughly in paper trading mode
- [ ] Understand all risk parameters
- [ ] Have emergency stop procedures ready
- [ ] Never risk more than you can afford to lose

### During Trading
- [ ] Monitor positions regularly
- [ ] Check daily P&L
- [ ] Verify stop orders are active
- [ ] Watch for system errors

### Risk Warnings
- **Automated trading involves significant risk**
- **You can lose money rapidly**
- **Past performance does not guarantee future results**
- **Always test in paper trading first**

## 🤝 **Contributing**

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 **Support**

For issues and questions:
1. Check the documentation in the README files
2. Review the troubleshooting sections
3. Test in paper trading mode first
4. Open an issue on GitHub

## 🔗 **Related Documentation**

- [Auto Trader Guide](AUTO_TRADER_README.md) - Detailed auto trading documentation
- [Separated Trader Guide](SEPARATED_TRADER_README.md) - Process separation system
- [Scanner Configurations](scanner_configs.json) - Trading preset definitions

---

**⚠️ Remember: Trading involves risk. Use this software responsibly and at your own risk.**
