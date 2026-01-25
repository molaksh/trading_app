"""
Abstract broker adapter interface.

Defines contracts for broker integration without tying to specific broker.
All implementations must support:
- Market orders at market open only
- Order status polling
- Position queries
- Paper-trading only mode
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List
from datetime import datetime


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "pending"           # Order submitted, awaiting fill
    FILLED = "filled"             # Order filled completely
    PARTIAL = "partial_filled"    # Partially filled
    REJECTED = "rejected"         # Order rejected by broker
    CANCELLED = "cancelled"       # Order cancelled
    EXPIRED = "expired"           # Order expired


@dataclass
class OrderResult:
    """Result of an order submission or query."""
    order_id: str
    symbol: str
    side: str                      # "buy" or "sell"
    quantity: float
    status: OrderStatus
    filled_qty: float
    filled_price: Optional[float]
    submit_time: datetime
    fill_time: Optional[datetime]
    rejection_reason: Optional[str] = None
    
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.status == OrderStatus.FILLED
    
    def is_pending(self) -> bool:
        """Check if order is still pending."""
        return self.status in (OrderStatus.PENDING, OrderStatus.PARTIAL)
    
    def __repr__(self) -> str:
        if self.is_filled():
            return (
                f"Order {self.order_id}: {self.side.upper()} {self.quantity} "
                f"{self.symbol} @ {self.filled_price:.2f} ({self.status.value})"
            )
        elif self.is_pending():
            return (
                f"Order {self.order_id}: {self.side.upper()} {self.quantity} "
                f"{self.symbol} - {self.filled_qty} filled ({self.status.value})"
            )
        else:
            reason = f" - {self.rejection_reason}" if self.rejection_reason else ""
            return (
                f"Order {self.order_id}: {self.side.upper()} {self.quantity} "
                f"{self.symbol} ({self.status.value}){reason}"
            )


@dataclass
class Position:
    """Current position for a symbol."""
    symbol: str
    quantity: float                # Positive for long, negative for short
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.quantity > 0
    
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.quantity < 0
    
    def __repr__(self) -> str:
        direction = "LONG" if self.is_long() else "SHORT"
        return (
            f"{direction} {abs(self.quantity)} {self.symbol} "
            f"@ {self.avg_entry_price:.2f} "
            f"(current: {self.current_price:.2f}, "
            f"PnL: {self.unrealized_pnl_pct:+.2%})"
        )


class BrokerAdapter(ABC):
    """
    Abstract interface for broker integration.
    
    Implementations must:
    1. Support paper trading ONLY (safety first)
    2. Enforce market orders at market open only
    3. Provide order status polling
    4. Enable position queries
    5. Fail loudly on configuration errors
    """
    
    @property
    @abstractmethod
    def is_paper_trading(self) -> bool:
        """
        Check if adapter is in paper trading mode.
        
        Must always return True. Raise exception if live trading is detected.
        
        Returns:
            True (always)
            
        Raises:
            RuntimeError: If live trading is detected
        """
        pass
    
    @property
    @abstractmethod
    def account_equity(self) -> float:
        """
        Get current account equity in USD.
        
        Returns:
            Account equity as float
        """
        pass
    
    @property
    @abstractmethod
    def buying_power(self) -> float:
        """
        Get current available buying power in USD.
        
        Returns:
            Buying power as float
        """
        pass
    
    @abstractmethod
    def submit_market_order(
        self,
        symbol: str,
        quantity: float,
        side: str,
        time_in_force: str = "opg",  # "opg" = at market open
    ) -> OrderResult:
        """
        Submit a market order at market open.
        
        For swing trading, orders should be submitted before market open
        to execute at next day's open price.
        
        Args:
            symbol: Ticker symbol
            quantity: Number of shares
            side: "buy" or "sell"
            time_in_force: Order duration ("opg" for market open)
        
        Returns:
            OrderResult with order status
            
        Raises:
            ValueError: If quantity is invalid or side is not buy/sell
            RuntimeError: If broker is in live trading mode
        """
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderResult:
        """
        Query status of a submitted order.
        
        Args:
            order_id: Order identifier returned by submit_market_order
        
        Returns:
            OrderResult with current status
            
        Raises:
            ValueError: If order_id is invalid
        """
        pass
    
    @abstractmethod
    def get_positions(self) -> Dict[str, Position]:
        """
        Get all current open positions.
        
        Returns:
            Dict mapping symbol -> Position
        """
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get position for specific symbol.
        
        Args:
            symbol: Ticker symbol
        
        Returns:
            Position if held, else None
        """
        pass
    
    @abstractmethod
    def close_position(self, symbol: str) -> OrderResult:
        """
        Close position for symbol (sell all if long, buy all if short).
        
        Args:
            symbol: Ticker symbol
        
        Returns:
            OrderResult for the close order
            
        Raises:
            ValueError: If position doesn't exist
        """
        pass
    
    @abstractmethod
    def get_market_hours(self, date: datetime) -> tuple[datetime, datetime]:
        """
        Get market open and close times for a specific date.
        
        Args:
            date: Date to check
        
        Returns:
            Tuple of (market_open, market_close) as datetime
            
        Raises:
            ValueError: If market is closed on that date
        """
        pass
    
    @abstractmethod
    def is_market_open(self) -> bool:
        """
        Check if market is currently open.
        
        Returns:
            True if market is open, False otherwise
        """
        pass
