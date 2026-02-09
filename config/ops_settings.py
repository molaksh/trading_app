"""
Phase E v2 configuration settings.

Feature flags and configuration for temporal awareness and passive notifications.
All v2 features default to False for backward compatibility.
"""

import os

# ============================================================================
# Phase E v2 Feature Flags
# ============================================================================

# Enable watch creation and evaluation
ENABLE_WATCHES = os.getenv("OPS_ENABLE_WATCHES", "false").lower() == "true"

# Enable regime duration tracking
ENABLE_DURATION_TRACKING = (
    os.getenv("OPS_ENABLE_DURATION_TRACKING", "false").lower() == "true"
)

# Enable historical context framing in responses
ENABLE_HISTORICAL_FRAMING = (
    os.getenv("OPS_ENABLE_HISTORICAL_FRAMING", "false").lower() == "true"
)

# Enable scheduled digest generation
ENABLE_DIGESTS = os.getenv("OPS_ENABLE_DIGESTS", "false").lower() == "true"

# ============================================================================
# Watch Configuration
# ============================================================================

# Maximum TTL for any watch (hours)
WATCH_MAX_TTL_HOURS = int(os.getenv("OPS_WATCH_MAX_TTL_HOURS", "72"))

# Default TTL for watches if not specified (hours)
WATCH_DEFAULT_TTL_HOURS = int(os.getenv("OPS_WATCH_DEFAULT_TTL_HOURS", "24"))

# Maximum number of active watches per user
WATCH_MAX_PER_USER = int(os.getenv("OPS_WATCH_MAX_PER_USER", "10"))

# Cleanup old watch records (days)
WATCH_CLEANUP_DAYS = int(os.getenv("OPS_WATCH_CLEANUP_DAYS", "30"))

# ============================================================================
# Digest Configuration
# ============================================================================

# Schedule time for digest (UTC, 24-hour format: HH:MM)
# Default: 01:00 UTC (9 PM ET)
DIGEST_SCHEDULE_TIME_UTC = os.getenv("OPS_DIGEST_TIME_UTC", "01:00")

# Only send digest if activity detected
DIGEST_ONLY_IF_ACTIVITY = (
    os.getenv("OPS_DIGEST_ONLY_IF_ACTIVITY", "true").lower() == "true"
)

# ============================================================================
# Historical Analysis Configuration
# ============================================================================

# Number of days to look back for historical statistics
HISTORICAL_LOOKBACK_DAYS = int(os.getenv("OPS_HISTORICAL_LOOKBACK_DAYS", "30"))

# Minimum number of regime occurrences to report statistics
HISTORICAL_MIN_OCCURRENCES = int(os.getenv("OPS_HISTORICAL_MIN_OCCURRENCES", "2"))

# ============================================================================
# Duration Tracking Configuration
# ============================================================================

# Maximum age of regime history to consider (days)
DURATION_HISTORY_DAYS = int(os.getenv("OPS_DURATION_HISTORY_DAYS", "90"))

# Cleanup old regime events (days)
DURATION_CLEANUP_DAYS = int(os.getenv("OPS_DURATION_CLEANUP_DAYS", "30"))
