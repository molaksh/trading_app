"""
Configuration and constants for the trading screener.
ML-ready format: all parameters centralized and versioned.
"""

import logging

# ============================================================================
# PORTFOLIO AND RISK PARAMETERS
# ============================================================================
START_CAPITAL = 100000

# ============================================================================
# DATA WINDOWS AND LOOKBACK PERIODS (trading days)
# ============================================================================
LOOKBACK_DAYS = 252              # ~1 trading year for indicator history
MIN_HISTORY_DAYS = 210           # Minimum required for valid features
SMA_SHORT = 20                   # Short-term trend window
SMA_LONG = 200                   # Long-term trend window
ATR_PERIOD = 14                  # ATR calculation period
VOLUME_LOOKBACK = 20             # Volume average window
SMA_SLOPE_WINDOW = 5             # Slope calculation window

# ============================================================================
# FEATURE COMPUTATION THRESHOLDS
# ============================================================================
# Scoring rules: +1 each if condition met
THRESHOLD_PULLBACK = 0.05        # Pullback depth < 5%
THRESHOLD_VOLUME_RATIO = 1.2     # Volume > 1.2x average (20% surge)
THRESHOLD_ATR_PCT = 0.03         # ATR < 3% of price (stable)
THRESHOLD_SMA_SLOPE = 0.0        # SMA20 slope > 0 (positive momentum)

# ============================================================================
# CONFIDENCE SCORE BOUNDS
# ============================================================================
MIN_CONFIDENCE = 1
MAX_CONFIDENCE = 5

# ============================================================================
# DISPLAY AND OUTPUT SETTINGS
# ============================================================================
TOP_N_CANDIDATES = 20
PRINT_WIDTH = 120

# ============================================================================
# BACKTEST SETTINGS
# ============================================================================
BACKTEST_LOOKBACK_YEARS = 5      # Years of historical data for backtest
HOLD_DAYS = 5                    # Days to hold each position
BACKTEST_MIN_CONFIDENCE = 3      # Minimum confidence to enter trade

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
