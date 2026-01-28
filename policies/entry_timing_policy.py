"""
Entry timing policy implementations for different trading modes.

Defines when and how often to evaluate entry signals:
- Swing: Once per day, pre-close window
- Day Trade: Multiple intraday scans
- Continuous: Real-time evaluation
"""

import logging
from typing import Optional
from policies.base import EntryTimingPolicy

logger = logging.getLogger(__name__)


class SwingEntryTimingPolicy(EntryTimingPolicy):
    """
    Entry timing policy for swing trading mode.
    
    Characteristics:
    - Frequency: Once per day
    - Timing: Pre-close window (default: 30 minutes before close)
    - No intraday entry evaluation
    - Execution: Next market open (or before close if time permits)
    """
    
    # Minutes before market close to evaluate entries
    ENTRY_WINDOW_MINUTES_BEFORE_CLOSE = 30
    
    def entry_frequency(self) -> str:
        return 'once_per_day'
    
    def get_entry_window_minutes_before_close(self) -> Optional[int]:
        return self.ENTRY_WINDOW_MINUTES_BEFORE_CLOSE
    
    def supports_intraday_entry(self) -> bool:
        return False
    
    def get_name(self) -> str:
        return "SwingEntryTimingPolicy"


class IntradayEntryTimingPolicy(EntryTimingPolicy):
    """
    Entry timing policy for intraday trading modes (NOT IMPLEMENTED).
    
    Future characteristics:
    - Frequency: Multiple times per day
    - Timing: Periodic scans (e.g., every 5-15 minutes)
    - Supports intraday entry evaluation
    """
    
    def entry_frequency(self) -> str:
        raise NotImplementedError(
            "IntradayEntryTimingPolicy not implemented. "
            "Intraday entry evaluation is not supported. "
            "Required implementation: entry_frequency='multiple_intraday'"
        )
    
    def get_entry_window_minutes_before_close(self) -> Optional[int]:
        raise NotImplementedError(
            "IntradayEntryTimingPolicy not implemented. "
            "Intraday entry evaluation is not supported. "
            "Required implementation: return None (not close-dependent)"
        )
    
    def supports_intraday_entry(self) -> bool:
        raise NotImplementedError(
            "IntradayEntryTimingPolicy not implemented. "
            "Intraday entry evaluation is not supported. "
            "Required implementation: supports_intraday_entry=True"
        )
    
    def get_name(self) -> str:
        return "IntradayEntryTimingPolicy (NOT IMPLEMENTED)"


class ContinuousEntryTimingPolicy(EntryTimingPolicy):
    """
    Entry timing policy for continuous/streaming evaluation (NOT IMPLEMENTED).
    
    Future characteristics:
    - Frequency: Continuous (streaming market data)
    - Timing: Real-time signal detection
    - Execution: Immediate
    """
    
    def entry_frequency(self) -> str:
        raise NotImplementedError(
            "ContinuousEntryTimingPolicy not implemented. "
            "Continuous entry evaluation is not supported. "
            "Required implementation: entry_frequency='continuous'"
        )
    
    def get_entry_window_minutes_before_close(self) -> Optional[int]:
        raise NotImplementedError(
            "ContinuousEntryTimingPolicy not implemented. "
            "Continuous entry evaluation is not supported. "
            "Required implementation: return None (streaming mode)"
        )
    
    def supports_intraday_entry(self) -> bool:
        raise NotImplementedError(
            "ContinuousEntryTimingPolicy not implemented. "
            "Continuous entry evaluation is not supported. "
            "Required implementation: supports_intraday_entry=True"
        )
    
    def get_name(self) -> str:
        return "ContinuousEntryTimingPolicy (NOT IMPLEMENTED)"
