"""
Exit policy implementations for different trading modes.

Defines exit evaluation timing and execution:
- Swing: EOD evaluation, next-open execution
- Day Trade: Intraday evaluation, immediate execution
- Options: Expiration-aware evaluation
"""

import logging
from typing import Optional, Tuple
from policies.base import ExitPolicy, ExitUrgency

logger = logging.getLogger(__name__)


class SwingExitPolicy(ExitPolicy):
    """
    Exit policy for swing trading mode.
    
    Characteristics:
    - Evaluation: End-of-day (EOD) only
    - Execution: 5-30 minutes after next market open (two-phase model)
    - Emergency exits: Immediate (intraday, rare)
    - No intraday discretionary exits
    """
    
    # Two-phase exit execution window (minutes after market open)
    EXECUTION_WINDOW_START_MIN = 5
    EXECUTION_WINDOW_END_MIN = 30
    
    def evaluation_frequency(self) -> str:
        return 'eod'
    
    def get_exit_urgency(self, exit_reason: str) -> ExitUrgency:
        """
        Classify exit urgency based on reason.
        
        Emergency exits (stop loss, risk manager): IMMEDIATE
        Strategy exits (profit target, trend break, time): EOD
        """
        emergency_keywords = ['stop_loss', 'risk_manager', 'emergency']
        
        reason_lower = exit_reason.lower()
        for keyword in emergency_keywords:
            if keyword in reason_lower:
                return ExitUrgency.IMMEDIATE
        
        return ExitUrgency.EOD
    
    def supports_intraday_evaluation(self) -> bool:
        return False  # Swing exits evaluate EOD only
    
    def get_execution_window(self) -> Optional[Tuple[int, int]]:
        """Return execution window for swing exits (5-30 min after open)."""
        return (self.EXECUTION_WINDOW_START_MIN, self.EXECUTION_WINDOW_END_MIN)
    
    def get_name(self) -> str:
        return "SwingExitPolicy"


class IntradayExitPolicy(ExitPolicy):
    """
    Exit policy for intraday trading modes (NOT IMPLEMENTED).
    
    Future characteristics:
    - Evaluation: Continuous or periodic intraday
    - Execution: Immediate
    - Supports intraday exit signals
    """
    
    def evaluation_frequency(self) -> str:
        raise NotImplementedError(
            "IntradayExitPolicy not implemented. "
            "Intraday exit evaluation is not supported. "
            "Required implementation: evaluation_frequency='intraday' or 'continuous'"
        )
    
    def get_exit_urgency(self, exit_reason: str) -> ExitUrgency:
        raise NotImplementedError(
            "IntradayExitPolicy not implemented. "
            "Intraday exit evaluation is not supported. "
            "Required implementation: classify exit urgency for intraday signals"
        )
    
    def supports_intraday_evaluation(self) -> bool:
        raise NotImplementedError(
            "IntradayExitPolicy not implemented. "
            "Intraday exit evaluation is not supported. "
            "Required implementation: supports_intraday_evaluation=True"
        )
    
    def get_execution_window(self) -> Optional[Tuple[int, int]]:
        raise NotImplementedError(
            "IntradayExitPolicy not implemented. "
            "Intraday exit evaluation is not supported. "
            "Required implementation: return None (immediate execution)"
        )
    
    def get_name(self) -> str:
        return "IntradayExitPolicy (NOT IMPLEMENTED)"


class ExpirationAwareExitPolicy(ExitPolicy):
    """
    Exit policy for options trading with expiration awareness (NOT IMPLEMENTED).
    
    Future characteristics:
    - Evaluation: Daily or intraday, expiration-aware
    - Execution: Before expiration
    - Forced exits: Days before expiration
    """
    
    def evaluation_frequency(self) -> str:
        raise NotImplementedError(
            "ExpirationAwareExitPolicy not implemented. "
            "Options trading mode is not supported. "
            "Required implementation: expiration-aware evaluation frequency"
        )
    
    def get_exit_urgency(self, exit_reason: str) -> ExitUrgency:
        raise NotImplementedError(
            "ExpirationAwareExitPolicy not implemented. "
            "Options trading mode is not supported. "
            "Required implementation: classify urgency (expiration vs strategy)"
        )
    
    def supports_intraday_evaluation(self) -> bool:
        raise NotImplementedError(
            "ExpirationAwareExitPolicy not implemented. "
            "Options trading mode is not supported."
        )
    
    def get_execution_window(self) -> Optional[Tuple[int, int]]:
        raise NotImplementedError(
            "ExpirationAwareExitPolicy not implemented. "
            "Options trading mode is not supported. "
            "Required implementation: execution before expiration"
        )
    
    def get_name(self) -> str:
        return "ExpirationAwareExitPolicy (NOT IMPLEMENTED)"
