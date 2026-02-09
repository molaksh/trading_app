"""
Phase D configuration settings.

Phase D is a constitutional governance layer that studies whether the BTC regime gate
is potentially over-constraining based on evidence from block detection, evidence
collection, and eligibility evaluation.

All features default to False for safety and backward compatibility.
"""

import os

# ============================================================================
# Phase D Feature Flags
# ============================================================================

# Enable Phase D v0 (block detection + evidence collection)
PHASE_D_V0_ENABLED = os.getenv("PHASE_D_V0_ENABLED", "false").lower() == "true"

# Enable Phase D v1 (eligibility computation)
PHASE_D_V1_ENABLED = os.getenv("PHASE_D_V1_ENABLED", "false").lower() == "true"

# Global kill-switch (overrides all features)
PHASE_D_KILL_SWITCH = os.getenv("PHASE_D_KILL_SWITCH", "false").lower() == "true"

# ============================================================================
# Block Classification Thresholds
# ============================================================================

# NOISE classification: short, insignificant blocks
NOISE_DURATION_MULTIPLIER = 1.5  # Must be < 1.5x median duration
NOISE_MAX_UPSIDE_PCT = 3.0       # Max upside during block
NOISE_MAX_DRAWDOWN_PCT = 2.0     # Max drawdown during block

# COMPRESSION classification: long, low volatility, low upside
COMPRESSION_VOL_EXPANSION_MAX = 1.2   # Vol after/before ratio
COMPRESSION_MAX_UPSIDE_PCT = 5.0      # Max upside during block

# SHOCK classification: extreme volatility or drawdown
SHOCK_VOL_EXPANSION_MIN = 2.0         # Vol expansion ratio threshold
SHOCK_MAX_DRAWDOWN_PCT = 10.0         # Max drawdown threshold (absolute)

# ============================================================================
# Eligibility Configuration (v1)
# ============================================================================

# Minimum number of completed blocks with evidence before evaluating eligibility
ELIGIBILITY_MIN_BLOCKS = 3

# Minimum number of blocks with positive cost-benefit to pass rule 4
ELIGIBILITY_MIN_POSITIVE_CB = 2

# Hours until an eligibility evaluation expires (auto-reset)
ELIGIBILITY_EXPIRY_HOURS = 24

# ============================================================================
# Historical Analysis Configuration
# ============================================================================

# Number of days to look back for regime block statistics
HISTORICAL_LOOKBACK_DAYS = 30

# Minimum number of blocks to compute statistics
HISTORICAL_MIN_BLOCKS = 2

# ============================================================================
# Persistence Configuration
# ============================================================================

PHASE_D_PERSIST_ROOT = "persist/phase_d"

# Cleanup old block events (days)
PHASE_D_CLEANUP_DAYS = 90

# ============================================================================
# Evidence Collection Configuration
# ============================================================================

# Symbols to use for evidence collection (upside/drawdown computation)
EVIDENCE_CORE_SYMBOLS = ["BTC", "ETH", "SOL"]

# ============================================================================
# Runtime Observability Configuration
# ============================================================================

# Regime block detection sensitivity (minimum duration to consider a "block")
REGIME_BLOCK_MIN_DURATION_SECONDS = 60  # Don't report blocks shorter than 1 minute
