"""
Zerodha adapter - Phase 0 stub.

Will be fully implemented in Phase 1.
For now, provides enough interface compliance to not break tests.
"""

import logging
from typing import Optional, Dict

from broker.adapter import BrokerAdapter, OrderResult, OrderStatus
from datetime import datetime

logger = logging.getLogger(__name__)


class ZerodhaAdapter(BrokerAdapter):
    """Zerodha adapter (stub for Phase 0)."""
    
    def __init__(self, paper_mode: bool = True):
        """Initialize Zerodha adapter."""
        self.paper_mode = paper_mode
        self.mode = "paper" if paper_mode else "live"
        logger.info(f"ZerodhaAdapter initialized (mode={self.mode})")
    
    @property
    def is_paper_trading(self) -> bool:
        """Check if in paper trading mode."""
        return self.paper_mode
    
    @property
    def account_equity(self) -> float:
        """Get account equity (stub)."""
        raise NotImplementedError("Zerodha adapter not implemented in Phase 0")
    
    @property
    def buying_power(self) -> float:
        """Get buying power (stub)."""
        raise NotImplementedError("Zerodha adapter not implemented in Phase 0")
    
    def submit_market_order(self, symbol: str, quantity: float, side: str, time_in_force: str = "opg") -> OrderResult:
        """Submit market order (stub)."""
        raise NotImplementedError("Zerodha adapter not implemented in Phase 0")
    
    def get_order_status(self, order_id: str) -> OrderResult:
        """Get order status (stub)."""
        raise NotImplementedError("Zerodha adapter not implemented in Phase 0")
    
    def get_positions(self) -> Dict:
        """Get all positions (stub)."""
        raise NotImplementedError("Zerodha adapter not implemented in Phase 0")
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position (stub)."""
        raise NotImplementedError("Zerodha adapter not implemented in Phase 0")
    
    def close_position(self, symbol: str) -> OrderResult:
        """Close position (stub)."""
        raise NotImplementedError("Zerodha adapter not implemented in Phase 0")
    
    def get_market_hours(self, date: datetime) -> tuple:
        """Get market hours (stub)."""
        raise NotImplementedError("Zerodha adapter not implemented in Phase 0")
    
    def is_market_open(self) -> bool:
        """Check if market is open (stub)."""
        raise NotImplementedError("Zerodha adapter not implemented in Phase 0")
