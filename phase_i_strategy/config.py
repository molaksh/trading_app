"""
Phase I Configuration: Strategy Intelligence & Autonomy settings and feature flags.

All constants are configurable via environment variables.
Feature flags default to OFF (safe).
"""

import os

# ============================================================================
# FEATURE FLAGS
# ============================================================================
PHASE_I_STRATEGY_ENABLED = os.getenv("PHASE_I_STRATEGY_ENABLED", "false").lower() == "true"
PHASE_I_STRATEGY_KILL_SWITCH = os.getenv("PHASE_I_STRATEGY_KILL_SWITCH", "false").lower() == "true"

# ============================================================================
# OBSERVATORY (Phase I-A)
# ============================================================================
# How often the observatory scheduler task runs (minutes)
OBSERVATORY_INTERVAL_MINUTES = 60

# Zero-signal anomaly: strategy produces 0 non-FLAT signals for this many hours
ZERO_SIGNAL_THRESHOLD_HOURS = 4.0

# Degradation anomaly: rolling win rate drops below this
DEGRADATION_WIN_RATE_THRESHOLD = 0.35

# Parameter staleness: unchanged for this many days with below-median health
PARAMETER_STALE_DAYS = 14

# All-FLAT anomaly: consecutive FLAT cycles before alert
ALL_FLAT_CYCLE_THRESHOLD = 48

# Rolling window for performance metrics (hours)
PERFORMANCE_ROLLING_WINDOW_HOURS = 168  # 7 days

# Signal buffer: flush to disk after this many records
SIGNAL_BUFFER_SIZE = 20

# Maximum cycle timeout (seconds)
MAX_OBSERVATORY_CYCLE_SECONDS = 60
