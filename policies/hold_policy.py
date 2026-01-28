"""
Hold policy implementations for different trading modes.

Defines position holding constraints:
- Swing: 2-20 day holds, no same-day exits
- Day Trade: 0-1 day holds, same-day exits allowed
- Options: Expiration-aware holds
"""

import logging
from typing import Optional, Tuple
from policies.base import HoldPolicy

logger = logging.getLogger(__name__)


class SwingHoldPolicy(HoldPolicy):
    """
    Hold policy for swing trading mode.
    
    Characteristics:
    - Minimum hold: 2 days (prevents behavioral PDT)
    - Maximum hold: 20 days (forces position review)
    - No same-day discretionary exits (swing trading philosophy)
    - Risk-reducing exits (stop loss, risk manager) always allowed
    """
    
    MIN_HOLD_DAYS = 2
    MAX_HOLD_DAYS = 20
    
    def min_hold_days(self) -> int:
        return self.MIN_HOLD_DAYS
    
    def max_hold_days(self) -> int:
        return self.MAX_HOLD_DAYS
    
    def allows_same_day_exit(self) -> bool:
        return False
    
    def is_forced_exit_required(self, holding_days: int) -> bool:
        return holding_days > self.MAX_HOLD_DAYS
    
    def validate_hold_period(self, holding_days: int, is_risk_reducing: bool) -> Tuple[bool, Optional[str]]:
        """
        Validate swing hold period constraints.
        
        Logic:
        1. Risk-reducing exits (stop loss, risk manager) ALWAYS allowed
        2. Same-day discretionary exits BLOCKED
        3. Min hold period enforced for discretionary exits
        4. Max hold period triggers forced exit
        """
        # Risk-reducing exits bypass all hold period checks
        if is_risk_reducing:
            return (True, None)
        
        # Force exit if max hold exceeded
        if holding_days > self.MAX_HOLD_DAYS:
            return (True, None)  # Allow forced exit
        
        # Block same-day discretionary exits
        if holding_days == 0:
            return (False, f"Same-day discretionary exit not allowed (swing mode)")
        
        # Block exits before minimum hold period
        if holding_days < self.MIN_HOLD_DAYS:
            return (False, f"Must hold for {self.MIN_HOLD_DAYS} days ({holding_days} days held)")
        
        # All checks passed
        return (True, None)
    
    def get_name(self) -> str:
        return "SwingHoldPolicy"


class DayTradeHoldPolicy(HoldPolicy):
    """
    Hold policy for day trading mode (NOT IMPLEMENTED).
    
    Future characteristics:
    - Minimum hold: 0 days (same-day exits allowed)
    - Maximum hold: 1 day (positions closed by EOD)
    - Same-day exits: ALLOWED
    - Overnight holds: BLOCKED
    """
    
    def min_hold_days(self) -> int:
        raise NotImplementedError(
            "DayTradeHoldPolicy not implemented. "
            "Day trading mode is not supported. "
            "Required implementation: min_hold_days=0"
        )
    
    def max_hold_days(self) -> int:
        raise NotImplementedError(
            "DayTradeHoldPolicy not implemented. "
            "Day trading mode is not supported. "
            "Required implementation: max_hold_days=1"
        )
    
    def allows_same_day_exit(self) -> bool:
        raise NotImplementedError(
            "DayTradeHoldPolicy not implemented. "
            "Day trading mode is not supported. "
            "Required implementation: allows_same_day_exit=True"
        )
    
    def is_forced_exit_required(self, holding_days: int) -> bool:
        raise NotImplementedError(
            "DayTradeHoldPolicy not implemented. "
            "Day trading mode is not supported."
        )
    
    def validate_hold_period(self, holding_days: int, is_risk_reducing: bool) -> Tuple[bool, Optional[str]]:
        raise NotImplementedError(
            "DayTradeHoldPolicy not implemented. "
            "Day trading mode is not supported. "
            "To implement: allow same-day exits, block overnight holds"
        )
    
    def get_name(self) -> str:
        return "DayTradeHoldPolicy (NOT IMPLEMENTED)"


class OptionsHoldPolicy(HoldPolicy):
    """
    Hold policy for options trading mode (NOT IMPLEMENTED).
    
    Future characteristics:
    - Expiration-aware holds
    - Forced exit before expiration
    - Early assignment risk management
    """
    
    def min_hold_days(self) -> int:
        raise NotImplementedError(
            "OptionsHoldPolicy not implemented. "
            "Options trading mode is not supported. "
            "Required implementation: expiration-aware min hold"
        )
    
    def max_hold_days(self) -> int:
        raise NotImplementedError(
            "OptionsHoldPolicy not implemented. "
            "Options trading mode is not supported. "
            "Required implementation: max_hold=days_to_expiration-1"
        )
    
    def allows_same_day_exit(self) -> bool:
        raise NotImplementedError(
            "OptionsHoldPolicy not implemented. "
            "Options trading mode is not supported."
        )
    
    def is_forced_exit_required(self, holding_days: int) -> bool:
        raise NotImplementedError(
            "OptionsHoldPolicy not implemented. "
            "Options trading mode is not supported. "
            "Required implementation: check days_to_expiration"
        )
    
    def validate_hold_period(self, holding_days: int, is_risk_reducing: bool) -> Tuple[bool, Optional[str]]:
        raise NotImplementedError(
            "OptionsHoldPolicy not implemented. "
            "Options trading mode is not supported. "
            "To implement: expiration risk checks, early assignment handling"
        )
    
    def get_name(self) -> str:
        return "OptionsHoldPolicy (NOT IMPLEMENTED)"
