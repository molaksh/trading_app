"""
Pydantic schemas for Phase E Ops Agent.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class Intent(BaseModel):
    """Parsed user intent."""

    intent_type: str  # EXPLAIN_*, STATUS, START_WATCH, STOP_WATCH
    scope: Optional[str] = None  # live_crypto, paper_crypto, live_us, paper_us, governance
    condition: Optional[str] = None  # For watches: regime_change, governance_pending, etc.
    ttl_hours: Optional[int] = None  # For watches: default 24
    confidence: float = Field(ge=0, le=1)  # 0-1 confidence in parsing


class TelegramMessage(BaseModel):
    """Incoming Telegram message."""

    chat_id: int
    message_id: int
    text: str
    sender_id: int
    timestamp: datetime


class ObservabilitySnapshot(BaseModel):
    """Latest observability state for a scope."""

    scope: str
    timestamp: datetime
    regime: str  # RISK_ON, NEUTRAL, RISK_OFF, PANIC
    trading_active: bool
    blocks: List[str] = []  # Reasons trading is blocked
    recent_trades: int
    daily_pnl: float
    max_drawdown: float
    scan_coverage: int
    signals_skipped: int
    trades_executed: int
    data_issues: int


class DailySummaryEntry(BaseModel):
    """Single entry from daily_summary.jsonl."""

    timestamp: datetime
    scope: str
    regime: str
    trades_executed: int
    realized_pnl: float
    max_drawdown: float
    data_issues: int = 0


class GovernanceProposal(BaseModel):
    """Governance proposal summary."""

    proposal_id: str
    environment: str  # paper, live
    proposal_type: str
    symbols: List[str]
    recommendation: str  # APPROVE, CAUTION, DEFER, REJECT
    confidence: float
    status: str  # PENDING, APPROVED, REJECTED, EXPIRED
    created_at: datetime
    expires_at: Optional[datetime] = None


class Watch(BaseModel):
    """Active temporary watch."""

    watch_id: str
    chat_id: int
    scope: Optional[str]
    condition: str  # regime_change, governance_pending, no_trades, etc.
    created_at: datetime
    expires_at: datetime
    last_state: Optional[Dict[str, Any]] = None
    one_shot: bool = False  # Fire once then stop


class OpsEvent(BaseModel):
    """Append-only ops event."""

    timestamp: datetime
    event_type: str  # INTENT_PARSED, INTENT_EXECUTED, WATCH_CREATED, WATCH_FIRED, etc.
    chat_id: int
    intent: Optional[str]
    scope: Optional[str]
    details: Dict[str, Any] = {}


class OpsDiagnostic(BaseModel):
    """Response diagnostic for explainability."""

    scope: str
    question: str  # "Why no trades?", "What regime?", etc.
    answer: str  # Concise answer
    reason: str  # Single dominant reason
    supporting_data: Dict[str, Any]  # Data backing the answer
    confidence: float
