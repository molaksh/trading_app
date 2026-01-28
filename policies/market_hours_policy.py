"""
Market hours policy implementations for different markets.

Defines market timezone, open/close times, and 24x7 vs regular markets:
- US Equity: 9:30 AM - 4:00 PM ET, Mon-Fri
- India Equity: 9:15 AM - 3:30 PM IST, Mon-Fri
- Crypto: 24x7 operation
"""

import logging
from datetime import time
from policies.base import MarketHoursPolicy

logger = logging.getLogger(__name__)


class USEquityMarketHours(MarketHoursPolicy):
    """
    Market hours policy for US equity markets.
    
    Characteristics:
    - Timezone: America/New_York (Eastern Time)
    - Open: 9:30 AM ET
    - Close: 4:00 PM ET
    - Trading days: Monday-Friday
    - No 24x7 operation
    """
    
    TIMEZONE = "America/New_York"
    MARKET_OPEN = time(9, 30)   # 9:30 AM ET
    MARKET_CLOSE = time(16, 0)  # 4:00 PM ET
    
    def get_timezone(self) -> str:
        return self.TIMEZONE
    
    def get_market_open_time(self) -> time:
        return self.MARKET_OPEN
    
    def get_market_close_time(self) -> time:
        return self.MARKET_CLOSE
    
    def is_24x7_market(self) -> bool:
        return False
    
    def has_market_close(self) -> bool:
        return True
    
    def get_name(self) -> str:
        return "USEquityMarketHours"


class IndiaEquityMarketHours(MarketHoursPolicy):
    """
    Market hours policy for India equity markets (NOT IMPLEMENTED).
    
    Future characteristics:
    - Timezone: Asia/Kolkata (Indian Standard Time)
    - Open: 9:15 AM IST
    - Close: 3:30 PM IST
    - Trading days: Monday-Friday
    """
    
    def get_timezone(self) -> str:
        raise NotImplementedError(
            "IndiaEquityMarketHours not implemented. "
            "India market is not supported. "
            "Required implementation: timezone='Asia/Kolkata'"
        )
    
    def get_market_open_time(self) -> time:
        raise NotImplementedError(
            "IndiaEquityMarketHours not implemented. "
            "India market is not supported. "
            "Required implementation: open=time(9, 15) (9:15 AM IST)"
        )
    
    def get_market_close_time(self) -> time:
        raise NotImplementedError(
            "IndiaEquityMarketHours not implemented. "
            "India market is not supported. "
            "Required implementation: close=time(15, 30) (3:30 PM IST)"
        )
    
    def is_24x7_market(self) -> bool:
        raise NotImplementedError(
            "IndiaEquityMarketHours not implemented. "
            "India market is not supported. "
            "Required implementation: is_24x7_market=False"
        )
    
    def has_market_close(self) -> bool:
        raise NotImplementedError(
            "IndiaEquityMarketHours not implemented. "
            "India market is not supported. "
            "Required implementation: has_market_close=True"
        )
    
    def get_name(self) -> str:
        return "IndiaEquityMarketHours (NOT IMPLEMENTED)"


class Crypto24x7MarketHours(MarketHoursPolicy):
    """
    Market hours policy for 24x7 cryptocurrency markets (NOT IMPLEMENTED).
    
    Future characteristics:
    - Timezone: UTC (universal)
    - Open: N/A (always open)
    - Close: N/A (no daily close)
    - Trading: 24 hours, 7 days a week
    """
    
    def get_timezone(self) -> str:
        raise NotImplementedError(
            "Crypto24x7MarketHours not implemented. "
            "Crypto market is not supported. "
            "Required implementation: timezone='UTC'"
        )
    
    def get_market_open_time(self) -> time:
        raise NotImplementedError(
            "Crypto24x7MarketHours not implemented. "
            "Crypto market is not supported. "
            "Required implementation: return time(0, 0) (always open)"
        )
    
    def get_market_close_time(self) -> time:
        raise NotImplementedError(
            "Crypto24x7MarketHours not implemented. "
            "Crypto market is not supported. "
            "Required implementation: return time(0, 0) (no close)"
        )
    
    def is_24x7_market(self) -> bool:
        raise NotImplementedError(
            "Crypto24x7MarketHours not implemented. "
            "Crypto market is not supported. "
            "Required implementation: is_24x7_market=True"
        )
    
    def has_market_close(self) -> bool:
        raise NotImplementedError(
            "Crypto24x7MarketHours not implemented. "
            "Crypto market is not supported. "
            "Required implementation: has_market_close=False"
        )
    
    def get_name(self) -> str:
        return "Crypto24x7MarketHours (NOT IMPLEMENTED)"
