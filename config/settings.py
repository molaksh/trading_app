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
# CAPITAL SIMULATION SETTINGS
# ============================================================================
STARTING_CAPITAL = 100000        # Initial account equity
BASE_RISK_PCT = 0.01             # Risk 1% of account per trade
CONFIDENCE_RISK_MAP = {
    1: 0.25,                      # Confidence 1: 25% of base risk
    2: 0.375,                     # Confidence 2: 37.5% of base risk
    3: 0.5,                       # Confidence 3: 50% of base risk
    4: 1.0,                       # Confidence 4: 100% of base risk
    5: 1.5,                       # Confidence 5: 150% of base risk
}

# ============================================================================
# ML DATASET LABEL CONFIGURATION
# ============================================================================
# Label definition: 1 if price reaches TARGET_RETURN within HORIZON
# WITHOUT falling below MAX_DRAWDOWN first, else 0
LABEL_HORIZON_DAYS = 5           # Days to look ahead for labeling
LABEL_TARGET_RETURN = 0.02       # +2% target return (2% profit)
LABEL_MAX_DRAWDOWN = -0.01       # -1% max drawdown tolerance

# Dataset output
DATASET_OUTPUT_DIR = "./data"    # Directory to save feature snapshots
DATASET_FILE_FORMAT = "parquet"  # Use 'parquet' or 'csv'

# ============================================================================
# ============================================================================
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
