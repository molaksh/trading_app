"""
Position Scaling Decision Engine - Architecture & Integration Guide

This document describes the production-grade position scaling system for the
trading platform, including design principles, integration points, and examples.

============================================================================
DESIGN PHILOSOPHY
============================================================================

The scaling system enforces clean separation of concerns:

1. STRATEGY LAYER declares intent
   - "I want to scale positions"
   - Provides explicit policy: max entries, entry timing, price structure rules
   - Policy is immutable during a trading session

2. EXECUTION LAYER enforces safety
   - Checks hard constraints: max position size, risk limits, broker consistency
   - Never infers intent or confidence
   - Always defaults to BLOCK unless qualified to SCALE

3. DECISION ENGINE coordinates
   - Runs through checks in priority order
   - Returns first blocking issue (for diagnostics)
   - Logs every decision for audit trail

============================================================================
KEY COMPONENTS
============================================================================

StrategyScalingPolicy (risk/scaling_policy.py)
- Data structure owned by strategy
- Declares:
  * allows_multiple_entries (bool) - primary gate
  * max_entries_per_symbol (int) - hard limit
  * max_total_position_pct (float) - portfolio constraint
  * scaling_type (pyramid | average) - entry strategy
  * Timing constraints (min bars, min seconds between entries)
  * Quality thresholds (signal strength, volatility)
  * Price structure rules

ScalingContext (risk/scaling_policy.py)
- Complete snapshot for decision evaluation
- Includes: trade intent, position state, market data, account state
- Immutable during decision process

ScalingDecision (risk/scaling_policy.py)
- BLOCK: Hard safety violation (must not scale)
- SKIP: Conditions not met, but not a violation (try next signal)
- SCALE: Safe to add position

Decision Engine (strategies/scaling_engine.py)
- Main function: should_scale_position(context) -> ScalingDecisionResult
- Runs in phases:
  1. Hard Safety Enforcement (execution layer)
  2. Directionality Check
  3. Strategy Qualification (timing, signals, structure)
  4. Execution Feasibility
- Returns first failure, or SCALE if all pass

============================================================================
HARD SAFETY ENFORCEMENT (Execution Layer)
============================================================================

These checks ALWAYS block scaling:

1. check_strategy_permits_scaling()
   - Strategy must explicitly allow_multiple_entries=True
   - Default: single-entry only (backward compatible)

2. check_max_entries_not_exceeded()
   - Current entries >= max_entries → BLOCK
   - Critical: prevents position pile-up

3. check_max_position_size()
   - Proposed position % > max_position_pct → BLOCK
   - Protects against overconcentration

4. check_pending_order_conflicts()
   - Pending BUY for same symbol → BLOCK (avoid double submission)
   - Pending SELL for same symbol → BLOCK (conflicting intent)

5. check_broker_ledger_consistency()
   - Broker qty ≠ ledger qty → BLOCK (risk of duplication)
   - Critical before adding positions

6. check_risk_budget()
   - Proposed risk > available budget → BLOCK
   - Respects account risk parameters

============================================================================
STRATEGY QUALIFICATION CHECKS (Strategy Layer)
============================================================================

These checks SKIP (not block) when conditions unmet:

1. check_minimum_time_since_entry()
   - Minutes elapsed < min_seconds → SKIP
   - Allows cool-off period between adds

2. check_minimum_bars_since_entry()
   - Bars since entry < min_bars → SKIP
   - Timeframe-independent timing

3. check_signal_quality()
   - Signal confidence < threshold → SKIP
   - Bearish divergence detected → SKIP
   - Ensures high-quality entries

4. check_price_structure()
   - PYRAMID:
     * Entry price must be > last entry (better price)
     * No lower low since last entry (momentum requirement)
   - AVERAGE:
     * Entry price must be < last entry (averaging down)
     * Drawdown <= max ATR multiple (risk limit)

5. check_volatility_regime()
   - ATR < rolling median → SKIP (vol collapsing)
   - Requires stable volatility environment

6. check_directionality()
   - Signal direction != position direction → BLOCK
   - Critical: prevents mixing long and short

============================================================================
EXECUTION SANITY CHECKS
============================================================================

1. check_execution_feasibility()
   - Order size >= minimum shares → BLOCK if too small
   - Order value >= minimum dollars → BLOCK if too small
   - Slippage acceptable → Optional check
   - Liquidity sufficient → Optional check

============================================================================
INTEGRATION WITH EXECUTION LAYER
============================================================================

In broker/paper_trading_executor.py, before execute_signal():

    def execute_signal_with_scaling(self, symbol, confidence, ...):
        '''Execute entry signal with multi-entry scaling logic.'''
        
        # Check if this is an additional entry
        ledger_entries = self.trade_ledger.get_open_trades_for_symbol(symbol)
        if len(ledger_entries) > 0:
            # Existing position - evaluate scaling
            context = build_scaling_context(
                symbol=symbol,
                current_signal_confidence=confidence,
                ledger_entries=ledger_entries,
                # ... populate all context fields
            )
            
            scaling_result = should_scale_position(context)
            scaling_result.log(context)  # Structured audit trail
            
            if scaling_result.decision == ScalingDecision.BLOCK:
                logger.error(f"Scaling blocked for {symbol}: {scaling_result}")
                return False, None
            elif scaling_result.decision == ScalingDecision.SKIP:
                logger.warning(f"Scaling skipped for {symbol}: {scaling_result}")
                return False, None
            # else: SCALE - continue to execution
        
        # Execute BUY order (first entry or approved add)
        return self.execute_signal(symbol, confidence, ...)

============================================================================
LOGGING & OBSERVABILITY
============================================================================

Every scaling decision is logged via ScalingDecisionResult.log():

Format:
    SCALING DECISION: {BLOCK|SKIP|SCALE} | Symbol: TEST | 
    Strategy: test_strategy | Reason: reason_code | 
    Entries: 2/3 | Position %: 2.50% | Risk: $350.00 | 
    Text: Detailed human-readable explanation

Example log lines:

    WARNING | SCALING DECISION: BLOCK | Symbol: AAPL | Strategy: swing_pyramid | 
    Reason: max_entries_exceeded | Entries: 3/3 | Text: Current entries (3) >= max (3)
    
    INFO | SCALING DECISION: SKIP | Symbol: AAPL | Strategy: swing_pyramid | 
    Reason: minimum_bars_not_met | Entries: 1/3 | Text: Only 3 bars since last entry, need 5
    
    INFO | SCALING DECISION: SCALE | Symbol: AAPL | Strategy: swing_pyramid | 
    Reason: strategy_disallows_scaling | Entries: 1/3 | Position %: 2.50% | 
    Text: All scaling checks passed. Approved to add position.

============================================================================
STRATEGY CONFIGURATION EXAMPLE
============================================================================

Single-entry strategy (default):
    config = {
        "enabled": True,
        "risk_per_trade": 100,
        # No scaling_policy key → defaults to single-entry
    }

Pyramid scaling strategy:
    config = {
        "enabled": True,
        "risk_per_trade": 100,
        "scaling_policy": {
            "allows_multiple_entries": True,
            "max_entries_per_symbol": 3,
            "max_total_position_pct": 5.0,
            "scaling_type": "pyramid",
            "min_bars_between_entries": 5,
            "min_time_between_entries_seconds": 300,  # 5 minutes
            "min_signal_strength_for_add": 4.0,  # Require high confidence
            "require_no_lower_low": True,
            "require_volatility_above_median": True,
        }
    }

Average-down strategy:
    config = {
        "enabled": True,
        "risk_per_trade": 100,
        "scaling_policy": {
            "allows_multiple_entries": True,
            "max_entries_per_symbol": 3,
            "max_total_position_pct": 8.0,  # Larger position for averaging
            "scaling_type": "average",
            "min_bars_between_entries": 10,
            "min_time_between_entries_seconds": 600,
            "min_signal_strength_for_add": 2.0,  # More lenient for averaging
            "max_atr_drawdown_multiple": 1.5,  # Limit drawdown
            "require_volatility_above_median": False,  # Averaging works in quiet markets
        }
    }

============================================================================
BACKWARD COMPATIBILITY
============================================================================

Existing single-entry strategies:
- Do NOT need to modify configuration
- No scaling_policy key is required
- Behavior: attempts to add position → BLOCK with reason "strategy_disallows_scaling"
- No breaking changes

Strategies with empty scaling_policy:
- Treated same as no scaling_policy
- Default single-entry behavior

============================================================================
TESTING
============================================================================

Comprehensive unit tests in tests/test_scaling_engine.py:

1. Policy validation tests
2. Hard safety enforcement (unit tests for each check)
3. Strategy qualification tests
4. Execution feasibility tests
5. Main decision engine tests
6. Decision logging tests
7. Backward compatibility tests
8. Helper function tests

Run:
    python -m pytest tests/test_scaling_engine.py -v
    python -m pytest tests/test_scaling_engine.py::TestMainDecisionEngine::test_scale_approved_all_checks_pass -v

============================================================================
COMMON PATTERNS
============================================================================

Pattern 1: Block all scaling except specific symbols
    if symbol not in ["AAPL", "MSFT"]:
        scaling_policy.allows_multiple_entries = False

Pattern 2: Tighter constraints in high-volatility periods
    if market.volatility > threshold:
        scaling_policy.max_entries_per_symbol = 1  # No scaling in vol

Pattern 3: Adaptive scaling based on account size
    if account_equity < 50000:
        scaling_policy.max_total_position_pct = 3.0
    else:
        scaling_policy.max_total_position_pct = 5.0

Pattern 4: Require higher signal quality for adds
    scaling_policy.min_signal_strength_for_add = first_entry_confidence + 1

============================================================================
TROUBLESHOOTING
============================================================================

"SCALING DECISION: BLOCK | Reason: broker_ledger_mismatch"
→ Position reconciliation needed
→ Check trade_ledger.get_open_trades_for_symbol() vs broker.get_position()
→ Do not add until reconciled

"SCALING DECISION: SKIP | Reason: minimum_bars_not_met"
→ Signal is good but timing not right
→ Try again in next bar
→ Not an error, normal operation

"SCALING DECISION: SKIP | Reason: price_structure_violation"
→ Price structure doesn't match strategy type
→ Pyramid: entry must be better (higher) than last entry
→ Average: entry must be worse (lower) than last entry

"SCALING DECISION: BLOCK | Reason: max_entries_exceeded"
→ Already at max positions for this symbol
→ Must close a position before adding more
→ This is intentional safety limit

============================================================================
"""

