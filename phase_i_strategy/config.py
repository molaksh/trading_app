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

# ============================================================================
# RESEARCH ENGINE (Phase I-B)
# ============================================================================
PHASE_I_RESEARCH_ENABLED = os.getenv("PHASE_I_RESEARCH_ENABLED", "false").lower() == "true"

# Backtester: minimum candles required (200 lookback + test window)
BACKTEST_MIN_CANDLES = 300

# Backtester: simulated trading budget
BACKTEST_BUDGET = 10000.0

# Backtester: simple exit after N bars if no opposing signal
BACKTEST_MAX_HOLD_BARS = 60  # 5h at 5m candles

# Grid search: top N results to validate
GRID_SEARCH_TOP_N = 3

# Walk-forward: train/test split
WALK_FORWARD_TRAIN_DAYS = 30
WALK_FORWARD_TEST_DAYS = 7

# Research: minimum OOS Sharpe improvement over current params to count as finding
RESEARCH_MIN_SHARPE_IMPROVEMENT = 0.1

# Research: max runtime (seconds)
MAX_RESEARCH_CYCLE_SECONDS = 5400  # 90 minutes

# Default parameter search spaces
PARAMETER_SEARCH_SPACES = {
    "mean_reversion": {
        "atr_multiplier": [0.8, 1.0, 1.2, 1.5, 2.0],
        "ma_period": [10, 15, 20, 30],
    },
    "long_term_trend_follower": {
        "trend_strength_threshold": [0.3, 0.4, 0.5, 0.6],
        "max_position_size_pct": [2.0, 3.0, 4.0],
    },
    "volatility_scaled_swing": {
        "vol_threshold_high": [0.03, 0.04, 0.05],
        "profit_target_pct": [3.0, 5.0, 7.0],
        "loss_limit_pct": [1.5, 2.0, 3.0],
    },
}
