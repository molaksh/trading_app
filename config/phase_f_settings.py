"""
Phase F: Epistemic Market Intelligence - Configuration Settings

Phase F is a READ-ONLY epistemic layer that observes external market data
and forms beliefs about regime validity. It has ZERO authority over execution.
"""

import os
from typing import List

# ============================================================================
# Master Kill-Switch
# ============================================================================

PHASE_F_ENABLED = os.getenv("PHASE_F_ENABLED", "true").lower() == "true"

# ============================================================================
# Scheduling (CRITICAL: OFF-HOURS ONLY)
# ============================================================================

# Daily run at fixed UTC time (03:00 UTC = overnight)
PHASE_F_RUN_SCHEDULE_UTC = os.getenv("PHASE_F_RUN_SCHEDULE_UTC", "03:00")

# Kill switch to disable Phase F entirely
PHASE_F_KILL_SWITCH = os.getenv("PHASE_F_KILL_SWITCH", "false").lower() == "true"

# Weekly semantic summary (optional, default True)
PHASE_F_MONTHLY_SYNTHESIS_ENABLED = os.getenv("PHASE_F_MONTHLY_SYNTHESIS_ENABLED", "true").lower() == "true"
PHASE_F_SYNTHESIS_DAY_OF_WEEK = os.getenv("PHASE_F_SYNTHESIS_DAY_OF_WEEK", "0")  # 0=Sunday

# ============================================================================
# Runtime Limits (MANDATORY - SAFETY)
# ============================================================================

# Per-agent timeout (hard stop)
PHASE_F_PER_AGENT_TIMEOUT_SECONDS = int(os.getenv("PHASE_F_PER_AGENT_TIMEOUT_SECONDS", "600"))

# Total cycle timeout (all 3 agents)
PHASE_F_TOTAL_CYCLE_TIMEOUT_SECONDS = int(os.getenv("PHASE_F_TOTAL_CYCLE_TIMEOUT_SECONDS", "1500"))

# ============================================================================
# Resource Limits (SAFETY)
# ============================================================================

# Articles per agent (max 25)
PHASE_F_MAX_ARTICLES_PER_AGENT = int(os.getenv("PHASE_F_MAX_ARTICLES_PER_AGENT", "25"))

# Unique sources per agent (max 15)
PHASE_F_MAX_SOURCES_PER_AGENT = int(os.getenv("PHASE_F_MAX_SOURCES_PER_AGENT", "15"))

# Token limit per agent run
PHASE_F_MAX_TOKENS_PER_RUN = int(os.getenv("PHASE_F_MAX_TOKENS_PER_RUN", "100000"))

# Daily cost cap (USD)
PHASE_F_DAILY_COST_CAP_USD = float(os.getenv("PHASE_F_DAILY_COST_CAP_USD", "5.00"))

# ============================================================================
# Integration Constraints (HARD - NEVER VIOLATE)
# ============================================================================

# These flags document that Phase F is pure observation
PHASE_F_BLOCKS_GOVERNANCE_RULE_CHANGES = True  # Never trigger Type C proposals
PHASE_F_BLOCKS_EXECUTION_CHANGES = True
PHASE_F_BLOCKS_POSITION_SIZING = True
PHASE_F_BLOCKS_REGIME_OVERRIDE = True
PHASE_F_BLOCKS_UNIVERSE_ACTIONS = True

# ============================================================================
# Allowed Verdicts (Whitelist)
# ============================================================================

ALLOWED_VERDICTS: List[str] = [
    "REGIME_VALIDATED",
    "REGIME_QUESTIONABLE",
    "HIGH_NOISE_NO_ACTION",
    "POSSIBLE_STRUCTURAL_SHIFT_OBSERVE"
]

# ============================================================================
# Logging & Transparency
# ============================================================================

# Logs root directory
PHASE_F_LOGS_ROOT = os.getenv("PHASE_F_LOGS_ROOT", "phase_f/logs/runs")

# Persistence root directory
PHASE_F_PERSIST_ROOT = os.getenv("PHASE_F_PERSIST_ROOT", "persist/phase_f/crypto")

# Data retention (days)
PHASE_F_ACTIVE_LOGS_RETENTION_DAYS = int(os.getenv("PHASE_F_ACTIVE_LOGS_RETENTION_DAYS", "30"))
PHASE_F_ARCHIVE_RETENTION_DAYS = int(os.getenv("PHASE_F_ARCHIVE_RETENTION_DAYS", "365"))

# ============================================================================
# API Configuration
# ============================================================================

# OpenAI for reasoning (used by agents internally if needed)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_API_BASE_URL = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# NewsAPI configuration
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "").strip()
NEWSAPI_BASE_URL = os.getenv("NEWSAPI_BASE_URL", "https://newsapi.org/v2")

# Glassnode API (on-chain data)
GLASSNODE_API_KEY = os.getenv("GLASSNODE_API_KEY", "").strip()
GLASSNODE_BASE_URL = os.getenv("GLASSNODE_BASE_URL", "https://api.glassnode.com")

# ============================================================================
# Forbidden Keywords (Safety Check)
# ============================================================================

FORBIDDEN_ACTION_WORDS = [
    "execute",
    "trade",
    "buy",
    "sell",
    "position",
    "remove",
    "add",
    "change",
    "reduce",
    "increase",
    "should",
    "must",
    "recommend",
    "action",
    "do",
    "trigger",
    "signal",
    "order",
]

FORBIDDEN_CAUSATION_WORDS = [
    "causes",
    "leads to",
    "->",
    "results in",
    "makes",
    "forces",
]
