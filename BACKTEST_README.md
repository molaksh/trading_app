"""Backtest module documentation and architecture."""

# ============================================================================
# BACKTEST MODULE - DIAGNOSTIC VALIDATION
# ============================================================================
#
# PURPOSE
# -------
# Evaluate whether higher confidence scores correlate with better returns.
# This is a research/diagnostic tool, NOT for production trading.
#
# ARCHITECTURE
# -----------
# backtest/
# ├── __init__.py
# ├── simple_backtest.py  - Trade simulation (Trade class, run_backtest)
# ├── metrics.py          - Statistics calculation (calculate_metrics, print_metrics)
#
# KEY COMPONENTS
# --------------
#
# 1. Trade Class (simple_backtest.py)
#    - Represents a single entry/exit trade
#    - Stores: symbol, entry_date, entry_price, exit_date, exit_price, confidence
#    - Calculates return_pct automatically
#
# 2. run_backtest(symbols) -> List[Trade]
#    - Iterates through historical dates
#    - For each symbol on each date:
#      * Load data up to that date (no lookahead bias)
#      * Compute features
#      * Score confidence
#      * If score >= BACKTEST_MIN_CONFIDENCE: simulate trade
#      * Track entry/exit with actual prices
#    - Returns list of all trades
#
# 3. calculate_metrics(trades) -> DataFrame
#    - Groups trades by confidence level
#    - Calculates per group:
#      * Trade count
#      * Win rate (% profitable)
#      * Average return
#      * Median return
#      * Max loss
#    - Returns summary DataFrame
#
# 4. print_metrics(trades) -> None
#    - Formats and logs metrics table
#    - Clean output showing confidence vs performance
#
# ENTRY RULES
# -----------
# - Confidence >= BACKTEST_MIN_CONFIDENCE (config)
# - Entry price: next day open (or close if unavailable)
# - No overlapping positions per symbol (one trade at a time)
# - Overlapping trades allowed across symbols
#
# EXIT RULES
# ----------
# - Time-based: HOLD_DAYS from entry (config)
# - Exit price: open price on exit date (or close if unavailable)
# - No early exit
#
# CONFIGURATION (config/settings.py)
# ----------------------------------
# BACKTEST_LOOKBACK_YEARS = 5    # Years of history to test
# HOLD_DAYS = 5                  # Days to hold each position
# BACKTEST_MIN_CONFIDENCE = 3    # Min confidence to enter
#
# RUNNING THE BACKTEST
# --------------------
#
# Option 1: Integrated with screener
# Set in main.py:
#   RUN_BACKTEST = True
# Then run:
#   python3 main.py
#
# Option 2: Demo with synthetic trades
#   python3 demo_backtest.py
#
# EXAMPLE OUTPUT
# ---------------
# Conf   Trades   WinRate    AvgReturn    MedianRet    MaxLoss
# ----   ------   -------    ---------    ---------    -------
# 5      120      62.0%      1.80%        1.20%       -2.50%
# 4      240      56.0%      1.10%        0.60%       -4.20%
# 3      300      51.0%      0.40%        0.10%       -5.80%
#
# INTERPRETATION
# ---------------
# - Higher confidence generally has higher win rate and avg return
# - This validates the scoring system for research purposes
# - NOT suitable for live trading (survivorship bias, data issues, etc.)
#
# LIMITATIONS
# -----------
# - No commissions or slippage
# - Position size always 1 unit
# - No portfolio-level risk management
# - Historical data quality issues (missing data, gaps)
# - Possible survivorship bias in symbol universe
# - No accounting for corporate actions (splits, dividends)
# - No rebalancing or portfolio rules
#
# FUTURE ENHANCEMENTS (NOT IMPLEMENTED)
# --------------------------------------
# - Money management (Kelly criterion, position sizing)
# - Risk metrics (Sharpe ratio, sortino ratio)
# - Walk-forward testing
# - Parameter sensitivity analysis
# - Broker simulation (commissions, slippage)
# - Live trading integration
