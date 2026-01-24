"""
QUICK REFERENCE - Trading Screener v1.0
========================================

FILE PURPOSES
=============

config/settings.py
  - All configuration parameters
  - Thresholds, lookback windows, scoring limits
  - Change here to tune behavior

universe/symbols.py
  - List of ~43 liquid US stocks to screen
  - Easy to add/remove symbols

data/price_loader.py
  - Loads real price data from yfinance
  - Returns clean DataFrame indexed by date
  - Handles missing data safely

data/synthetic_data.py
  - Generates realistic synthetic OHLCV data
  - Reproducible per symbol
  - Use for testing without network

features/feature_engine.py
  - Computes 9 technical indicators
  - No lookahead bias guaranteed
  - Returns DataFrame ready for scoring

scoring/rule_scorer.py
  - Converts features → confidence score (1-5)
  - 5 simple, interpretable rules
  - Easy to replace with ML model

main.py
  - Production screener (real yfinance data)
  - Handles network errors gracefully
  - Prints ranked candidates

demo.py
  - Demo screener (synthetic data)
  - No network required
  - Shows complete pipeline working


RUNNING THE SCREENER
====================

Setup:
  cd /path/to/trading_app
  python3 -m pip install -r requirements.txt

Demo (no internet needed):
  python3 demo.py

Production (requires internet):
  python3 main.py


FEATURE DESCRIPTIONS
====================

close              Latest closing price
sma_20             20-day moving average (short-term trend)
sma_200            200-day moving average (long-term trend)
dist_20sma         % from 20-day SMA (-0.05 = 5% below)
dist_200sma        % from 200-day SMA (+0.10 = 10% above)
sma20_slope        Linear slope of SMA20 over 5 days (momentum)
atr_pct            Average True Range as % of price (volatility)
vol_ratio          Current volume / 20-day avg (volume surge)
pullback_depth     % drop from 20-day high (support/consolidation)


INTERPRETING SCORES
===================

Confidence 5 (Strong Buy Signals):
  - Trading above 200-day SMA
  - Positive momentum (SMA20 sloping up)
  - Shallow pullback (near resistance)
  - Above-average volume
  - Low volatility (stable)
  → Momentum continuation play

Confidence 4 (Moderate Buy):
  - 4 of 5 criteria met
  → Worth monitoring, decent setup

Confidence 3 (Neutral/Mixed):
  - 3 of 5 criteria met
  → Requires additional analysis

Confidence 2 (Weak):
  - 2 of 5 criteria met
  → Avoid or wait for improvement

Confidence 1 (Strong Sell Signals):
  - 0-1 criteria met
  → Below trend, no momentum, high volatility
  → Skip or go short


MODIFYING SCORES
================

To adjust sensitivity:

In config/settings.py, modify thresholds:

THRESHOLD_PULLBACK = 0.05        # Make stricter: 0.03
THRESHOLD_VOLUME_RATIO = 1.2     # Make stricter: 1.5
THRESHOLD_ATR_PCT = 0.03         # Make stricter: 0.025

In scoring/rule_scorer.py, change point allocation:

score += 2 if dist_200sma > 0.10  # Higher weight for trend


ADDING NEW SYMBOLS
==================

Edit universe/symbols.py:

SYMBOLS = [
    'SPY',
    'YOUR_SYMBOL_HERE',  # Add here
    'AAPL',
]


ADDING NEW FEATURES
===================

In features/feature_engine.py:

1. Compute the indicator:
   result['my_indicator'] = ...

2. Add to output columns:
   output_cols = [..., 'my_indicator']

3. Use in scoring (scoring/rule_scorer.py):
   if features_row['my_indicator'] > threshold:
       score += 1


DATA PIPELINE EXAMPLE
=====================

CSV Data → yfinance → price_loader.py
                         ↓
                     df (OHLCV)
                         ↓
                   feature_engine.py
                         ↓
            features_df (9 indicators)
                         ↓
                   latest row
                         ↓
                   rule_scorer.py
                         ↓
            confidence score (1-5)
                         ↓
                   main.py
                         ↓
        Ranked table of candidates


DEPENDENCIES EXPLAINED
======================

pandas         2.1.3    # DataFrames, time series
numpy          1.24.3   # Numerical arrays, calculations
scipy          1.11.4   # Linear regression for slopes
yfinance       0.2.32   # Free stock data (optional, use demo.py if fails)
matplotlib     3.8.2    # (Optional) For future charting


NEXT STEPS (AFTER SCREENING)
=============================

1. Manual Review
   - Check charts on TradingView
   - Verify technical setup visually
   - Look for support/resistance

2. Fundamental Analysis
   - Earnings growth
   - Valuation (PE ratio)
   - Balance sheet health

3. Backtesting
   - Test rules on historical data
   - Measure win rate, profit factor
   - Optimize parameters

4. Paper Trading
   - Execute signals on paper account
   - Track performance vs screener
   - Validate in real conditions

5. Live Trading (if profitable)
   - Risk management first
   - Position sizing
   - Stop losses, take profits


DEBUGGING TIPS
==============

If screener hangs:
  - Ctrl+C to stop
  - Check internet connection
  - Try demo.py instead

If scores are wrong:
  - Print features_row in rule_scorer.py
  - Verify thresholds in config/settings.py
  - Check feature calculations in feature_engine.py

If no candidates found:
  - Check universe/symbols.py (any bad tickers?)
  - Increase LOOKBACK_DAYS if data is sparse
  - Lower confidence thresholds

Want to add logging?
  - Add print() statements in price_loader.py
  - Or use Python's logging module


VERSION HISTORY
===============

v1.0 (Jan 2026)
  - Initial screener: data loading, features, scoring
  - Rule-based confidence (1-5)
  - 43 liquid US stocks
  - Demo with synthetic data

v2.0 (Coming)
  - Backtesting module
  - ML-based scoring
  - Real-time alerts
  - Portfolio optimization

v3.0 (Future)
  - Live trading integration
  - Risk management
  - Position sizing
"""
