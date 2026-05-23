# Contributing to IB Scanner

Thank you for your interest in contributing to IB Scanner! This document provides guidelines and information for contributors.

## 🚀 Getting Started

### Prerequisites
- Python 3.8 or higher
- Git
- Interactive Brokers account (paper trading recommended for testing)
- Basic understanding of trading and technical analysis

### Development Setup

1. **Fork the repository**
   ```bash
   # Fork on GitHub, then clone your fork
   git clone https://github.com/yourusername/ib_scanner.git
   cd ib_scanner
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Test the installation**
   ```bash
   python technical_scanner.py --help
   ```

## 📋 Contribution Guidelines

### Types of Contributions

We welcome several types of contributions:

- **Bug Reports**: Report issues and bugs
- **Feature Requests**: Suggest new features or improvements
- **Code Contributions**: Submit code improvements or new features
- **Documentation**: Improve documentation and examples
- **Testing**: Add tests or improve test coverage

### Code Style

- Follow PEP 8 Python style guidelines
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and reasonably sized
- Add comments for complex logic

### Commit Messages

Use clear, descriptive commit messages:

```
feat: add new technical indicator support
fix: resolve IB connection timeout issue
docs: update README with new examples
test: add unit tests for scanner functions
```

### Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write clean, well-documented code
   - Test your changes thoroughly
   - Update documentation if needed

3. **Test your changes**
   ```bash
   # Test in paper trading mode
   python technical_scanner.py --paper --preset day_trading
   ```

4. **Submit a pull request**
   - Provide a clear description of changes
   - Reference any related issues
   - Include screenshots if applicable

## 🧪 Testing Guidelines

### Testing Requirements

- **Always test in paper trading mode first**
- Test with different market conditions
- Verify error handling and edge cases
- Test with various configuration options

### Test Scenarios

```bash
# Basic functionality test
python technical_scanner.py --paper --preset day_trading

# Different timeframes
python technical_scanner.py --paper --interval 1min
python technical_scanner.py --paper --interval 1hour

# Different presets
python technical_scanner.py --paper --preset swing_trading
python technical_scanner.py --paper --preset conservative

# Auto trader testing
python run_separated_trader.py --paper --show-scanner-status
```

### Safety Testing

- Never test with live trading unless absolutely necessary
- Use small position sizes for any live testing
- Always have emergency stop procedures ready
- Document any issues or unexpected behavior

## 🐛 Bug Reports

When reporting bugs, please include:

1. **Environment Information**
   - Python version
   - Operating system
   - IB TWS/Gateway version
   - Dependencies versions

2. **Steps to Reproduce**
   - Exact commands used
   - Configuration settings
   - Expected vs actual behavior

3. **Error Information**
   - Full error messages
   - Stack traces
   - Log files (if applicable)

4. **Additional Context**
   - Screenshots if helpful
   - Related issues
   - Workarounds if any

## 💡 Feature Requests

When suggesting features:

1. **Describe the feature clearly**
   - What problem does it solve?
   - How would it work?
   - Who would benefit from it?

2. **Provide context**
   - Use cases and examples
   - Related features
   - Potential implementation approach

3. **Consider alternatives**
   - Are there existing solutions?
   - Could existing features be extended?

## 🔧 Development Areas

### High Priority
- **Performance Optimization**: Improve scanning speed and efficiency
- **Additional Indicators**: Add more technical analysis indicators
- **Risk Management**: Enhance risk management features
- **Documentation**: Improve user guides and examples

### Medium Priority
- **UI/UX**: Create web interface or GUI
- **Backtesting**: Add historical backtesting capabilities
- **Multi-Market**: Support for additional markets
- **Alerts**: Add notification and alerting system

### Low Priority
- **Mobile Support**: Mobile app or responsive web interface
- **Advanced Analytics**: Performance analytics and reporting
- **Integration**: Integration with other trading platforms
- **Machine Learning**: ML-based signal generation

## 📚 Code Documentation

### Function Documentation
```python
def calculate_rsi(prices, period=14):
    """
    Calculate Relative Strength Index (RSI).
    
    Args:
        prices (list): List of price values
        period (int): RSI calculation period (default: 14)
    
    Returns:
        float: RSI value between 0 and 100
        
    Raises:
        ValueError: If prices list is empty or period is invalid
    """
    # Implementation here
```

### Class Documentation
```python
class TechnicalScanner:
    """
    Technical analysis scanner for stock market opportunities.
    
    This class provides comprehensive technical analysis scanning
    capabilities with support for multiple indicators and timeframes.
    
    Attributes:
        host (str): IB connection host
        port (int): IB connection port
        client_id (int): IB client ID
    """
```

## 🚨 Safety Guidelines

### Trading Safety
- **Never commit live trading credentials**
- **Always test in paper trading first**
- **Use appropriate risk management**
- **Have emergency stop procedures**

### Code Safety
- **Validate all inputs**
- **Handle errors gracefully**
- **Use appropriate logging**
- **Follow security best practices**

## 📞 Getting Help

### Resources
- **GitHub Issues**: For bug reports and feature requests
- **Discussions**: For questions and general discussion
- **Documentation**: Check existing README files
- **Code Comments**: Read inline documentation

### Communication
- Be respectful and constructive
- Provide clear, detailed information
- Search existing issues before creating new ones
- Help others when you can

## 🎯 Recognition

Contributors will be recognized in:
- **README.md**: Listed as contributors
- **Release Notes**: Mentioned in relevant releases
- **GitHub**: Shown in contributor statistics

## 📄 License

By contributing to IB Scanner, you agree that your contributions will be licensed under the MIT License.

## ⚠️ Disclaimer

Remember that this software is for educational and research purposes. Trading involves significant risk. Contributors are not responsible for any financial losses incurred through the use of this software.

---

Thank you for contributing to IB Scanner! Your efforts help make this project better for everyone. 🚀
