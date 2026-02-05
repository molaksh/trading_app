"""
Policy factory for creating mode/market-specific trading policies.

Creates policy sets based on SCOPE (mode + market combination).
Supported scopes fail-fast at startup if policies not implemented.
"""

import logging
from typing import Dict, Tuple
from policies.base import TradingPolicies
from policies.hold_policy import (
    SwingHoldPolicy,
    DayTradeHoldPolicy,
    OptionsHoldPolicy,
)
from policies.exit_policy import (
    SwingExitPolicy,
    IntradayExitPolicy,
    ExpirationAwareExitPolicy,
)
from policies.entry_timing_policy import (
    SwingEntryTimingPolicy,
    IntradayEntryTimingPolicy,
    ContinuousEntryTimingPolicy,
)
from policies.market_hours_policy import (
    USEquityMarketHours,
    Crypto24x7MarketHours,
)
from policies.market_hours.india_equity_market_hours import IndiaEquityMarketHours

logger = logging.getLogger(__name__)


# Policy registry mapping (mode, market) -> policy classes
POLICY_REGISTRY: Dict[Tuple[str, str], Dict[str, type]] = {
    # US Swing (IMPLEMENTED)
    ("swing", "us"): {
        "hold": SwingHoldPolicy,
        "exit": SwingExitPolicy,
        "entry_timing": SwingEntryTimingPolicy,
        "market_hours": USEquityMarketHours,
    },
    
    # US Day Trading (NOT IMPLEMENTED)
    ("daytrade", "us"): {
        "hold": DayTradeHoldPolicy,
        "exit": IntradayExitPolicy,
        "entry_timing": IntradayEntryTimingPolicy,
        "market_hours": USEquityMarketHours,
    },
    
    # US Options (NOT IMPLEMENTED)
    ("options", "us"): {
        "hold": OptionsHoldPolicy,
        "exit": ExpirationAwareExitPolicy,
        "entry_timing": SwingEntryTimingPolicy,  # Options may use swing-like timing
        "market_hours": USEquityMarketHours,
    },
    
    # India Swing (NOT IMPLEMENTED)
    ("swing", "india"): {
        "hold": SwingHoldPolicy,  # Swing hold policy is reusable
        "exit": SwingExitPolicy,  # Swing exit policy is reusable
        "entry_timing": SwingEntryTimingPolicy,  # Swing timing is reusable
        "market_hours": IndiaEquityMarketHours,  # NOT IMPLEMENTED
    },
    
    # India Day Trading (NOT IMPLEMENTED)
    ("daytrade", "india"): {
        "hold": DayTradeHoldPolicy,
        "exit": IntradayExitPolicy,
        "entry_timing": IntradayEntryTimingPolicy,
        "market_hours": IndiaEquityMarketHours,
    },
    
    # Crypto (IMPLEMENTED)
    ("crypto", "global"): {
        "hold": SwingHoldPolicy,  # Crypto uses swing-like holding logic
        "exit": SwingExitPolicy,  # Crypto uses swing-like exit signals
        "entry_timing": ContinuousEntryTimingPolicy,  # 24/7 entry for crypto
        "market_hours": Crypto24x7MarketHours,  # 24/7 market for crypto
    },
    
    # Crypto Swing (NOT IMPLEMENTED)
    ("swing", "crypto"): {
        "hold": SwingHoldPolicy,  # Swing hold policy may be reusable
        "exit": SwingExitPolicy,  # BUT: EOD concept unclear for 24x7
        "entry_timing": SwingEntryTimingPolicy,  # Pre-close window irrelevant
        "market_hours": Crypto24x7MarketHours,  # NOT IMPLEMENTED
    },
}


