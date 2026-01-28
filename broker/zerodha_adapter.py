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
    
    def submit_order(self, symbol: str, quantity: int, side: str, order_type: str = "market") -> OrderResult:
        """Submit order (stub)."""
        raise NotImplementedError("Zerodha adapter not implemented in Phase 0")
    
    def get_order_status(self, order_id: str) -> OrderResult:
        """Get order status (stub)."""
        raise NotImplementedError("Zerodha adapter not implemented in Phase 0")
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position (stub)."""
        raise NotImplementedError("Zerodha adapter not implemented in Phase 0")
    
    def get_account_equity(self) -> float:
        """Get account equity (stub)."""
        raise NotImplementedError("Zerodha adapter not implemented in Phase 0")
