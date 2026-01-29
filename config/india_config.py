"""
India-specific configuration for NSE paper trading.

Market: india
Broker: nse_simulator
Mode: swing
Instrument: equity
"""

# ============================================================================
# MARKET CONFIGURATION
# ============================================================================

# Market timezone
MARKET_TIMEZONE = "Asia/Kolkata"

# Market hours (IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# ============================================================================
# SWING TRADING CONFIGURATION
# ============================================================================

# Entry window: last N minutes before close
ENTRY_WINDOW_MINUTES_BEFORE_CLOSE = 20

# Exit evaluation: after close
SWING_EXIT_DELAY_MINUTES_AFTER_CLOSE = 15

# ============================================================================
# UNIVERSE CONFIGURATION
# ============================================================================

# Use NSE swing universe
USE_NSE_SWING_UNIVERSE = True

# Universe file
UNIVERSE_MODULE = "universe.nse_swing_universe"

# ============================================================================
# DATA CONFIGURATION
# ============================================================================

# Data provider
DATA_PROVIDER = "nse"

# Historical data
HISTORICAL_LOOKBACK_DAYS = 365
DATA_CACHE_ENABLED = True

# ============================================================================
# BROKER CONFIGURATION
# ============================================================================

# Simulated broker
BROKER_NAME = "nse_simulator"

# Starting capital (₹)
STARTING_CAPITAL = 1_000_000  # ₹10 lakhs

# Brokerage (₹ per order)
BROKERAGE_PER_ORDER = 20

# Slippage range (%)
MIN_SLIPPAGE_PCT = 0.05
MAX_SLIPPAGE_PCT = 0.15

# ============================================================================
# RISK MANAGEMENT
# ============================================================================

# Max position size (% of portfolio)
MAX_POSITION_SIZE_PCT = 20.0

# Max portfolio risk per trade (%)
MAX_PORTFOLIO_RISK_PCT = 2.0

# Max total positions
MAX_TOTAL_POSITIONS = 5

# Max single position (₹)
MAX_SINGLE_POSITION_INR = 200_000  # ₹2 lakhs

# ============================================================================
# LOGGING
# ============================================================================

# Log level
LOG_LEVEL = "INFO"

# Log format
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
