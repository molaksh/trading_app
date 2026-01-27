"""
Scheduler configuration for continuous trading loop.
Environment-driven so container can tune cadence without code edits.
"""

import os

# Timezone for market-aware scheduling (default: US Eastern)
MARKET_TIMEZONE = os.getenv("MARKET_TIMEZONE", "America/New_York")

# Interval configuration (minutes)
RECONCILIATION_INTERVAL_MINUTES = int(os.getenv("RECONCILIATION_INTERVAL_MINUTES", "60"))
EMERGENCY_EXIT_INTERVAL_MINUTES = int(os.getenv("EMERGENCY_EXIT_INTERVAL_MINUTES", "20"))
ORDER_POLL_INTERVAL_MINUTES = int(os.getenv("ORDER_POLL_INTERVAL_MINUTES", "3"))
HEALTH_CHECK_INTERVAL_MINUTES = int(os.getenv("HEALTH_CHECK_INTERVAL_MINUTES", "60"))

# Daily windows relative to market close/open
ENTRY_WINDOW_MINUTES_BEFORE_CLOSE = int(os.getenv("ENTRY_WINDOW_MINUTES_BEFORE_CLOSE", "25"))
SWING_EXIT_DELAY_MINUTES_AFTER_CLOSE = int(os.getenv("SWING_EXIT_DELAY_MINUTES_AFTER_CLOSE", "10"))

# Tick cadence (seconds) for scheduler loop
SCHEDULER_TICK_SECONDS = int(os.getenv("SCHEDULER_TICK_SECONDS", "60"))

# Startup behaviors
RUN_STARTUP_RECONCILIATION = os.getenv("RUN_STARTUP_RECONCILIATION", "true").lower() == "true"
RUN_HEALTH_CHECK_ON_BOOT = os.getenv("RUN_HEALTH_CHECK_ON_BOOT", "true").lower() == "true"
