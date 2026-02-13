"""
Phase G Configuration: Universe governance settings and feature flags.

All constants are configurable via environment variables.
Feature flag defaults to OFF (safe).
"""

import os

# ============================================================================
# FEATURE FLAGS
# ============================================================================
PHASE_G_ENABLED = os.getenv("PHASE_G_ENABLED", "false").lower() == "true"
PHASE_G_DRY_RUN = os.getenv("PHASE_G_DRY_RUN", "true").lower() == "true"

# ============================================================================
# SCORING WEIGHTS (must sum to 1.0)
# ============================================================================
SCORE_WEIGHTS = {
    "performance": 0.45,
    "regime": 0.25,
    "liquidity": 0.15,
    "volatility": 0.10,
    "sentiment": 0.05,
}

# ============================================================================
# GUARDRAILS
# ============================================================================
MAX_ADDITIONS_PER_CYCLE = 2
MAX_REMOVALS_PER_CYCLE = 2
MIN_UNIVERSE_SIZE = 5
MAX_UNIVERSE_SIZE = 15
MIN_SCORE_TO_ADD = 60.0
MAX_SCORE_TO_REMOVE = 30.0
COOLDOWN_DAYS_AFTER_REMOVE = 7

# ============================================================================
# REGIME PENALTY SCHEDULE
# ============================================================================
REGIME_PENALTY = {
    "risk_on": 1.0,
    "neutral": 0.85,
    "risk_off": 0.6,
    "panic": 0.3,
}
