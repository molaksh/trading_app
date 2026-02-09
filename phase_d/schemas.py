"""
Pydantic schemas for Phase D governance layer.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class BlockType(str, Enum):
    """Classification of regime blocks."""
    NOISE = "NOISE"              # Short, insignificant block
    COMPRESSION = "COMPRESSION"  # Long, low vol, low upside
    SHOCK = "SHOCK"              # Extreme vol or drawdown
    STRUCTURAL = "STRUCTURAL"    # Long, high upside


class BlockEvent(BaseModel):
    """Regime block detection event."""

    block_id: str  # UUID
    scope: str  # live_crypto, paper_crypto, etc.
    event_type: str  # BLOCK_START, BLOCK_END
    timestamp: datetime
    regime: str  # BTC regime causing block
    reason: str  # BTC_UNSUITABLE, etc.
    block_start_ts: datetime
    block_end_ts: Optional[datetime] = None
    duration_seconds: Optional[int] = None  # Set when block ends
    block_type: Optional[BlockType] = None  # Classified after block ends
    regime_changes_during_block: List[str] = Field(default_factory=list)


class BlockEvidence(BaseModel):
    """Post-facto evidence metrics for a completed block."""

    block_id: str
    scope: str
    duration_seconds: int

    # Historical context
    historical_median_duration: Optional[int] = None
    historical_p90_duration: Optional[int] = None

    # Missed upside (%)
    btc_max_upside_pct: float
    eth_max_upside_pct: float
    alt_max_upside_pct: float = 0.0  # SOL or aggregate

    # Drawdown avoided (%)
    btc_max_drawdown_pct: float
    eth_max_drawdown_pct: float = 0.0

    # Optional portfolio simulation
    portfolio_simulated_pnl: float = 0.0

    # Volatility metrics
    volatility_before_block_end: float = 0.0
    volatility_after_block_end: float = 0.0
    volatility_expansion_ratio: float = 1.0

    # Regime tracking
    regime_at_start: str
    regime_at_end: str
    regime_changes_during_block: List[str] = Field(default_factory=list)

    # Time context
    time_of_day_utc: int = 0  # 0-23
    day_of_week: int = 0  # 0-6 (Monday-Sunday)


class PhaseEligibilityResult(BaseModel):
    """Result of Phase D v1 eligibility evaluation."""

    timestamp: datetime
    scope: str
    current_block_id: Optional[str] = None

    # Overall eligibility
    eligible: bool  # ALL 5 rules must pass

    # Rule pass/fail states
    evidence_sufficiency_passed: bool      # Rule 1: >= 3 completed blocks
    duration_anomaly_passed: bool          # Rule 2: current > p90
    block_type_passed: bool                # Rule 3: COMPRESSION or STRUCTURAL
    cost_benefit_passed: bool              # Rule 4: positive CB in >= 2 blocks
    regime_safety_passed: bool             # Rule 5: regime safe, vol normal

    # Details for debugging
    rule_details: Dict[str, Any] = Field(default_factory=dict)

    # Auto-expiry
    expiry_timestamp: Optional[datetime] = None


class PhaseDEvent(BaseModel):
    """Append-only Phase D event."""

    timestamp: datetime
    event_type: str  # BLOCK_START, BLOCK_END, EVIDENCE_COLLECTED, ELIGIBILITY_EVALUATED
    scope: str
    block_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
