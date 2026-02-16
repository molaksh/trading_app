"""
Phase H Configuration: Crypto regime autonomy settings and feature flags.

All constants are configurable via environment variables.
Feature flags default to OFF (safe).
"""

import os

# ============================================================================
# FEATURE FLAGS
# ============================================================================
PHASE_H_CRYPTO_ENABLED = os.getenv("PHASE_H_CRYPTO_ENABLED", "false").lower() == "true"
PHASE_H_CRYPTO_LIVE_AUTONOMY = os.getenv("PHASE_H_CRYPTO_LIVE_AUTONOMY", "false").lower() == "true"
PHASE_H_CRYPTO_KILL_SWITCH = os.getenv("PHASE_H_CRYPTO_KILL_SWITCH", "false").lower() == "true"

# ============================================================================
# COMPOSITE MACRO WEIGHTS (must sum to 1.0)
# ============================================================================
MACRO_WEIGHTS = {
    "btc_regime": 0.40,
    "eth_regime": 0.20,
    "total_market_trend": 0.15,
    "alt_vs_btc_strength": 0.15,
    "volatility_expansion": 0.10,
}

# ============================================================================
# MACRO REGIME THRESHOLDS
# ============================================================================
MACRO_RISK_ON = 0.75
MACRO_NEUTRAL_LOW = 0.55
MACRO_RISK_OFF_LOW = 0.35

# ============================================================================
# ASSET REGIME THRESHOLDS
# ============================================================================
ASSET_VERY_STRONG = 0.75
ASSET_STRONG = 0.60
ASSET_NEUTRAL = 0.45

# ============================================================================
# EXPOSURE LADDER (base caps per macro regime)
# ============================================================================
EXPOSURE_CAPS = {
    "RISK_ON": 1.0,
    "NEUTRAL": 0.75,
    "RISK_OFF": 0.40,
    "PANIC": 0.10,
}
CONFIDENCE_CLAMP_LOW = 0.35
CONFIDENCE_CLAMP_HIGH = 0.95

# ============================================================================
# SCHEDULING
# ============================================================================
AUTONOMY_INTERVAL_MINUTES = 30
MIN_DWELL_HOURS = 4.0

# ============================================================================
# FLIP BUDGET
# ============================================================================
MAX_FLIPS_PER_7_DAYS = 3
FLIP_LOCKOUT_HOURS = 24

# ============================================================================
# DRIFT
# ============================================================================
DRIFT_FLIP_THRESHOLD = 0.75

# ============================================================================
# CIRCUIT BREAKERS
# ============================================================================
CB_DAILY_PNL_LIMIT = -0.02
CB_INTRADAY_DRAWDOWN_LIMIT = -0.03
CB_CONSECUTIVE_STOPS = 3
CB_STOP_WINDOW_HOURS = 6
CB_COOLDOWN_HOURS_MIN = 6
CB_COOLDOWN_HOURS_MAX = 24

# ============================================================================
# SHOCK MODE
# ============================================================================
SHOCK_DRAWDOWN_THRESHOLD = -0.25
SHOCK_VOL_MULTIPLIER = 2.5
SHOCK_LOCK_HOURS = 12

# ============================================================================
# DATA INTEGRITY
# ============================================================================
DATA_CONFIDENCE_DECAY = 0.05
DATA_CONFIDENCE_FLOOR = 0.35
DATA_EXPOSURE_SAFETY_FACTOR = 0.80

# ============================================================================
# AUTO-REVERT
# ============================================================================
REVERT_EVAL_HOURS_MIN = 6
REVERT_EVAL_HOURS_MAX = 12
REVERT_LOCK_HOURS = 24

# ============================================================================
# TIMEOUT
# ============================================================================
MAX_CYCLE_SECONDS = 90
