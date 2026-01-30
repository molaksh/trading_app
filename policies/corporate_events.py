"""
Corporate Event Blackout System.

CRITICAL SAFETY RULE:
Block new positions around corporate events where execution risk is elevated.

Events that trigger blackouts:
- Earnings announcements
- Dividend ex-dates
- Stock splits
- Spin-offs
- Mergers/acquisitions
- Other material corporate actions

PHILOSOPHY:
- Missing event data → BLOCK symbol (fail-safe)
- Blackout window is configurable (default: ±2 days around event)
- Applies to NEW positions only (existing positions managed separately)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CorporateEventType(Enum):
    """Types of corporate events that trigger blackouts."""
    
    EARNINGS = "earnings"
    DIVIDEND_EX = "dividend_ex"
    SPLIT = "split"
    SPINOFF = "spinoff"
    MERGER = "merger"
    OTHER = "other"


@dataclass
class CorporateEvent:
    """Corporate event metadata."""
    
    symbol: str
    event_type: CorporateEventType
    event_date: datetime
    description: str = ""
    
    def __str__(self) -> str:
        return f"{self.symbol} {self.event_type.value} on {self.event_date.strftime('%Y-%m-%d')}"


class CorporateEventGuard:
    """
    Block new positions around corporate events.
    
    SAFETY PHILOSOPHY:
    - No event data → BLOCK
    - Within blackout window → BLOCK
    - Better to miss opportunity than risk elevated execution risk
    """
    
    def __init__(self, blackout_days_before: int = 2, blackout_days_after: int = 2):
        """
        Initialize corporate event guard.
        
        Args:
            blackout_days_before: Days before event to start blackout
            blackout_days_after: Days after event to end blackout
        """
        self.blackout_days_before = blackout_days_before
        self.blackout_days_after = blackout_days_after
        
        # Event calendar (symbol -> list of events)
        # In production, this would load from a data provider
        self._event_calendar: Dict[str, List[CorporateEvent]] = {}
        
        # Symbols with missing event data (BLOCK by default)
        self._missing_data_symbols: Set[str] = set()
        
        logger.info(f"CorporateEventGuard initialized (±{blackout_days_before}/{blackout_days_after} day blackout)")
    
    def load_events_from_provider(self, events: List[CorporateEvent]) -> None:
        """
        Load corporate events from data provider.
        
        In production, this would integrate with:
        - Earnings calendar API
        - Corporate actions feed
        - Exchange notifications
        
        Args:
            events: List of corporate events
        """
        self._event_calendar.clear()
        
        for event in events:
            if event.symbol not in self._event_calendar:
                self._event_calendar[event.symbol] = []
            self._event_calendar[event.symbol].append(event)
        
        logger.info(f"Loaded {len(events)} corporate events for {len(self._event_calendar)} symbols")
    
    def mark_symbol_missing_data(self, symbol: str) -> None:
        """
        Mark symbol as having missing event data.
        
        This triggers automatic BLOCK for safety.
        
        Args:
            symbol: Stock symbol
        """
        self._missing_data_symbols.add(symbol)
        logger.warning(f"Symbol {symbol} marked as missing event data → BLOCKED")
    
    def is_symbol_blocked(self, symbol: str, current_date: Optional[datetime] = None) -> bool:
        """
        Check if symbol is blocked due to corporate events.
        
        Args:
            symbol: Stock symbol to check
            current_date: Current date (defaults to now)
            
        Returns:
            True if symbol is blocked (within blackout window or missing data)
        """
        if current_date is None:
            current_date = datetime.now()
        
        # Block if missing event data (fail-safe)
        if symbol in self._missing_data_symbols:
            logger.info(f"BLOCK {symbol}: Missing corporate event data")
            return True
        
        # Check for upcoming/recent events
        events = self._event_calendar.get(symbol, [])
        
        for event in events:
            blackout_start = event.event_date - timedelta(days=self.blackout_days_before)
            blackout_end = event.event_date + timedelta(days=self.blackout_days_after)
            
            if blackout_start <= current_date <= blackout_end:
                logger.info(
                    f"BLOCK {symbol}: Within blackout window for {event.event_type.value} "
                    f"on {event.event_date.strftime('%Y-%m-%d')} "
                    f"(window: {blackout_start.strftime('%Y-%m-%d')} to {blackout_end.strftime('%Y-%m-%d')})"
                )
                return True
        
        # Not blocked
        return False
    
    def get_blocked_symbols(self, symbols: List[str], current_date: Optional[datetime] = None) -> Set[str]:
        """
        Get subset of symbols that are currently blocked.
        
        Args:
            symbols: List of symbols to check
            current_date: Current date (defaults to now)
            
        Returns:
            Set of blocked symbols
        """
        blocked = set()
        for symbol in symbols:
            if self.is_symbol_blocked(symbol, current_date):
                blocked.add(symbol)
        return blocked
    
    def get_next_event(self, symbol: str, current_date: Optional[datetime] = None) -> Optional[CorporateEvent]:
        """
        Get next upcoming corporate event for symbol.
        
        Args:
            symbol: Stock symbol
            current_date: Current date (defaults to now)
            
        Returns:
            Next corporate event or None
        """
        if current_date is None:
            current_date = datetime.now()
        
        events = self._event_calendar.get(symbol, [])
        future_events = [e for e in events if e.event_date >= current_date]
        
        if not future_events:
            return None
        
        return min(future_events, key=lambda e: e.event_date)
    
    def filter_universe(self, symbols: List[str], current_date: Optional[datetime] = None) -> List[str]:
        """
        Filter universe to remove blocked symbols.
        
        Args:
            symbols: Original symbol list
            current_date: Current date (defaults to now)
            
        Returns:
            Filtered symbol list (blocked symbols removed)
        """
        blocked = self.get_blocked_symbols(symbols, current_date)
        filtered = [s for s in symbols if s not in blocked]
        
        if blocked:
            logger.info(f"Corporate event filter: {len(blocked)} symbols blocked, {len(filtered)} allowed")
            logger.debug(f"Blocked symbols: {sorted(blocked)}")
        
        return filtered
    
    def get_blackout_summary(self, symbols: List[str], current_date: Optional[datetime] = None) -> Dict:
        """
        Get summary of blackout status for symbols.
        
        Args:
            symbols: Symbols to check
            current_date: Current date (defaults to now)
            
        Returns:
            Summary dict with statistics
        """
        if current_date is None:
            current_date = datetime.now()
        
        blocked = self.get_blocked_symbols(symbols, current_date)
        
        # Count by event type
        event_counts = {et.value: 0 for et in CorporateEventType}
        
        for symbol in blocked:
            events = self._event_calendar.get(symbol, [])
            for event in events:
                blackout_start = event.event_date - timedelta(days=self.blackout_days_before)
                blackout_end = event.event_date + timedelta(days=self.blackout_days_after)
                
                if blackout_start <= current_date <= blackout_end:
                    event_counts[event.event_type.value] += 1
        
        return {
            "total_symbols": len(symbols),
            "blocked_count": len(blocked),
            "allowed_count": len(symbols) - len(blocked),
            "missing_data_count": len(blocked & self._missing_data_symbols),
            "event_type_counts": event_counts,
            "blocked_symbols": sorted(blocked),
        }


# Global singleton
_event_guard: Optional[CorporateEventGuard] = None


def get_corporate_event_guard() -> CorporateEventGuard:
    """Get global corporate event guard instance."""
    global _event_guard
    if _event_guard is None:
        _event_guard = CorporateEventGuard()
    return _event_guard
