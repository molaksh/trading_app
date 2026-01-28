"""
Runtime trading configuration integrator.

Creates policy-driven trading components for the active SCOPE.
Replaces hardcoded component initialization with policy-based factories.

PHASE: Future-proofing refactor
- Centralized component creation
- Policy-driven configuration
- Fail-fast on unsupported scope
"""

import logging
from typing import Optional
from dataclasses import dataclass

from config.scope import Scope, get_scope
from policies.policy_factory import create_policies_for_scope
from policies.base import TradingPolicies
from risk.trade_intent_guard import create_guard, TradeIntentGuard

logger = logging.getLogger(__name__)


@dataclass
class TradingRuntimeConfig:
    """
    Policy-driven runtime configuration for trading.
    
    All mode/market-specific behavior is defined by policies.
    Components use policies instead of hardcoded constants.
    """
    scope: Scope
    policies: TradingPolicies
    intent_guard: TradeIntentGuard
    
    def __repr__(self) -> str:
        return (
            f"TradingRuntimeConfig(\n"
            f"  scope={self.scope},\n"
            f"  policies={self.policies},\n"
            f"  intent_guard={self.intent_guard.hold_policy.get_name()}\n"
            f")"
        )


def create_trading_runtime_config(scope: Optional[Scope] = None) -> TradingRuntimeConfig:
    """
    Create policy-driven runtime configuration for trading.
    
    This factory:
    1. Creates policies for the scope
    2. Creates TradeIntentGuard with HoldPolicy
    3. Returns integrated configuration
    
    Args:
        scope: Trading scope (defaults to current SCOPE from environment)
    
    Returns:
        TradingRuntimeConfig with all policy-driven components
    
    Raises:
        NotImplementedError: If policies not implemented for scope
        ValueError: If scope not supported
    """
    if scope is None:
        scope = get_scope()
    
    logger.info("=" * 80)
    logger.info("CREATING TRADING RUNTIME CONFIGURATION")
    logger.info("=" * 80)
    logger.info(f"Scope: {scope}")
    
    # Create policies (will raise if not supported)
    policies = create_policies_for_scope(scope.mode, scope.market)
    
    # Create TradeIntentGuard with hold policy
    intent_guard = create_guard(
        hold_policy=policies.hold_policy,
        allow_manual_override=False  # Always disabled for safety
    )
    
    logger.info("✅ Trading runtime configuration created successfully")
    logger.info("=" * 80)
    
    return TradingRuntimeConfig(
        scope=scope,
        policies=policies,
        intent_guard=intent_guard,
    )


def get_market_timezone(scope: Optional[Scope] = None) -> str:
    """
    Get market timezone for scope.
    
    Args:
        scope: Trading scope (defaults to current SCOPE from environment)
    
    Returns:
        Timezone string (e.g., 'America/New_York')
    """
    if scope is None:
        scope = get_scope()
    
    policies = create_policies_for_scope(scope.mode, scope.market)
    return policies.market_hours_policy.get_timezone()


def get_entry_window_minutes(scope: Optional[Scope] = None) -> Optional[int]:
    """
    Get entry window minutes before close for scope.
    
    Args:
        scope: Trading scope (defaults to current SCOPE from environment)
    
    Returns:
        Minutes before close, or None if not applicable
    """
    if scope is None:
        scope = get_scope()
    
    policies = create_policies_for_scope(scope.mode, scope.market)
    return policies.entry_timing_policy.get_entry_window_minutes_before_close()
