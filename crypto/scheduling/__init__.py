"""
Crypto-specific downtime scheduler.

24/7 trading with enforced daily downtime window for ML training.
- Default: 03:00-05:00 UTC
- Configurable per environment
"""

import logging
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Optional, Tuple
import pytz

logger = logging.getLogger(__name__)


class TradingState(Enum):
    """Trading state enum."""
    TRADING = "trading"
    DOWNTIME = "downtime"
    TRANSITION = "transition"


class DowntimeScheduler:
    """
    Manages crypto downtime window (24/7 market).
    
    Enforces:
    - Trading paused during downtime
    - ML training runs only during downtime
    - Training must complete before downtime ends
    - Safe fallback if training overruns
    """
    
    def __init__(self, downtime_start_utc: str = "03:00", 
                 downtime_end_utc: str = "05:00",
                 timezone: str = "UTC"):
        """
        Initialize downtime scheduler.
        
        Args:
            downtime_start_utc: Start time (HH:MM format, UTC)
            downtime_end_utc: End time (HH:MM format, UTC)
            timezone: Timezone for scheduling
        """
        self.downtime_start = self._parse_time(downtime_start_utc)
        self.downtime_end = self._parse_time(downtime_end_utc)
        self.tz = pytz.timezone(timezone)
        
        if self.downtime_start >= self.downtime_end:
            raise ValueError(
                f"Downtime start {downtime_start_utc} must be before "
                f"end {downtime_end_utc}"
            )
        
        duration_mins = (
            datetime.combine(datetime.today(), self.downtime_end) -
            datetime.combine(datetime.today(), self.downtime_start)
        ).total_seconds() / 60
        
        logger.info(f"Downtime scheduler initialized")
        logger.info(f"  Window: {downtime_start_utc}-{downtime_end_utc} UTC")
        logger.info(f"  Duration: {duration_mins:.0f} minutes")
    
    def _parse_time(self, time_str: str) -> time:
        """Parse HH:MM format string to time object."""
        parts = time_str.split(':')
        return time(hour=int(parts[0]), minute=int(parts[1]))
    
    def get_current_state(self, now: Optional[datetime] = None) -> TradingState:
        """
        Get current trading state.
        
        Args:
            now: Current datetime (default: now in UTC)
        
        Returns:
            TradingState (TRADING, DOWNTIME, or TRANSITION)
        """
        if now is None:
            now = datetime.now(pytz.UTC)
        
        current_time = now.time()
        
        if self.downtime_start <= current_time < self.downtime_end:
            return TradingState.DOWNTIME
        else:
            return TradingState.TRADING
    
    def is_trading_allowed(self, now: Optional[datetime] = None) -> bool:
        """Check if trading is allowed right now."""
        return self.get_current_state(now) == TradingState.TRADING
    
    def is_training_allowed(self, now: Optional[datetime] = None) -> bool:
        """Check if ML training is allowed right now."""
        return self.get_current_state(now) == TradingState.DOWNTIME
    
    def time_until_downtime(self, now: Optional[datetime] = None) -> timedelta:
        """
        Calculate time until next downtime starts.
        
        Args:
            now: Current datetime (default: now in UTC)
        
        Returns:
            Timedelta until downtime
        """
        if now is None:
            now = datetime.now(pytz.UTC)
        
        # Today's downtime start
        downtime_today = datetime.combine(now.date(), self.downtime_start)
        downtime_today = pytz.UTC.localize(downtime_today)
        
        if now < downtime_today:
            # Downtime hasn't started yet today
            return downtime_today - now
        else:
            # Downtime was today, next one is tomorrow
            downtime_tomorrow = downtime_today + timedelta(days=1)
            return downtime_tomorrow - now
    
    def time_until_trading_resumes(self, now: Optional[datetime] = None) -> timedelta:
        """
        Calculate time until trading resumes (downtime ends).
        
        Args:
            now: Current datetime (default: now in UTC)
        
        Returns:
            Timedelta until trading resumes
        """
        if now is None:
            now = datetime.now(pytz.UTC)
        
        # Today's downtime end
        downtime_end_today = datetime.combine(now.date(), self.downtime_end)
        downtime_end_today = pytz.UTC.localize(downtime_end_today)
        
        if now < downtime_end_today:
            return downtime_end_today - now
        else:
            # Downtime ended, next one is tomorrow
            downtime_end_tomorrow = downtime_end_today + timedelta(days=1)
            return downtime_end_tomorrow - now
    
    def validate_training_completion(self, 
                                    training_start: datetime,
                                    training_end: datetime,
                                    now: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Validate that training completed before downtime ended.
        
        Args:
            training_start: When training started
            training_end: When training completed
            now: Current datetime (default: now in UTC)
        
        Returns:
            Tuple of (valid: bool, message: str)
        """
        if now is None:
            now = datetime.now(pytz.UTC)
        
        downtime_end = datetime.combine(training_start.date(), self.downtime_end)
        downtime_end = pytz.UTC.localize(downtime_end)
        
        if training_start < datetime.combine(training_start.date(), self.downtime_start):
            downtime_end = downtime_end - timedelta(days=1)
        
        if training_end > downtime_end:
            duration = (training_end - downtime_end).total_seconds() / 60
            msg = f"Training overran downtime by {duration:.1f} minutes"
            return False, msg
        
        return True, "Training completed within downtime window"


def create_scheduler(downtime_start: str = "03:00", 
                    downtime_end: str = "05:00") -> DowntimeScheduler:
    """Factory function to create downtime scheduler."""
    return DowntimeScheduler(downtime_start, downtime_end)
