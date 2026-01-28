"""
Base policy interfaces for mode/market-specific behavior.

These interfaces define contracts for trading policies that vary by:
- Mode: swing, daytrade, options
- Market: us, india, crypto
- Instrument: equity, option, future

Each interface must be implemented for supported mode/market combinations.
Unsupported combinations should have stub implementations that raise NotImplementedError.
"""

from abc import ABC, abstractmethod
from datetime import date, datetime, time
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ExitUrgency(Enum):
    """Exit execution urgency classification."""
    EOD = "eod"                      # Execute at end of day or next open
    IMMEDIATE = "immediate"          # Execute ASAP (risk-reducing)
    SCHEDULED = "scheduled"          # Execute at specific time


@dataclass
class TradingPolicies:
    """
    Container for all trading policies for a specific scope.
    
    Each scope (mode + market combination) has its own policy set.
    Policies define behavior that varies by mode/market.
    """
    hold_policy: 'HoldPolicy'
    exit_policy: 'ExitPolicy'
    entry_timing_policy: 'EntryTimingPolicy'
    market_hours_policy: 'MarketHoursPolicy'
    
    def __repr__(self) -> str:
        return (
            f"TradingPolicies("
            f"hold={self.hold_policy.__class__.__name__}, "
            f"exit={self.exit_policy.__class__.__name__}, "
            f"entry={self.entry_timing_policy.__class__.__name__}, "
            f"market={self.market_hours_policy.__class__.__name__})"
        )


class HoldPolicy(ABC):
    """
    Policy interface for position holding constraints.
    
    Defines:
    - Minimum hold period (e.g., 2 days for swing, 0 for daytrade)
    - Maximum hold period (e.g., 20 days for swing, 1 for daytrade)
    - Same-day exit rules
    - Hold period validation
    """
    
    @abstractmethod
    def min_hold_days(self) -> int:
        """Minimum days before discretionary exit allowed."""
        pass
    
    @abstractmethod
    def max_hold_days(self) -> int:
        """Maximum days before forced exit required."""
        pass
    
    @abstractmethod
    def allows_same_day_exit(self) -> bool:
        """Whether same-day discretionary exits are allowed."""
        pass
    
    @abstractmethod
    def is_forced_exit_required(self, holding_days: int) -> bool:
        """Check if holding period exceeded and forced exit required."""
        pass
    
    @abstractmethod
    def validate_hold_period(self, holding_days: int, is_risk_reducing: bool) -> Tuple[bool, Optional[str]]:
        """
        Validate if exit is allowed based on hold period.
        
        Args:
            holding_days: Days position has been held
            is_risk_reducing: Whether exit is risk-reducing (stop loss, etc.)
        
        Returns:
            Tuple of (allowed, block_reason)
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Policy name for logging."""
        pass


class ExitPolicy(ABC):
    """
    Policy interface for exit evaluation timing and execution.
    
    Defines:
    - When to evaluate exits (EOD, intraday, continuous)
    - Exit urgency classification
    - Exit timing windows
    """
    
    @abstractmethod
    def evaluation_frequency(self) -> str:
        """
        How often to evaluate exits.
        
        Returns:
            'eod' (once per day), 'intraday' (multiple times), 'continuous' (streaming)
        """
        pass
    
    @abstractmethod
    def get_exit_urgency(self, exit_reason: str) -> ExitUrgency:
        """
        Determine exit urgency based on reason.
        
        Args:
            exit_reason: Exit reason string
        
        Returns:
            ExitUrgency enum value
        """
        pass
    
    @abstractmethod
    def supports_intraday_evaluation(self) -> bool:
        """Whether this policy supports intraday exit evaluation."""
        pass
    
    @abstractmethod
    def get_execution_window(self) -> Optional[Tuple[int, int]]:
        """
        Get execution window for exits (minutes after market open).
        
        Returns:
            Tuple of (start_minutes, end_minutes) or None if immediate
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Policy name for logging."""
        pass


class EntryTimingPolicy(ABC):
    """
    Policy interface for entry timing and frequency.
    
    Defines:
    - When to evaluate entries (pre-close, intraday, continuous)
    - Entry frequency (once per day, multiple times, continuous)
    - Entry timing windows
    """
    
    @abstractmethod
    def entry_frequency(self) -> str:
        """
        How often to evaluate entries.
        
        Returns:
            'once_per_day', 'multiple_intraday', 'continuous'
        """
        pass
    
    @abstractmethod
    def get_entry_window_minutes_before_close(self) -> Optional[int]:
        """
        Minutes before market close to run entry evaluation.
        
        Returns:
            Minutes before close, or None if not applicable
        """
        pass
    
    @abstractmethod
    def supports_intraday_entry(self) -> bool:
        """Whether this policy supports intraday entry evaluation."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Policy name for logging."""
        pass


class MarketHoursPolicy(ABC):
    """
    Policy interface for market hours and timing.
    
    Defines:
    - Market timezone
    - Market open/close times
    - Trading hours validation
    - Holiday calendar (future)
    """
    
    @abstractmethod
    def get_timezone(self) -> str:
        """
        Market timezone name.
        
        Returns:
            Timezone string (e.g., 'America/New_York', 'Asia/Kolkata')
        """
        pass
    
    @abstractmethod
    def get_market_open_time(self) -> time:
        """
        Market open time in market timezone.
        
        Returns:
            time object (e.g., time(9, 30) for 9:30 AM)
        """
        pass
    
    @abstractmethod
    def get_market_close_time(self) -> time:
        """
        Market close time in market timezone.
        
        Returns:
            time object (e.g., time(16, 0) for 4:00 PM)
        """
        pass
    
    @abstractmethod
    def is_24x7_market(self) -> bool:
        """Whether market operates 24x7 (e.g., crypto)."""
        pass
    
    @abstractmethod
    def has_market_close(self) -> bool:
        """Whether market has a daily close (False for 24x7 markets)."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Policy name for logging."""
        pass
