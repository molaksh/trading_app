"""
Policy subsystem for mode/market-specific behavior.

This module provides explicit policy interfaces for trading behavior
that varies by mode (swing, daytrade, options) and market (us, india, crypto).

KEY PRINCIPLES:
- Explicit policy classes replace hardcoded constants
- Each mode/market has concrete policy implementations
- Unsupported modes have stubs that raise NotImplementedError
- Policy selection is container-driven (no runtime flags)
- Fail fast at startup if policy not implemented
"""

from policies.base import (
    HoldPolicy,
    ExitPolicy,
    EntryTimingPolicy,
    MarketHoursPolicy,
    TradingPolicies,
)
from policies.policy_factory import create_policies_for_scope

__all__ = [
    "HoldPolicy",
    "ExitPolicy",
    "EntryTimingPolicy",
    "MarketHoursPolicy",
    "TradingPolicies",
    "create_policies_for_scope",
]
