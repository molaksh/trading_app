"""
Configuration and constants for the trading screener.
ML-ready format: all parameters centralized and versioned.
Supports multi-market: US (default) and INDIA via MARKET_MODE flag.
"""

import logging

# ============================================================================
# MARKET MODE: CONTROL US vs INDIA TRADING
# ============================================================================
MARKET_MODE = "INDIA"               # Options: "US" or "INDIA"
INDIA_MODE = MARKET_MODE == "INDIA"
US_MODE = MARKET_MODE == "US"

# ============================================================================
# INDIA VALIDATION MODE: RULES-ONLY BEFORE ML
# ============================================================================
# When True: ML model disabled, rules-based only
# When False: Use ML model (after validation complete)
# REQUIRED: Must be True during initial India paper trading phase
INDIA_RULES_ONLY = True          # SAFETY: Only disable after 20+ days validation

# ============================================================================
# INDIA OBSERVATION & BASELINE CONFIG
# ============================================================================
INDIA_MIN_OBSERVATION_DAYS = 20  # Minimum trading days before ML validation allowed
INDIA_OBSERVATION_LOG_DIR = "logs/india_observations"  # JSONL log storage
INDIA_ML_VALIDATION_ENABLED = False  # CLI override flag, requires explicit --run-india-ml-validation

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
# RISK & PORTFOLIO GOVERNANCE PARAMETERS
# ============================================================================
# Per-trade risk as % of account equity
RISK_PER_TRADE = 0.01            # Risk 1% per trade

# Per-symbol maximum exposure as % of account
MAX_RISK_PER_SYMBOL = 0.02       # Max 2% exposure per symbol

# Portfolio heat: total open risk as % of account
MAX_PORTFOLIO_HEAT = 0.08        # Max 8% total portfolio risk

# Position sizing constraints
MAX_TRADES_PER_DAY = 4           # Max 4 new positions per day
MAX_CONSECUTIVE_LOSSES = 3       # Stop after 3 consecutive losing trades
DAILY_LOSS_LIMIT = 0.02          # Stop if daily loss exceeds 2%

# Confidence-based position sizing multipliers
CONFIDENCE_RISK_MULTIPLIER = {
    1: 0.25,                      # Confidence 1: 25% of base risk
    2: 0.50,                      # Confidence 2: 50% of base risk
    3: 0.75,                      # Confidence 3: 75% of base risk
    4: 1.00,                      # Confidence 4: 100% of base risk
    5: 1.25,                      # Confidence 5: 125% of base risk (slightly more aggressive)
}

# ML-based confidence sizing control
# When disabled: confidence multiplier always uses 1.0 (neutral sizing)
# When enabled: confidence multiplier respected from CONFIDENCE_RISK_MULTIPLIER
ENABLE_ML_SIZING = True          # Set to False to disable confidence-based scaling

# ============================================================================
# EXECUTION REALISM PARAMETERS (Phase G)
# ============================================================================
# Slippage: basis points (bps) charged on fills
ENTRY_SLIPPAGE_BPS = 5           # 5 bps = 0.05% on entry
EXIT_SLIPPAGE_BPS = 5            # 5 bps = 0.05% on exit

# Liquidity check: reject positions that exceed % of daily volume
MAX_POSITION_ADV_PCT = 0.05      # Position size max 5% of average daily volume

# Entry timing for backtests
USE_NEXT_OPEN_ENTRY = True       # True: use next day's open (realistic)
                                 # False: use same day's close (optimistic)

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
# PAPER TRADING (Phase I)
# ============================================================================
# SAFETY: Paper trading only. Set to False to prevent execution.
RUN_PAPER_TRADING = False        # Set to True to enable paper trading
PAPER_TRADING_MODE_REQUIRED = True  # Safety: fail if not in paper trading mode

# Paper trading broker
PAPER_TRADING_BROKER = "alpaca"  # Currently supported: "alpaca"

# ============================================================================
# MONITORING & DEGRADATION DETECTION (Phase H)
# ============================================================================
# Global monitoring settings
RUN_MONITORING = True            # Enable all monitoring features
ENABLE_AUTO_PROTECTION = True    # Enable auto-protection when degradation detected

# Confidence distribution monitoring
ENABLE_CONFIDENCE_MONITORING = True
CONFIDENCE_INFLATION_THRESHOLD = 0.30  # Flag if >30% are confidence 5
CONFIDENCE_COLLAPSE_THRESHOLD = 0.10   # Flag if <10% are confidence 4-5
CONFIDENCE_MIN_WINDOW_SIZE = 20        # Minimum signals before checking

# Performance degradation monitoring
ENABLE_PERFORMANCE_MONITORING = True
PERFORMANCE_MIN_TIER_TRADES = 10       # Min trades per tier before checking
WIN_RATE_ALERT_THRESHOLD = 0.40        # Flag if win rate < 40%
AVG_RETURN_ALERT_THRESHOLD = -0.01     # Flag if avg return < -1%

# Feature drift monitoring
ENABLE_FEATURE_DRIFT_MONITORING = True
FEATURE_DRIFT_ZSCORE_THRESHOLD = 3.0   # Flag if z-score > 3.0
FEATURE_DRIFT_LOOKBACK_WINDOW = 60     # Recent window (days)
FEATURE_DRIFT_BASELINE_WINDOW = 250    # Long-term baseline (days)

# Auto-protection settings
MAX_CONSECUTIVE_ALERTS = 3             # Trigger protection after N alerts
AUTO_PROTECTION_DISABLES_ML_SIZING = True  # Protection disables ML confidence scaling
AUTO_PROTECTION_REVERSIBLE = True      # Can re-enable after investigation

# ============================================================================
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
# ============================================================================
# INDIA MARKET SPECIFIC PARAMETERS (NSE)
# ============================================================================
# When MARKET_MODE == "INDIA", these parameters override US defaults
if INDIA_MODE:
    # India risk parameters (more conservative for lower liquidity)
    BASE_RISK_PCT = 0.0075           # 0.75% base risk (vs 1% US)
    MAX_RISK_PER_SYMBOL = 0.015      # 1.5% max per symbol (vs 2% US)
    MAX_PORTFOLIO_HEAT = 0.05        # 5% max portfolio heat (vs 8% US)
    MAX_TRADES_PER_DAY = 2           # 2 trades/day max (vs 4 US)
    
    # India liquidity assumptions
    MAX_POSITION_ADV_PCT = 0.02      # 2% of ADV (vs 5% US) - tighter
    ENTRY_SLIPPAGE_BPS = 10          # 10 bps = 0.10% (vs 5 bps US)
    EXIT_SLIPPAGE_BPS = 10           # 10 bps = 0.10% (vs 5 bps US)
    
    # India labeling
    LABEL_HORIZON_DAYS = 7           # 7-day horizon (vs 5 US)
    LABEL_TARGET_RETURN = 0.025      # +2.5% target (vs 2% US)
    LABEL_MAX_DRAWDOWN = -0.015      # -1.5% max drawdown (vs -1% US)