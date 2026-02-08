"""
Governance configuration for Phase C.

Controls scheduling, AI settings, and constitutional limits.
"""

import os
from typing import Optional

# Feature flags
GOVERNANCE_ENABLED = os.getenv("GOVERNANCE_ENABLED", "false").lower() == "true"
GOVERNANCE_RUN_WEEKLY = True  # Sunday only
GOVERNANCE_RUN_TIME_UTC = "08:15"  # 3:15 AM ET (during crypto downtime)
GOVERNANCE_LOOKBACK_DAYS = int(os.getenv("GOVERNANCE_LOOKBACK_DAYS", "7"))

# AI settings for governance agents
GOVERNANCE_AI_MODEL = os.getenv("GOVERNANCE_AI_MODEL", "gpt-4o")
GOVERNANCE_AI_TEMPERATURE = float(os.getenv("GOVERNANCE_AI_TEMPERATURE", "0.2"))
GOVERNANCE_MAX_TOKENS = int(os.getenv("GOVERNANCE_MAX_TOKENS", "2000"))

# Constitutional limits
MAX_SYMBOLS_ADDED_PER_PROPOSAL = 5
MAX_SYMBOLS_REMOVED_PER_PROPOSAL = 3
PROPOSAL_EXPIRY_HOURS = 72

# Scopes to analyze
PAPER_SCOPE = "paper.kraken.crypto.global"
LIVE_SCOPE = "live.kraken.crypto.global"

# Persistence configuration
GOVERNANCE_ARTIFACT_BASE_PATH = "governance"
GOVERNANCE_PROPOSALS_SUBDIR = "proposals"
GOVERNANCE_LOGS_SUBDIR = "logs"

def get_governance_settings() -> dict:
    """Return governance settings as a dict."""
    return {
        "enabled": GOVERNANCE_ENABLED,
        "run_weekly": GOVERNANCE_RUN_WEEKLY,
        "run_time_utc": GOVERNANCE_RUN_TIME_UTC,
        "lookback_days": GOVERNANCE_LOOKBACK_DAYS,
        "ai_model": GOVERNANCE_AI_MODEL,
        "ai_temperature": GOVERNANCE_AI_TEMPERATURE,
        "max_tokens": GOVERNANCE_MAX_TOKENS,
        "max_symbols_added": MAX_SYMBOLS_ADDED_PER_PROPOSAL,
        "max_symbols_removed": MAX_SYMBOLS_REMOVED_PER_PROPOSAL,
        "proposal_expiry_hours": PROPOSAL_EXPIRY_HOURS,
        "paper_scope": PAPER_SCOPE,
        "live_scope": LIVE_SCOPE,
    }
