"""
Position Scaling Policy & Decision Engine

Provides strategy-owned scaling policies and execution-layer safety enforcement.
Ensures multi-entry scaling is only applied when explicitly permitted by strategy
and all safety checks pass.

Design Philosophy:
- Strategies declare scaling intent via StrategyScalingPolicy
- Execution layer enforces hard safety rules ONLY
- No implicit or inferred scaling behavior
- Every scaling decision is logged and traceable
- Default behavior is BLOCK on existing position (fail-safe)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)


class ScalingType(Enum):
    """Position scaling strategy types."""
    PYRAMID = "pyramid"        # Add at better prices (higher for longs)
    AVERAGE = "average"        # Add at worse prices (lower for longs)


class ScalingDecision(Enum):
    """Outcome of scaling evaluation."""
    BLOCK = "BLOCK"            # Hard safety violation, do not scale
    SKIP = "SKIP"              # Conditions not met, but not a violation (try next signal)
    SCALE = "SCALE"            # Safe to add position


class ScalingReasonCode(Enum):
    """Structured reason codes for scaling decisions."""
    # BLOCK reasons
    STRATEGY_DISALLOWS_SCALING = "strategy_disallows_scaling"
    MAX_ENTRIES_EXCEEDED = "max_entries_exceeded"
    MAX_POSITION_SIZE_EXCEEDED = "max_position_size_exceeded"
    PENDING_BUY_EXISTS = "pending_buy_exists"
    CONFLICTING_SELL_EXISTS = "conflicting_sell_exists"
    BROKER_LEDGER_MISMATCH = "broker_ledger_mismatch"
    RISK_BUDGET_EXCEEDED = "risk_budget_exceeded"
    PRICE_STRUCTURE_VIOLATION = "price_structure_violation"
    MINIMUM_TIME_NOT_MET = "minimum_time_not_met"
    MINIMUM_BARS_NOT_MET = "minimum_bars_not_met"
    VOLATILITY_REGIME_INVALID = "volatility_regime_invalid"
    SIGNAL_QUALITY_INSUFFICIENT = "signal_quality_insufficient"
    DIRECTIONAL_CONFLICT = "directional_conflict"
    INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"
    ORDER_SIZE_BELOW_MINIMUM = "order_size_below_minimum"
    SLIPPAGE_UNACCEPTABLE = "slippage_unacceptable"

    # SKIP reasons
    WAITING_FOR_FIRST_ENTRY = "waiting_for_first_entry"
    NO_POSITION_EXISTING = "no_position_existing"
    POSITION_TOO_SMALL = "position_too_small"
    SIGNAL_CONFIDENCE_TOO_LOW = "signal_confidence_too_low"


@dataclass
class StrategyScalingPolicy:
    """
    Strategy-declared scaling policy.
    
    Each strategy must explicitly define its scaling behavior.
    If not provided, defaults to single-entry (no scaling).
    
    Attributes:
        allows_multiple_entries: Whether strategy permits multi-entry
        max_entries_per_symbol: Maximum number of adds per symbol
        max_total_position_pct: Maximum position as % of account equity
        scaling_type: "pyramid" (better prices) or "average" (worse prices)
        min_bars_between_entries: Minimum bars between adds
        min_time_between_entries_seconds: Minimum seconds between adds
        min_signal_strength_for_add: Signal must be >= first entry signal
        max_atr_drawdown_multiple: For averaging, max drawdown as ATR multiple
        require_no_lower_low: For pyramiding, require no lower low since entry
        require_volatility_above_median: ATR must exceed rolling median
        max_correlation_allowed: Max correlation with existing positions
    """

    allows_multiple_entries: bool = False
    max_entries_per_symbol: int = 1
    max_total_position_pct: float = 5.0
    scaling_type: ScalingType = ScalingType.PYRAMID
    min_bars_between_entries: int = 0
    min_time_between_entries_seconds: int = 0
    min_signal_strength_for_add: float = 0.0
    max_atr_drawdown_multiple: float = 2.0
    require_no_lower_low: bool = True
    require_volatility_above_median: bool = True
    max_correlation_allowed: float = 0.85

    def validate(self) -> Tuple[bool, Optional[str]]:
        """Validate policy consistency. Returns (is_valid, error_msg)."""
        if self.allows_multiple_entries:
            if self.max_entries_per_symbol < 1:
                return False, "max_entries_per_symbol must be >= 1"
            if self.max_total_position_pct <= 0:
                return False, "max_total_position_pct must be > 0"
            if self.min_bars_between_entries < 0:
                return False, "min_bars_between_entries must be >= 0"
            if self.min_time_between_entries_seconds < 0:
                return False, "min_time_between_entries_seconds must be >= 0"
        return True, None


@dataclass
class ScalingContext:
    """
    Complete context for scaling decision evaluation.
    
    Provides all data needed to determine if adding to a position is safe.
    """

    # Trade context
    symbol: str
    current_signal_confidence: float  # 0-10
    proposed_entry_price: float
    proposed_entry_size: float

    # Position state
    current_position_qty: float  # From broker (authoritative)
    current_position_value: float  # Market value from broker
    ledger_entries: List[Dict] = field(default_factory=list)  # List of {price, qty, timestamp}
    pending_buy_orders: List[Dict] = field(default_factory=list)  # Unfilled buys
    pending_sell_orders: List[Dict] = field(default_factory=list)  # Unfilled sells

    # Market state
    current_price: float = 0.0
    atr: float = 0.0
    atr_rolling_median: float = 0.0
    bars_since_last_entry: int = 0
    minutes_since_last_entry: int = 0
    price_highest_since_last_entry: float = 0.0
    price_lowest_since_last_entry: float = 0.0
    has_lower_low: bool = False
    has_higher_high: bool = False

    # Signal quality
    has_bearish_divergence: bool = False
    signal_matches_position_direction: bool = True

    # Account state
    account_equity: float = 100000.0
    available_risk_budget: float = 10000.0
    proposed_risk_amount: float = 0.0  # $ amount at risk for this add

    # Scaling policy
    strategy_name: str = "Unknown"
    scaling_policy: Optional[StrategyScalingPolicy] = None


@dataclass
class ScalingDecisionResult:
    """
    Outcome of a scaling decision evaluation.
    
    Attributes:
        decision: BLOCK, SKIP, or SCALE
        reason_code: Specific reason from ScalingReasonCode enum
        reason_text: Human-readable explanation
        current_entry_count: How many entries currently held
        would_exceed_max: Would this entry exceed max?
        proposed_position_pct: What % of account would this represent
        estimated_risk: Dollar amount at risk
        timestamp: When decision was made
        debug_info: Additional context for troubleshooting
    """

    decision: ScalingDecision
    reason_code: ScalingReasonCode
    reason_text: str
    current_entry_count: int = 1
    would_exceed_max: bool = False
    proposed_position_pct: float = 0.0
    estimated_risk: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    debug_info: Dict = field(default_factory=dict)

    def __str__(self) -> str:
        return (
            f"ScalingDecision({self.decision.value}): {self.reason_code.value} - {self.reason_text}"
        )

    def log(self, context: ScalingContext) -> None:
        """Log this decision with context."""
        log_level = logging.WARNING if self.decision == ScalingDecision.BLOCK else logging.INFO

        logger.log(
            log_level,
            f"SCALING DECISION: {self.decision.value} | "
            f"Symbol: {context.symbol} | "
            f"Strategy: {context.strategy_name} | "
            f"Reason: {self.reason_code.value} | "
            f"Entries: {self.current_entry_count}/{context.scaling_policy.max_entries_per_symbol if context.scaling_policy else 1} | "
            f"Position %: {self.proposed_position_pct:.2f}% | "
            f"Risk: ${self.estimated_risk:.2f} | "
            f"Text: {self.reason_text}",
        )

        # Log debug info if present
        if self.debug_info:
            logger.debug(f"  Debug Info: {self.debug_info}")


# ============================================================================
# Helper Functions for Policy Enforcement
# ============================================================================


def count_entries(ledger_entries: List[Dict]) -> int:
    """Count open entries in ledger."""
    return len([e for e in ledger_entries if e.get("status") == "open"])


def last_entry_price(ledger_entries: List[Dict]) -> Optional[float]:
    """Get most recent entry price."""
    open_entries = [e for e in ledger_entries if e.get("status") == "open"]
    if not open_entries:
        return None
    # Assume last entry is most recent (list is ordered)
    return open_entries[-1].get("price")


def last_entry_timestamp(ledger_entries: List[Dict]) -> Optional[datetime]:
    """Get most recent entry timestamp."""
    open_entries = [e for e in ledger_entries if e.get("status") == "open"]
    if not open_entries:
        return None
    ts = open_entries[-1].get("timestamp")
    if isinstance(ts, str):
        return datetime.fromisoformat(ts)
    return ts


def total_entry_quantity(ledger_entries: List[Dict]) -> float:
    """Get total quantity across all open entries."""
    return sum(e.get("qty", 0) for e in ledger_entries if e.get("status") == "open")


def has_pending_conflicting_order(
    symbol: str, order_type: str, pending_orders: List[Dict]
) -> bool:
    """
    Check if there's a pending order of given type for symbol.
    
    Args:
        symbol: Stock symbol
        order_type: "BUY" or "SELL"
        pending_orders: List of pending order dicts
    
    Returns:
        True if pending order exists
    """
    return any(
        o.get("symbol") == symbol and o.get("order_type") == order_type
        for o in pending_orders
    )
