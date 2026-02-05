"""
Crypto scheduler configuration (separate from swing scheduler).

Environment-driven so containers can tune cadence without code edits.
"""

import os

# Downtime window (UTC) for ML training/validation
CRYPTO_DOWNTIME_START_UTC = os.getenv("CRYPTO_DOWNTIME_START_UTC", "03:00")
CRYPTO_DOWNTIME_END_UTC = os.getenv("CRYPTO_DOWNTIME_END_UTC", "05:00")

# Trading loop tick cadence (seconds)
# How often to check if trading_tick should run
CRYPTO_SCHEDULER_TICK_SECONDS = int(os.getenv("CRYPTO_SCHEDULER_TICK_SECONDS", "60"))

# Trading task cadence (seconds)
# How often to run the main trading pipeline (scan/score/execute)
CRYPTO_TRADING_TICK_INTERVAL_MINUTES = int(os.getenv("CRYPTO_TRADING_TICK_INTERVAL_MINUTES", "1"))

# Monitoring task cadence (seconds)
# How often to check positions/exits during downtime
CRYPTO_MONITOR_INTERVAL_MINUTES = int(os.getenv("CRYPTO_MONITOR_INTERVAL_MINUTES", "15"))

# Reconciliation interval
CRYPTO_RECONCILIATION_INTERVAL_MINUTES = int(os.getenv("CRYPTO_RECONCILIATION_INTERVAL_MINUTES", "60"))

# Startup behaviors
CRYPTO_RUN_STARTUP_RECONCILIATION = os.getenv("CRYPTO_RUN_STARTUP_RECONCILIATION", "true").lower() == "true"
CRYPTO_RUN_HEALTH_CHECK_ON_BOOT = os.getenv("CRYPTO_RUN_HEALTH_CHECK_ON_BOOT", "true").lower() == "true"
