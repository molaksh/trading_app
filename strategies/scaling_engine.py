"""
Position Scaling Decision Engine

Core logic for determining when to add to existing positions.

Implements structured, testable scaling decisions with:
- Hard safety enforcement (execution layer responsibilities)
- Strategy-level qualification checks (directional integrity, price structure)
- Portfolio-level monitoring (non-blocking)
- Clear audit trail via structured logging

All decisions default to BLOCK unless explicitly qualified to SCALE.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from risk.scaling_policy import (
    ScalingContext,
    ScalingDecision,
    ScalingDecisionResult,
    ScalingReasonCode,
    ScalingType,
    StrategyScalingPolicy,
    count_entries,
    last_entry_price,
    last_entry_timestamp,
    total_entry_quantity,
    has_pending_conflicting_order,
)

logger = logging.getLogger(__name__)


# ============================================================================
# EXECUTION LAYER: Hard Safety Enforcement
# ============================================================================


def check_strategy_permits_scaling(
    context: ScalingContext,
) -> Optional[ScalingDecisionResult]:
    """
    Hard enforcement: Strategy must explicitly allow multi-entry.
    
    Returns:
        ScalingDecisionResult if scaling not allowed, else None
    """
    if context.scaling_policy is None or not context.scaling_policy.allows_multiple_entries:
        return ScalingDecisionResult(
            decision=ScalingDecision.BLOCK,
            reason_code=ScalingReasonCode.STRATEGY_DISALLOWS_SCALING,
            reason_text="Strategy does not permit multi-entry scaling",
            current_entry_count=count_entries(context.ledger_entries),
        )
    return None


def check_max_entries_not_exceeded(
    context: ScalingContext,
) -> Optional[ScalingDecisionResult]:
    """
    Hard enforcement: Do not exceed max entries per symbol.
    
    Returns:
        ScalingDecisionResult if max exceeded, else None
    """
    current_entries = count_entries(context.ledger_entries)
    max_entries = context.scaling_policy.max_entries_per_symbol

    if current_entries >= max_entries:
        return ScalingDecisionResult(
            decision=ScalingDecision.BLOCK,
            reason_code=ScalingReasonCode.MAX_ENTRIES_EXCEEDED,
            reason_text=(
                f"Current entries ({current_entries}) >= max allowed ({max_entries})"
            ),
            current_entry_count=current_entries,
            would_exceed_max=True,
        )
    return None


def check_max_position_size(
    context: ScalingContext,
) -> Optional[ScalingDecisionResult]:
    """
    Hard enforcement: Do not exceed max position as % of account equity.
    
    Proposed position value = current + proposed at current price.
    """
    proposed_total_value = (
        context.current_position_value + (context.proposed_entry_size * context.current_price)
    )
    proposed_position_pct = (proposed_total_value / context.account_equity) * 100

    if proposed_position_pct > context.scaling_policy.max_total_position_pct:
        return ScalingDecisionResult(
            decision=ScalingDecision.BLOCK,
            reason_code=ScalingReasonCode.MAX_POSITION_SIZE_EXCEEDED,
            reason_text=(
                f"Proposed position would be {proposed_position_pct:.2f}% of account "
                f"(max {context.scaling_policy.max_total_position_pct:.2f}%)"
            ),
            current_entry_count=count_entries(context.ledger_entries),
            proposed_position_pct=proposed_position_pct,
        )
    return None


def check_pending_order_conflicts(
    context: ScalingContext,
) -> Optional[ScalingDecisionResult]:
    """
    Hard enforcement: Do not scale if pending BUY or conflicting SELL exists.
    
    Returns:
        ScalingDecisionResult if conflict exists, else None
    """
    if has_pending_conflicting_order(context.symbol, "BUY", context.pending_buy_orders):
        return ScalingDecisionResult(
            decision=ScalingDecision.BLOCK,
            reason_code=ScalingReasonCode.PENDING_BUY_EXISTS,
            reason_text="Pending BUY order exists for this symbol",
            current_entry_count=count_entries(context.ledger_entries),
        )

    # Check for pending SELL on same position (conflicting intent)
    if has_pending_conflicting_order(context.symbol, "SELL", context.pending_sell_orders):
        return ScalingDecisionResult(
            decision=ScalingDecision.BLOCK,
            reason_code=ScalingReasonCode.CONFLICTING_SELL_EXISTS,
            reason_text="Pending SELL order exists for this symbol (conflicting intent)",
            current_entry_count=count_entries(context.ledger_entries),
        )

    return None


def check_broker_ledger_consistency(
    context: ScalingContext,
) -> Optional[ScalingDecisionResult]:
    """
    Hard enforcement: Broker qty must match ledger total.
    
    If mismatch, do not scale (risk of position doubling).
    """
    ledger_qty = total_entry_quantity(context.ledger_entries)

    # Allow small floating point tolerance
    qty_mismatch = abs(context.current_position_qty - ledger_qty) > 0.01

    if qty_mismatch:
        return ScalingDecisionResult(
            decision=ScalingDecision.BLOCK,
            reason_code=ScalingReasonCode.BROKER_LEDGER_MISMATCH,
            reason_text=(
                f"Broker qty ({context.current_position_qty:.2f}) != "
                f"Ledger qty ({ledger_qty:.2f}). "
                f"Do not scale until reconciled."
            ),
            current_entry_count=count_entries(context.ledger_entries),
            debug_info={
                "broker_qty": context.current_position_qty,
                "ledger_qty": ledger_qty,
                "mismatch": context.current_position_qty - ledger_qty,
            },
        )
    return None


def check_risk_budget(
    context: ScalingContext,
) -> Optional[ScalingDecisionResult]:
    """
    Hard enforcement: Risk for this add must fit within budget.
    
    Risk = proposed_size * (entry_price - stop_loss)
    For now, assume stop is at lowest bar since last entry.
    """
    if context.proposed_risk_amount > context.available_risk_budget:
        return ScalingDecisionResult(
            decision=ScalingDecision.BLOCK,
            reason_code=ScalingReasonCode.RISK_BUDGET_EXCEEDED,
            reason_text=(
                f"Proposed risk (${context.proposed_risk_amount:.2f}) "
                f"> available budget (${context.available_risk_budget:.2f})"
            ),
            current_entry_count=count_entries(context.ledger_entries),
            estimated_risk=context.proposed_risk_amount,
        )
    return None


# ============================================================================
# STRATEGY LAYER: Scaling Qualification Checks
# ============================================================================


def check_minimum_time_since_entry(
    context: ScalingContext,
) -> Optional[ScalingDecisionResult]:
    """
    Strategy enforcement: Minimum time must have elapsed since last entry.
    """
    min_time = context.scaling_policy.min_time_between_entries_seconds

    if min_time > 0 and context.minutes_since_last_entry < (min_time / 60):
        return ScalingDecisionResult(
            decision=ScalingDecision.SKIP,
            reason_code=ScalingReasonCode.MINIMUM_TIME_NOT_MET,
            reason_text=(
                f"Only {context.minutes_since_last_entry:.1f} minutes since last entry. "
                f"Need {min_time} seconds ({min_time/60:.1f} minutes)."
            ),
            current_entry_count=count_entries(context.ledger_entries),
            debug_info={"minutes_elapsed": context.minutes_since_last_entry, "min_seconds": min_time},
        )
    return None


def check_minimum_bars_since_entry(
    context: ScalingContext,
) -> Optional[ScalingDecisionResult]:
    """
    Strategy enforcement: Minimum bars must have passed since last entry.
    """
    min_bars = context.scaling_policy.min_bars_between_entries

    if min_bars > 0 and context.bars_since_last_entry < min_bars:
        return ScalingDecisionResult(
            decision=ScalingDecision.SKIP,
            reason_code=ScalingReasonCode.MINIMUM_BARS_NOT_MET,
            reason_text=(
                f"Only {context.bars_since_last_entry} bars since last entry. "
                f"Need {min_bars} bars."
            ),
            current_entry_count=count_entries(context.ledger_entries),
            debug_info={"bars_elapsed": context.bars_since_last_entry, "min_bars": min_bars},
        )
    return None


def check_signal_quality(
    context: ScalingContext,
) -> Optional[ScalingDecisionResult]:
    """
    Strategy enforcement: Signal quality must meet threshold for add.
    """
    min_strength = context.scaling_policy.min_signal_strength_for_add

    if context.current_signal_confidence < min_strength:
        return ScalingDecisionResult(
            decision=ScalingDecision.SKIP,
            reason_code=ScalingReasonCode.SIGNAL_CONFIDENCE_TOO_LOW,
            reason_text=(
                f"Signal confidence {context.current_signal_confidence:.2f} < "
                f"minimum {min_strength:.2f}"
            ),
            current_entry_count=count_entries(context.ledger_entries),
        )

    if context.has_bearish_divergence:
        return ScalingDecisionResult(
            decision=ScalingDecision.SKIP,
            reason_code=ScalingReasonCode.SIGNAL_QUALITY_INSUFFICIENT,
            reason_text="Bearish divergence detected since last entry",
            current_entry_count=count_entries(context.ledger_entries),
        )

    return None


def check_price_structure(
    context: ScalingContext,
) -> Optional[ScalingDecisionResult]:
    """
    Strategy enforcement: Price structure must match scaling type.
    
    Pyramid: Entry price > last entry price, no lower low (momentum)
    Average: Entry price < last entry price, drawdown <= max ATR (averaging down)
    """
    last_price = last_entry_price(context.ledger_entries)
    if last_price is None:
        return None  # First entry, no structure check needed

    scaling_type = context.scaling_policy.scaling_type

    if scaling_type == ScalingType.PYRAMID:
        # Pyramid requires better price (higher for long)
        if context.proposed_entry_price <= last_price:
            return ScalingDecisionResult(
                decision=ScalingDecision.SKIP,
                reason_code=ScalingReasonCode.PRICE_STRUCTURE_VIOLATION,
                reason_text=(
                    f"Pyramid entry price ${context.proposed_entry_price:.2f} "
                    f"not > last entry ${last_price:.2f}"
                ),
                current_entry_count=count_entries(context.ledger_entries),
                debug_info={"last_price": last_price, "proposed_price": context.proposed_entry_price},
            )

        # Pyramid: no lower low requirement
        if context.scaling_policy.require_no_lower_low and context.has_lower_low:
            return ScalingDecisionResult(
                decision=ScalingDecision.SKIP,
                reason_code=ScalingReasonCode.PRICE_STRUCTURE_VIOLATION,
                reason_text="Lower low detected since last entry (pyramid requires no lower low)",
                current_entry_count=count_entries(context.ledger_entries),
                debug_info={"lowest_since_entry": context.price_lowest_since_last_entry},
            )

    elif scaling_type == ScalingType.AVERAGE:
        # Average requires worse price (lower for long)
        if context.proposed_entry_price >= last_price:
            return ScalingDecisionResult(
                decision=ScalingDecision.SKIP,
                reason_code=ScalingReasonCode.PRICE_STRUCTURE_VIOLATION,
                reason_text=(
                    f"Average entry price ${context.proposed_entry_price:.2f} "
                    f"not < last entry ${last_price:.2f}"
                ),
                current_entry_count=count_entries(context.ledger_entries),
                debug_info={"last_price": last_price, "proposed_price": context.proposed_entry_price},
            )

        # Average: drawdown must not exceed max ATR multiple
        max_drawdown_multiple = context.scaling_policy.max_atr_drawdown_multiple
        drawdown = last_price - context.price_lowest_since_last_entry
        max_allowed_drawdown = max_drawdown_multiple * context.atr

        if drawdown > max_allowed_drawdown:
            return ScalingDecisionResult(
                decision=ScalingDecision.SKIP,
                reason_code=ScalingReasonCode.PRICE_STRUCTURE_VIOLATION,
                reason_text=(
                    f"Drawdown ${drawdown:.2f} ({drawdown/context.atr:.2f} ATR) "
                    f"> max ${max_allowed_drawdown:.2f} ({max_drawdown_multiple} ATR)"
                ),
                current_entry_count=count_entries(context.ledger_entries),
                debug_info={
                    "drawdown_dollars": drawdown,
                    "drawdown_atr_multiple": drawdown / context.atr if context.atr > 0 else 0,
                    "max_allowed_atr_multiple": max_drawdown_multiple,
                },
            )

    return None


def check_volatility_regime(
    context: ScalingContext,
) -> Optional[ScalingDecisionResult]:
    """
    Strategy enforcement: Volatility must be in acceptable regime.
    
    Default: ATR must be above rolling median (no vol collapse).
    """
    if not context.scaling_policy.require_volatility_above_median:
        return None

    if context.atr < context.atr_rolling_median:
        return ScalingDecisionResult(
            decision=ScalingDecision.SKIP,
            reason_code=ScalingReasonCode.VOLATILITY_REGIME_INVALID,
            reason_text=(
                f"ATR {context.atr:.2f} below rolling median {context.atr_rolling_median:.2f} "
                f"(volatility collapsing)"
            ),
            current_entry_count=count_entries(context.ledger_entries),
            debug_info={"atr": context.atr, "atr_median": context.atr_rolling_median},
        )

    return None


def check_directionality(
    context: ScalingContext,
) -> Optional[ScalingDecisionResult]:
    """
    Strategy enforcement: Signal must match position direction.
    
    Do not mix long and short signals for same symbol.
    """
    if not context.signal_matches_position_direction:
        return ScalingDecisionResult(
            decision=ScalingDecision.BLOCK,
            reason_code=ScalingReasonCode.DIRECTIONAL_CONFLICT,
            reason_text="Signal direction conflicts with existing position direction",
            current_entry_count=count_entries(context.ledger_entries),
        )

    return None


# ============================================================================
# EXECUTION SANITY CHECKS
# ============================================================================


def check_execution_feasibility(
    context: ScalingContext, min_order_size: float = 10.0, max_slippage_pct: float = 0.5
) -> Optional[ScalingDecisionResult]:
    """
    Execution sanity checks: Order size, slippage, liquidity.
    
    Args:
        context: Scaling context
        min_order_size: Minimum order value ($ or shares, depending on security)
        max_slippage_pct: Maximum acceptable slippage as % of entry price
    
    Returns:
        ScalingDecisionResult if check fails, else None
    """
    # Check minimum order size
    if context.proposed_entry_size < 0.01:  # Minimum 0.01 shares
        return ScalingDecisionResult(
            decision=ScalingDecision.BLOCK,
            reason_code=ScalingReasonCode.ORDER_SIZE_BELOW_MINIMUM,
            reason_text=f"Order size {context.proposed_entry_size:.4f} shares < minimum 0.01",
            current_entry_count=count_entries(context.ledger_entries),
        )

    order_value = context.proposed_entry_size * context.proposed_entry_price
    if order_value < min_order_size:
        return ScalingDecisionResult(
            decision=ScalingDecision.BLOCK,
            reason_code=ScalingReasonCode.ORDER_SIZE_BELOW_MINIMUM,
            reason_text=(
                f"Order value ${order_value:.2f} < minimum ${min_order_size:.2f}"
            ),
            current_entry_count=count_entries(context.ledger_entries),
        )

    # Note: Liquidity and slippage checks would require real-time market data
    # Implementation would depend on broker API and available data

    return None


# ============================================================================
# MAIN DECISION ENGINE
# ============================================================================


def should_scale_position(context: ScalingContext) -> ScalingDecisionResult:
    """
    Comprehensive scaling decision engine.
    
    Runs through all checks in priority order:
    1. Hard safety enforcement (execution layer)
    2. Strategy qualification (directional, price structure, signals)
    3. Execution feasibility
    
    Returns the FIRST failing check's result, or SCALE if all pass.
    
    Default: BLOCK unless explicitly qualified.
    
    Args:
        context: Complete scaling context
    
    Returns:
        ScalingDecisionResult with decision and reasoning
    """

    # Validate inputs
    if context.scaling_policy is None:
        return ScalingDecisionResult(
            decision=ScalingDecision.BLOCK,
            reason_code=ScalingReasonCode.STRATEGY_DISALLOWS_SCALING,
            reason_text="No scaling policy defined",
            current_entry_count=count_entries(context.ledger_entries),
        )

    is_valid, error_msg = context.scaling_policy.validate()
    if not is_valid:
        return ScalingDecisionResult(
            decision=ScalingDecision.BLOCK,
            reason_code=ScalingReasonCode.STRATEGY_DISALLOWS_SCALING,
            reason_text=f"Invalid scaling policy: {error_msg}",
            current_entry_count=count_entries(context.ledger_entries),
        )

    # ========================================================================
    # PHASE 1: Hard Safety Enforcement (Execution Layer)
    # ========================================================================

    result = check_strategy_permits_scaling(context)
    if result:
        return result

    result = check_max_entries_not_exceeded(context)
    if result:
        return result

    result = check_max_position_size(context)
    if result:
        return result

    result = check_pending_order_conflicts(context)
    if result:
        return result

    result = check_broker_ledger_consistency(context)
    if result:
        return result

    result = check_risk_budget(context)
    if result:
        return result

    # ========================================================================
    # PHASE 2: Directionality (BLOCK if mismatch, skip if not applicable)
    # ========================================================================

    result = check_directionality(context)
    if result:
        return result

    # ========================================================================
    # PHASE 3: Strategy Qualification (Timing, Signals, Structure)
    # ========================================================================

    result = check_minimum_time_since_entry(context)
    if result:
        return result

    result = check_minimum_bars_since_entry(context)
    if result:
        return result

    result = check_signal_quality(context)
    if result:
        return result

    result = check_volatility_regime(context)
    if result:
        return result

    result = check_price_structure(context)
    if result:
        return result

    # ========================================================================
    # PHASE 4: Execution Feasibility
    # ========================================================================

    result = check_execution_feasibility(context)
    if result:
        return result

    # ========================================================================
    # All checks passed - Safe to scale
    # ========================================================================

    return ScalingDecisionResult(
        decision=ScalingDecision.SCALE,
        reason_code=ScalingReasonCode.STRATEGY_DISALLOWS_SCALING,  # Placeholder, not used
        reason_text="All scaling checks passed. Approved to add position.",
        current_entry_count=count_entries(context.ledger_entries),
        proposed_position_pct=(
            (context.current_position_value
             + context.proposed_entry_size * context.current_price)
            / context.account_equity
            * 100
        ),
        estimated_risk=context.proposed_risk_amount,
    )
