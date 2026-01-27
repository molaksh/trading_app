"""
Market Interface - Defines regulatory and operational rules per market.

Markets define:
- Trading hours and holidays
- Regulatory constraints (PDT, margin requirements)
- Settlement rules (T+0, T+1, T+2)
- Tax implications
- Circuit breakers and limits
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, time, date
from typing import List, Dict, Any, Optional
from enum import Enum
import pytz


class MarketStatus(Enum):
    """Current market state."""
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    OPEN = "open"
    POST_MARKET = "post_market"
    HOLIDAY = "holiday"


@dataclass
class TradingHours:
    """Trading session hours."""
    market_open: time
    market_close: time
    pre_market_open: Optional[time] = None
    post_market_close: Optional[time] = None
    timezone: str = "US/Eastern"


class Market(ABC):
    """
    Base interface for market-specific rules.
    
    RESPONSIBILITIES:
    - Define trading hours
    - Check if market is open
    - Validate regulatory compliance
    - Apply market-specific constraints
    """
    
    def __init__(
        self,
        market_id: str,
        trading_hours: TradingHours,
        holidays: List[date] = None,
    ):
        """
        Initialize market.
        
        Args:
            market_id: Unique market identifier (e.g., "NSE", "NYSE")
            trading_hours: Trading session hours
            holidays: List of market holidays
        """
        self.market_id = market_id
        self.trading_hours = trading_hours
        self.holidays = holidays or []
        self.timezone = pytz.timezone(trading_hours.timezone)
    
    @abstractmethod
    def is_market_open(self, check_time: Optional[datetime] = None) -> bool:
        """
        Check if market is currently open.
        
        Args:
            check_time: Time to check (default: now in market timezone)
        
        Returns:
            True if market is open for trading
        """
        pass
    
    @abstractmethod
    def get_market_status(self, check_time: Optional[datetime] = None) -> MarketStatus:
        """
        Get current market status.
        
        Args:
            check_time: Time to check (default: now)
        
        Returns:
            MarketStatus enum
        """
        pass
    
    @abstractmethod
    def requires_pdt_check(self, account_context: Dict[str, Any]) -> bool:
        """
        Determine if PDT rules apply to this account.
        
        Args:
            account_context: Account details (equity, type, etc.)
        
        Returns:
            True if PDT rules must be enforced
        """
        pass
    
    @abstractmethod
    def get_settlement_days(self, instrument_type: str) -> int:
        """
        Get settlement period for instrument type.
        
        Args:
            instrument_type: Type of instrument
        
        Returns:
            Number of days to settlement (T+N)
        """
        pass
    
    def is_trading_day(self, check_date: date) -> bool:
        """Check if date is a trading day (not weekend or holiday)."""
        # Check weekend
        if check_date.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        
        # Check holidays
        if check_date in self.holidays:
            return False
        
        return True
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id='{self.market_id}')"


class IndiaMarket(Market):
    """
    NSE/BSE India market rules.
    
    CHARACTERISTICS:
    - Trading hours: 9:15 AM - 3:30 PM IST
    - Settlement: T+1 (moving to T+0)
    - No PDT rules (SEBI regulations different)
    - Margin: Intraday leverage allowed
    - Lot sizes: Varies by stock (10, 25, 50, etc.)
    """
    
    def __init__(self):
        """Initialize India market."""
        trading_hours = TradingHours(
            market_open=time(9, 15),     # 9:15 AM IST
            market_close=time(15, 30),   # 3:30 PM IST
            pre_market_open=time(9, 0),  # 9:00 AM IST
            post_market_close=time(16, 0),  # 4:00 PM IST
            timezone="Asia/Kolkata",
        )
        
        super().__init__(
            market_id="NSE",
            trading_hours=trading_hours,
            holidays=[],  # TODO: Load India holidays
        )
    
    def is_market_open(self, check_time: Optional[datetime] = None) -> bool:
        """Check if NSE is open."""
        if check_time is None:
            check_time = datetime.now(self.timezone)
        elif check_time.tzinfo is None:
            check_time = self.timezone.localize(check_time)
        else:
            check_time = check_time.astimezone(self.timezone)
        
        # Check if trading day
        if not self.is_trading_day(check_time.date()):
            return False
        
        # Check if within trading hours
        current_time = check_time.time()
        return (
            self.trading_hours.market_open <= current_time <= self.trading_hours.market_close
        )
    
    def get_market_status(self, check_time: Optional[datetime] = None) -> MarketStatus:
        """Get NSE market status."""
        if check_time is None:
            check_time = datetime.now(self.timezone)
        elif check_time.tzinfo is None:
            check_time = self.timezone.localize(check_time)
        else:
            check_time = check_time.astimezone(self.timezone)
        
        # Check holiday
        if not self.is_trading_day(check_time.date()):
            return MarketStatus.HOLIDAY
        
        current_time = check_time.time()
        
        # Check pre-market
        if (self.trading_hours.pre_market_open and 
            self.trading_hours.pre_market_open <= current_time < self.trading_hours.market_open):
            return MarketStatus.PRE_MARKET
        
        # Check open
        if self.trading_hours.market_open <= current_time <= self.trading_hours.market_close:
            return MarketStatus.OPEN
        
        # Check post-market
        if (self.trading_hours.post_market_close and
            self.trading_hours.market_close < current_time <= self.trading_hours.post_market_close):
            return MarketStatus.POST_MARKET
        
        return MarketStatus.CLOSED
    
    def requires_pdt_check(self, account_context: Dict[str, Any]) -> bool:
        """
        India does NOT have PDT rules like US.
        
        SEBI allows intraday trading without PDT restrictions.
        However, behavioral guard still applies.
        """
        return False
    
    def get_settlement_days(self, instrument_type: str) -> int:
        """India settlement: T+1 (moving to T+0)."""
        if instrument_type == "equity":
            return 1  # T+1 currently, will become T+0
        elif instrument_type == "option":
            return 1  # T+1
        else:
            return 1


class USMarket(Market):
    """
    NYSE/NASDAQ US market rules.
    
    CHARACTERISTICS:
    - Trading hours: 9:30 AM - 4:00 PM ET
    - Settlement: T+2 for equities, T+1 for options
    - PDT rules: Yes (margin accounts < $25k)
    - Margin: Reg T (50% for stocks)
    - Lot size: 1 share
    """
    
    def __init__(self):
        """Initialize US market."""
        trading_hours = TradingHours(
            market_open=time(9, 30),     # 9:30 AM ET
            market_close=time(16, 0),    # 4:00 PM ET
            pre_market_open=time(4, 0),  # 4:00 AM ET
            post_market_close=time(20, 0),  # 8:00 PM ET
            timezone="US/Eastern",
        )
        
        super().__init__(
            market_id="NYSE",
            trading_hours=trading_hours,
            holidays=[],  # TODO: Load US holidays
        )
    
    def is_market_open(self, check_time: Optional[datetime] = None) -> bool:
        """Check if US market is open."""
        if check_time is None:
            check_time = datetime.now(self.timezone)
        elif check_time.tzinfo is None:
            check_time = self.timezone.localize(check_time)
        else:
            check_time = check_time.astimezone(self.timezone)
        
        # Check if trading day
        if not self.is_trading_day(check_time.date()):
            return False
        
        # Check if within trading hours
        current_time = check_time.time()
        return (
            self.trading_hours.market_open <= current_time <= self.trading_hours.market_close
        )
    
    def get_market_status(self, check_time: Optional[datetime] = None) -> MarketStatus:
        """Get US market status."""
        if check_time is None:
            check_time = datetime.now(self.timezone)
        elif check_time.tzinfo is None:
            check_time = self.timezone.localize(check_time)
        else:
            check_time = check_time.astimezone(self.timezone)
        
        # Check holiday
        if not self.is_trading_day(check_time.date()):
            return MarketStatus.HOLIDAY
        
        current_time = check_time.time()
        
        # Check pre-market
        if (self.trading_hours.pre_market_open and 
            self.trading_hours.pre_market_open <= current_time < self.trading_hours.market_open):
            return MarketStatus.PRE_MARKET
        
        # Check open
        if self.trading_hours.market_open <= current_time <= self.trading_hours.market_close:
            return MarketStatus.OPEN
        
        # Check post-market
        if (self.trading_hours.post_market_close and
            self.trading_hours.market_close < current_time <= self.trading_hours.post_market_close):
            return MarketStatus.POST_MARKET
        
        return MarketStatus.CLOSED
    
    def requires_pdt_check(self, account_context: Dict[str, Any]) -> bool:
        """
        US PDT rules apply to:
        - Margin accounts
        - With equity < $25,000
        
        Cash accounts and accounts > $25k are exempt.
        """
        account_type = account_context.get("account_type", "CASH")
        account_equity = account_context.get("account_equity", 0)
        
        if account_type == "CASH":
            return False  # Cash accounts exempt from PDT
        
        # Margin accounts < $25k subject to PDT
        return account_equity < 25000.0
    
    def get_settlement_days(self, instrument_type: str) -> int:
        """US settlement periods."""
        if instrument_type == "equity":
            return 2  # T+2
        elif instrument_type == "option":
            return 1  # T+1
        else:
            return 2


class CryptoMarket(Market):
    """
    Global cryptocurrency market.
    
    CHARACTERISTICS:
    - Trading hours: 24/7
    - Settlement: Instant (T+0)
    - No PDT rules
    - Margin: Varies by exchange (1x-125x)
    - Lot size: Fractional
    """
    
    def __init__(self):
        """Initialize crypto market."""
        trading_hours = TradingHours(
            market_open=time(0, 0),      # 24/7
            market_close=time(23, 59),
            timezone="UTC",
        )
        
        super().__init__(
            market_id="CRYPTO",
            trading_hours=trading_hours,
            holidays=[],  # No holidays in crypto
        )
    
    def is_market_open(self, check_time: Optional[datetime] = None) -> bool:
        """Crypto market always open."""
        return True
    
    def get_market_status(self, check_time: Optional[datetime] = None) -> MarketStatus:
        """Crypto is always open."""
        return MarketStatus.OPEN
    
    def requires_pdt_check(self, account_context: Dict[str, Any]) -> bool:
        """Crypto has no PDT rules."""
        return False
    
    def get_settlement_days(self, instrument_type: str) -> int:
        """Crypto settles instantly."""
        return 0  # T+0