# Supported scope declarations (container-driven)
SUPPORTED_SCOPES = {
    # US Swing is fully implemented
    ("swing", "us", "equity"): True,
    
    # India Swing is fully implemented
    ("swing", "india", "equity"): True,
    
    # Crypto Global is fully implemented
    ("crypto", "global", "crypto"): True,
    
    # All other combinations are NOT supported
    ("daytrade", "us", "equity"): False,
    ("options", "us", "option"): False,
    ("daytrade", "india", "equity"): False,
    ("swing", "crypto", "btc"): False,
    ("swing", "crypto", "eth"): False,
}


def is_scope_supported(mode: str, market: str, instrument_type: str = "equity") -> bool:
    """
    Check if a scope combination is supported.
    
    Args:
        mode: Trading mode (swing, daytrade, options)
        market: Market (us, india, crypto)
        instrument_type: Instrument type (equity, option, btc, eth)
    
    Returns:
        True if supported, False otherwise
    """
    return SUPPORTED_SCOPES.get((mode, market, instrument_type), False)


def get_supported_scopes() -> list:
    """Get list of all supported scope combinations."""
    return [
        {"mode": mode, "market": market, "instrument": inst}
        for (mode, market, inst), supported in SUPPORTED_SCOPES.items()
        if supported
    ]


def create_policies_for_scope(mode: str, market: str) -> TradingPolicies:
    """
    Create trading policies for a specific mode/market combination.
    
    This function performs fail-fast validation:
    - If scope is not supported, raises ValueError
    - If any policy is not implemented, instantiation will raise NotImplementedError
    
    Args:
        mode: Trading mode (swing, daytrade, options)
        market: Market (us, india, crypto)
    
    Returns:
        TradingPolicies container with all policy instances
    
    Raises:
        ValueError: If mode/market combination not registered or not supported
        NotImplementedError: If any policy not implemented (raised during instantiation)
    """
    logger.info("=" * 80)
    logger.info("CREATING TRADING POLICIES")
    logger.info("=" * 80)
    logger.info(f"Mode: {mode}")
    logger.info(f"Market: {market}")
    
    # Check if scope is supported
    scope_key = (mode, market)
    
    # First check if registered
    if scope_key not in POLICY_REGISTRY:
        supported = get_supported_scopes()
        raise ValueError(
            f"Unsupported mode/market combination: mode={mode}, market={market}\n"
            f"Supported scopes: {supported}\n"
            f"To add support, register policies in policies/policy_factory.py"
        )
    
    # Then check if actually supported (not just registered as stub)
    if not is_scope_supported(mode, market, "equity"):
        raise ValueError(
            f"Mode/market combination not supported: mode={mode}, market={market}\n"
            f"This scope is registered but not yet fully implemented.\n"
            f"Supported scopes: {get_supported_scopes()}"
        )
    
    # Get policy classes for this scope
    policy_classes = POLICY_REGISTRY[scope_key]
    
    # Instantiate policies (may raise NotImplementedError if not implemented)
    try:
        hold_policy = policy_classes["hold"]()
        exit_policy = policy_classes["exit"]()
        entry_timing_policy = policy_classes["entry_timing"]()
        market_hours_policy = policy_classes["market_hours"]()
        
        policies = TradingPolicies(
            hold_policy=hold_policy,
            exit_policy=exit_policy,
            entry_timing_policy=entry_timing_policy,
            market_hours_policy=market_hours_policy,
        )
        
        logger.info("✅ Policies created successfully:")
        logger.info(f"  Hold Policy: {hold_policy.get_name()}")
        logger.info(f"  Exit Policy: {exit_policy.get_name()}")
        logger.info(f"  Entry Timing Policy: {entry_timing_policy.get_name()}")
        logger.info(f"  Market Hours Policy: {market_hours_policy.get_name()}")
        logger.info("=" * 80)
        
        return policies
        
    except NotImplementedError as e:
        logger.error("=" * 80)
        logger.error("❌ POLICY NOT IMPLEMENTED")
        logger.error("=" * 80)
        logger.error(f"Mode: {mode}")
        logger.error(f"Market: {market}")
        logger.error(f"Error: {str(e)}")
        logger.error("=" * 80)
        raise