# Example integration in paper_trading_executor.py

from strategies.scaling_engine import should_scale_position, ScalingDecision
from risk.scaling_policy import ScalingContext, ScalingType


def build_scaling_context_example(executor_self, symbol, confidence, market_data):
    """Build complete scaling context from execution state."""
    
    ledger_entries = executor_self.trade_ledger.get_open_trades_for_symbol(symbol)
    broker_position = executor_self.broker.get_position(symbol)
    
    context = ScalingContext(
        symbol=symbol,
        current_signal_confidence=confidence,
        proposed_entry_price=market_data["close"],
        proposed_entry_size=10,  # Position sizing calculated separately
        
        # Position state
        current_position_qty=broker_position.get("qty", 0) if broker_position else 0,
        current_position_value=broker_position.get("value", 0) if broker_position else 0,
        ledger_entries=ledger_entries,
        pending_buy_orders=executor_self.pending_orders.get(symbol, {}).get("buys", []),
        pending_sell_orders=executor_self.pending_orders.get(symbol, {}).get("sells", []),
        
        # Market state
        current_price=market_data["close"],
        atr=market_data.get("atr", 0),
        atr_rolling_median=market_data.get("atr_50d_median", 0),
        bars_since_last_entry=calculate_bars_since_entry(ledger_entries),
        minutes_since_last_entry=calculate_minutes_since_entry(ledger_entries),
        price_highest_since_last_entry=market_data.get("high_since_entry", market_data["close"]),
        price_lowest_since_last_entry=market_data.get("low_since_entry", market_data["close"]),
        has_lower_low=market_data.get("low_since_entry") < ledger_entries[-1]["price"] if ledger_entries else False,
        
        # Signal quality
        has_bearish_divergence=check_divergence(market_data),
        signal_matches_position_direction=check_direction_match(ledger_entries),
        
        # Account state
        account_equity=executor_self.broker.get_account_equity(),
        available_risk_budget=executor_self.risk_manager.get_available_budget(),
        proposed_risk_amount=estimate_risk(confidence, market_data),
        
        # Strategy state
        strategy_name=executor_self.strategy.name,
        scaling_policy=executor_self.strategy.scaling_policy,
    )
    
    return context


def execute_with_scaling_checks(executor_self, symbol, confidence, market_data):
    """Execute signal with scaling decision engine."""
    
    ledger_entries = executor_self.trade_ledger.get_open_trades_for_symbol(symbol)
    
    # First entry: no scaling check needed
    if not ledger_entries:
        return executor_self.execute_signal(symbol, confidence, market_data)
    
    # Additional entry: run scaling decision engine
    context = build_scaling_context_example(executor_self, symbol, confidence, market_data)
    result = should_scale_position(context)
    result.log(context)  # Structured audit trail
    
    if result.decision == ScalingDecision.BLOCK:
        logger.error(f"[{symbol}] Scaling BLOCKED: {result.reason_text}")
        return False, None
    elif result.decision == ScalingDecision.SKIP:
        logger.info(f"[{symbol}] Scaling SKIPPED: {result.reason_text}")
        return False, None
    
    # Approved to scale
    logger.info(f"[{symbol}] Scaling APPROVED: {result.reason_text}")
    return executor_self.execute_signal(symbol, confidence, market_data)
