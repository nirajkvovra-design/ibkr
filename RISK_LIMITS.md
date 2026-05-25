# Quantitative Risk Limits & Safety Mandates

This document outlines the strict quantitative boundaries, exposure limitations, and automated risk scaling parameters enforced by the `RiskManager` and `MacroIntelligenceEngine`.

---

## 1. Capital Allocation & Sizing Constraints
* **Position Sizing Cap (Dynamic Scaling):** Capped at a maximum percentage of net account liquidation value:
  $$\text{Max Position Sizing} = \text{AccountValue} \times \text{MAX\_PORTFOLIO\_POSITION\_PERCENT}$$
  - Default: `5%` (`0.05`) of account cash per trade.
* **Maximum Open Positions:** Restricted to a maximum of `1` active open position simultaneously under starter/volatile modes, scaling to `5` positions under low-volatility regimes.
* **Starter Account Mode:** If `STARTER_ACCOUNT_MODE` is enabled, position size is strictly capped at a fixed `$50` (or `STARTER_ACCOUNT_CAPITAL` equivalent) to protect small accounts.

---

## 2. Leverage Regulation Under Macro Stress
The platform regulates leverage dynamically based on the market regime classified by the `MacroIntelligenceEngine`:

| Macro Regime | Leverage Cap | Position Exposure Multiplier | Stop-Loss Width | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **`LOW_VOL_TREND`** | 2.0x (Standard Margin) | 1.0x | 1.0x | Default baseline state |
| **`HIGH_VOL_TREND`** | 1.5x | 0.75x | 1.5x | Elevated volatility de-risking |
| **`GEOPOLITICAL_SHOCK`** | 1.0x (Cash-Only) | 0.40x | 1.5x | Commodity & supply shock de-risking |
| **`INFLATION_SHOCK`** | 1.0x (Cash-Only) | 0.50x | 1.5x | Bond yield volatility stress |
| **`PANIC`** | 1.0x (Cash-Only) | 0.25x | 1.5x | Short-selling & options disabled |
| **`LIQUIDITY_CRISIS`** | 1.0x (Cash-Only) | 0.15x | 1.5x | Extreme liquidity stress lockdown |

---

## 3. Parametric Value at Risk (VaR) Safety Gate
- **VaR Safety Gate:** The platform evaluates 95% Parametric Value at Risk (VaR) before submitting new order signals.
- **Limit:** Total portfolio VaR must NOT exceed `5%` (`0.05`) of net account liquidation value. Any trade that breaches this limit will be programmatically blocked.

---

## 4. Drawdown Circuit Breakers & Loss Caps
* **Max Daily Loss Limit:** Set at a strict dollar cap or percentage cap relative to capital growth:
  $$\text{Daily Loss Limit} = \text{AccountValue} \times \left( \frac{\text{MAX\_DAILY\_LOSS}}{\text{STARTER\_ACCOUNT\_CAPITAL}} \right)$$
  - If daily P&L drops below this limit, the programmatic **Kill Switch** engages, blocking all new trades and triggering emergency exits for existing ones.
* **Transaction Fee-to-Profit Ratio Cap:** Expected execution fees must be $\le 35\%$ of expected trade profit (based on stop-loss/take-profit boundaries).

---

## 5. Event Blackout Windows & Blacklisting
* **Self-Learning Cool-Off Blacklist:** Any stock that experiences $\ge 2$ consecutive losses or drops below a `35%` win rate is programmatically blacklisted for `3` days.
* **Pre-Event Blackout Windows:** Blocks entries and buy signals during high-impact scheduled economic releases:
  - **FOMC Announcements:** 1-day buffer before the release.
  - **CPI Releases:** 1-day buffer before the release.
  - **Earnings Releases:** 3 days before and 1 day after the announcement.
  - **Dividend Releases:** 1 day before and 2 days after the ex-dividend date.
