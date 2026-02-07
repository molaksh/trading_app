"""
Crypto scheduler configuration (separate from swing scheduler).

Environment-driven so containers can tune cadence without code edits.
"""

import os

# Downtime window (UTC) for ML training/validation
# 03:00-05:00 ET (EST) == 08:00-10:00 UTC
CRYPTO_DOWNTIME_START_UTC = os.getenv("CRYPTO_DOWNTIME_START_UTC", "08:00")
CRYPTO_DOWNTIME_END_UTC = os.getenv("CRYPTO_DOWNTIME_END_UTC", "10:00")

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

# Observability
STATUS_SNAPSHOT_INTERVAL_MINUTES = int(os.getenv("STATUS_SNAPSHOT_INTERVAL_MINUTES", "15"))
DAILY_SUMMARY_OUTPUT_PATH = os.getenv("DAILY_SUMMARY_OUTPUT_PATH", "")

# AI Advisor (Phase A)
AI_ADVISOR_ENABLED = os.getenv("AI_ADVISOR_ENABLED", "false").lower() == "true"
AI_MAX_CALLS_PER_DAY = int(os.getenv("AI_MAX_CALLS_PER_DAY", "1"))
AI_RANKING_INTERVAL_HOURS = int(os.getenv("AI_RANKING_INTERVAL_HOURS", "24"))
AI_VALIDATE_SCHEDULER = os.getenv("AI_VALIDATE_SCHEDULER", "false").lower() == "true"

# Startup behaviors
CRYPTO_RUN_STARTUP_RECONCILIATION = os.getenv("CRYPTO_RUN_STARTUP_RECONCILIATION", "true").lower() == "true"
CRYPTO_RUN_HEALTH_CHECK_ON_BOOT = os.getenv("CRYPTO_RUN_HEALTH_CHECK_ON_BOOT", "true").lower() == "true"
