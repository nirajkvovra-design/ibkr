# Paper → Live: Safe rollout plan

Run the bot on **paper/demo money first** for at least **3 market days** before using a live account.

## Phase 1 — Paper validation (3–5+ days)

1. Open **TWS Paper Trading** (not live). Enable API on port **7497**.
2. Start the engine each market day (9:30 AM–4:00 PM ET):
   ```bat
   run_paper_trading.bat
   ```
   If it is **already running**, starting it again triggers a **graceful restart**: no new buys, exit checks and open orders finish, then the new instance starts (avoids "client id already in use").
   Or:
   ```bash
   python paper_validation.py --test-cycle   # one manual test
   python trading_engine.py                  # leave running during RTH
   ```
3. Review progress anytime:
   ```bash
   python paper_validation.py --report
   ```
4. All activity is logged to:
   - `trading_logs.txt` — system log
   - `paper_trading_journal.jsonl` — trades & daily snapshots for learning
   - `trading_research.jsonl` — open/close research each cycle (even when no orders fire)

### Research & end-of-day exits

- **Every 3 minutes** (paper learning), the bot runs **market research**: watchlist, BUY/SELL/HOLD signals, blockers, and position exit ideas — logged even when it does not place orders.
- **At 3:55 PM ET** (5 min before close), it **closes all positions opened that day** (`daily_positions.json` tracks them).
- Set `CLOSE_TODAYS_POSITIONS_AT_EOD=False` in `.env` to disable auto flatten.

### Paper learning mode (default when `PAPER_TRADING=True`)

Tuned for **faster learning** on demo money only (override any value in `.env`; live uses stricter defaults):

| Setting | Paper learning | Live default |
|---------|----------------|--------------|
| Max position | $500 | $100 |
| Max trades / day | 5 | 1 |
| Open positions | 2 | 1 |
| Trading loop | every 3 min | every 5 min |
| Buy signal threshold | 2 (strong) | 4 |
| Bullish news required | No | Yes |
| Market regime filter | Off | On |
| Take profit / stop | 1.5% / 2% | 0.75% / 1.25% |

Set `PAPER_LEARNING_MODE=False` in `.env` to use conservative paper settings only.

### What you are validating

- Stable connection to IB paper API
- Orders submit and fill (limit orders)
- Stop-loss / take-profit exits behave as expected
- Risk limits (position size, daily loss, max trades) are respected
- Strategy signals match what you expect from the journal

### Readiness checklist

When ready to *consider* live:

```bash
python paper_validation.py --readiness
```

Default requirements (override in `.env`):

| Check | Default |
|--------|---------|
| Separate session days | 3 |
| Paper executions (fills) | 3 |
| Daily loss within `MAX_DAILY_LOSS` | Yes |
| Still on paper mode | Yes (until you switch deliberately) |

## Phase 2 — Go live (only after paper passes)

1. Complete paper period; review `paper_trading_journal.jsonl` and TWS paper P&L.
2. Copy `.env.example` → `.env` and set:
   ```env
   PAPER_TRADING=False
   IB_PORT=7496
   ENABLE_LIVE_TRADING=True
   STARTER_ACCOUNT_MODE=True
   REQUIRE_SETTLED_CASH_FOR_BUYS=True
   REQUIRE_MARKET_REGIME_CONFIRMATION=True
   ```
3. Use **live** TWS/IB Gateway on port **7496** with your funded account.
4. Start with small limits (`MAX_POSITION_SIZE`, `MAX_DAILY_LOSS`) and increase only after live behavior matches paper.

**Never** set `ENABLE_LIVE_TRADING=True` on a live port until paper validation passes and you have reviewed every failed trade in the journal.
