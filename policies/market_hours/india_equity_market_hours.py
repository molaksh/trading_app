"""
India NSE Equity Market Hours Policy.

Market Hours (IST):
- Pre-open: 9:00 AM - 9:15 AM
- Trading: 9:15 AM - 3:30 PM
- Timezone: Asia/Kolkata

Holidays:
- NSE holiday calendar (stub for v1)
- Weekends (Saturday, Sunday)
"""

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Tuple

from policies.base import MarketHoursPolicy

logger = logging.getLogger(__name__)


class IndiaEquityMarketHours(MarketHoursPolicy):
    """
    NSE (National Stock Exchange) market hours for equity trading.
    
    Trading Schedule:
    - Pre-open: 9:00 AM - 9:15 AM IST
    - Regular: 9:15 AM - 3:30 PM IST
    - Timezone: Asia/Kolkata (IST = UTC+5:30)
    
    Holidays:
    - NSE holiday calendar
    - Weekends (Saturday, Sunday)
    """
    
    TIMEZONE = "Asia/Kolkata"
    MARKET_OPEN = time(9, 15)   # 9:15 AM IST
    MARKET_CLOSE = time(15, 30)  # 3:30 PM IST
    
    # NSE holidays 2026 (example - should be loaded from config/API)
    # Format: (month, day)
    NSE_HOLIDAYS_2026 = [
        (1, 26),   # Republic Day
        (3, 14),   # Maha Shivaratri
        (3, 25),   # Holi
        (4, 10),   # Mahavir Jayanti
        (4, 14),   # Dr. Ambedkar Jayanti
        (4, 18),   # Good Friday
        (5, 1),    # Maharashtra Day
        (8, 15),   # Independence Day
        (8, 27),   # Ganesh Chaturthi
        (10, 2),   # Gandhi Jayanti
        (10, 24),  # Dussehra
        (11, 12),  # Diwali
        (11, 13),  # Diwali (Balipratipada)
        (11, 14),  # Guru Nanak Jayanti
        (12, 25),  # Christmas
    ]
    
    def __init__(self):
        """Initialize India market hours policy."""
        self.tz = ZoneInfo(self.TIMEZONE)
        logger.info("IndiaEquityMarketHours initialized")
        logger.info(f"  Market hours: {self.MARKET_OPEN} - {self.MARKET_CLOSE} {self.TIMEZONE}")
    
    def get_name(self) -> str:
        """Get policy name."""
        return "IndiaEquityMarketHours"
    
    def get_timezone(self) -> str:
        """Get market timezone."""
        return self.TIMEZONE
    
    def get_market_open_time(self) -> time:
        """Get market open time."""
        return self.MARKET_OPEN
    
    def get_market_close_time(self) -> time:
        """Get market close time."""
        return self.MARKET_CLOSE
    
    def is_24x7_market(self) -> bool:
        """NSE equity market has daily close."""
        return False
    
    def has_market_close(self) -> bool:
        """NSE equity market closes daily at 3:30 PM."""
        return True
    
    def is_trading_day(self, date: datetime) -> bool:
        """
        Check if date is a trading day.
        
        Args:
            date: Date to check (any timezone)
        
        Returns:
            True if trading day, False otherwise
        """
        # Convert to IST
        dt_ist = date.astimezone(self.tz)
        
        # Check weekend
        if dt_ist.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
        
        # Check holidays
        date_tuple = (dt_ist.month, dt_ist.day)
        if date_tuple in self.NSE_HOLIDAYS_2026:
            logger.debug(f"{dt_ist.date()} is NSE holiday")
            return False
        
        return True
    
    def get_market_open(self, date: datetime) -> datetime:
        """
        Get market open time for a date.
        
        Args:
            date: Trading day date
        
        Returns:
            Market open datetime in IST
        """
        dt_ist = date.astimezone(self.tz)
        return dt_ist.replace(
            hour=self.MARKET_OPEN.hour,
            minute=self.MARKET_OPEN.minute,
            second=0,
            microsecond=0
        )
    
    def get_market_close(self, date: datetime) -> datetime:
        """
        Get market close time for a date.
        
        Args:
            date: Trading day date
        
        Returns:
            Market close datetime in IST
        """
        dt_ist = date.astimezone(self.tz)
        return dt_ist.replace(
            hour=self.MARKET_CLOSE.hour,
            minute=self.MARKET_CLOSE.minute,
            second=0,
            microsecond=0
        )
    
    def is_market_open(self, dt: Optional[datetime] = None) -> bool:
        """
        Check if market is currently open.
        
        Args:
            dt: Datetime to check (defaults to now)
        
        Returns:
            True if market is open
        """
        if dt is None:
            dt = datetime.now(self.tz)
        else:
            dt = dt.astimezone(self.tz)
        
        # Check if trading day
        if not self.is_trading_day(dt):
            return False
        
        # Check if within trading hours
        market_open = self.get_market_open(dt)
        market_close = self.get_market_close(dt)
        
        return market_open <= dt <= market_close
    
    def get_next_trading_day(self, date: datetime) -> datetime:
        """
        Get next trading day after given date.
        
        Args:
            date: Starting date
        
        Returns:
            Next trading day
        """
        dt_ist = date.astimezone(self.tz)
        current = dt_ist + timedelta(days=1)
        
        # Search up to 30 days ahead (handle long holiday periods)
        for _ in range(30):
            if self.is_trading_day(current):
                return current
            current += timedelta(days=1)
        
        raise ValueError(f"No trading day found within 30 days of {date}")
    
    def get_previous_trading_day(self, date: datetime) -> datetime:
        """
        Get previous trading day before given date.
        
        Args:
            date: Starting date
        
        Returns:
            Previous trading day
        """
        dt_ist = date.astimezone(self.tz)
        current = dt_ist - timedelta(days=1)
        
        # Search up to 30 days back
        for _ in range(30):
            if self.is_trading_day(current):
                return current
            current -= timedelta(days=1)
        
        raise ValueError(f"No trading day found within 30 days before {date}")
    
    def time_until_open(self, dt: Optional[datetime] = None) -> Optional[timedelta]:
        """
        Get time until next market open.
        
        Args:
            dt: Reference datetime (defaults to now)
        
        Returns:
            Timedelta until open, or None if market is open
        """
        if dt is None:
            dt = datetime.now(self.tz)
        else:
            dt = dt.astimezone(self.tz)
        
        if self.is_market_open(dt):
            return None
        
        # If after close today, next open is tomorrow (or next trading day)
        today_close = self.get_market_close(dt)
        if dt > today_close:
            next_day = self.get_next_trading_day(dt)
            next_open = self.get_market_open(next_day)
        else:
            # Before open today
            if self.is_trading_day(dt):
                next_open = self.get_market_open(dt)
            else:
                next_day = self.get_next_trading_day(dt)
                next_open = self.get_market_open(next_day)
        
        return next_open - dt
    
    def time_until_close(self, dt: Optional[datetime] = None) -> Optional[timedelta]:
        """
        Get time until market close.
        
        Args:
            dt: Reference datetime (defaults to now)
        
        Returns:
            Timedelta until close, or None if market is closed
        """
        if dt is None:
            dt = datetime.now(self.tz)
        else:
            dt = dt.astimezone(self.tz)
        
        if not self.is_market_open(dt):
            return None
        
        market_close = self.get_market_close(dt)
        return market_close - dt
