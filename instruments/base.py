"""
Instrument Interface - Defines behavior for different asset types.

Instruments define:
- Trading rules (lot sizes, tick sizes)
- Margin requirements
- Settlement cycles
- Order types supported
- Risk calculations

Markets define:
- Regulatory rules (PDT, margin requirements)
- Trading hours
- Holidays
- Settlement rules
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from decimal import Decimal


@dataclass
class InstrumentSpec:
    """Specification for an instrument."""
    symbol: str
    instrument_type: str        # equity, option, crypto, futures, etc.
    lot_size: int = 1          # Minimum tradable quantity
    tick_size: Decimal = Decimal("0.01")  # Minimum price increment
    margin_required_pct: float = 1.0      # 1.0 = 100% (cash), 0.5 = 50% (2x leverage)
    settlement_days: int = 0               # T+0, T+1, T+2, etc.
    tradable: bool = True
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class Instrument(ABC):
    """
    Base interface for all instrument types.
    
    RESPONSIBILITIES:
    - Validate order parameters
    - Calculate position value
    - Calculate margin requirement
    - Normalize quantity (lot sizes)
    """
    
    def __init__(self, spec: InstrumentSpec):
        """
        Initialize instrument.
        
        Args:
            spec: Instrument specification
        """
        self.spec = spec
    
    @abstractmethod
    def validate_quantity(self, quantity: int) -> tuple[bool, str]:
        """
        Validate if quantity meets instrument requirements.
        
        Args:
            quantity: Proposed trade quantity
        
        Returns:
            (is_valid, error_message)
        """
        pass
    
    @abstractmethod
    def calculate_position_value(
        self,
        quantity: int,
        price: float,
    ) -> float:
        """
        Calculate total position value.
        
        Args:
            quantity: Number of units
            price: Price per unit
        
        Returns:
            Total value in currency
        """
        pass
    
    @abstractmethod
    def calculate_margin_required(
        self,
        quantity: int,
        price: float,
    ) -> float:
        """
        Calculate margin required to open position.
        
        Args:
            quantity: Number of units
            price: Price per unit
        
        Returns:
            Margin required in currency
        """
        pass
    
    @abstractmethod
    def get_supported_order_types(self) -> List[str]:
        """Return list of supported order types for this instrument."""
        pass
    
    def normalize_quantity(self, quantity: int) -> int:
        """
        Normalize quantity to valid lot size.
        
        Args:
            quantity: Raw quantity
        
        Returns:
            Normalized quantity (rounded down to lot size)
        """
        lot_size = self.spec.lot_size
        return (quantity // lot_size) * lot_size
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.spec.symbol})"


class EquityInstrument(Instrument):
    """
    Equity (stock) instrument.
    
    CHARACTERISTICS:
    - Lot size: 1 (US), can be 10/25/50 (India)
    - Settlement: T+2 (US), T+1 (India moving to T+0)
    - Margin: 100% (cash), 50% (margin)
    - Order types: Market, Limit, Stop, Stop-Limit
    """
    
    def __init__(self, symbol: str, lot_size: int = 1, margin_pct: float = 1.0):
        """
        Initialize equity instrument.
        
        Args:
            symbol: Stock ticker
            lot_size: Minimum tradable quantity (1 for US, varies for India)
            margin_pct: Margin requirement (1.0 = cash, 0.5 = 2x margin)
        """
        spec = InstrumentSpec(
            symbol=symbol,
            instrument_type="equity",
            lot_size=lot_size,
            tick_size=Decimal("0.01"),
            margin_required_pct=margin_pct,
            settlement_days=2,  # T+2 for US
            tradable=True,
        )
        super().__init__(spec)
    
    def validate_quantity(self, quantity: int) -> tuple[bool, str]:
        """Validate equity quantity."""
        if quantity <= 0:
            return False, "Quantity must be positive"
        
        if quantity % self.spec.lot_size != 0:
            return False, f"Quantity must be multiple of lot size ({self.spec.lot_size})"
        
        return True, ""
    
    def calculate_position_value(self, quantity: int, price: float) -> float:
        """Calculate total equity position value."""
        return quantity * price
    
    def calculate_margin_required(self, quantity: int, price: float) -> float:
        """Calculate margin for equity."""
        position_value = self.calculate_position_value(quantity, price)
        return position_value * self.spec.margin_required_pct
    
    def get_supported_order_types(self) -> List[str]:
        """Equity supports all standard order types."""
        return ["market", "limit", "stop", "stop_limit"]


class OptionInstrument(Instrument):
    """
    Option contract instrument.
    
    CHARACTERISTICS:
    - Lot size: 1 contract = 100 shares (US)
    - Settlement: T+1
    - Margin: Complex (depends on strategy type)
    - Order types: Market, Limit (no stops on many platforms)
    """
    
    def __init__(
        self,
        symbol: str,
        strike: float,
        expiry: str,
        option_type: str,  # "call" or "put"
        multiplier: int = 100,
    ):
        """
        Initialize option instrument.
        
        Args:
            symbol: Underlying symbol
            strike: Strike price
            expiry: Expiration date
            option_type: "call" or "put"
            multiplier: Contract multiplier (100 for US equities)
        """
        spec = InstrumentSpec(
            symbol=symbol,
            instrument_type="option",
            lot_size=1,  # 1 contract
            tick_size=Decimal("0.01"),
            margin_required_pct=1.0,  # Simplified; real calc is complex
            settlement_days=1,  # T+1
            tradable=True,
            metadata={
                "strike": strike,
                "expiry": expiry,
                "option_type": option_type,
                "multiplier": multiplier,
            }
        )
        super().__init__(spec)
    
    def validate_quantity(self, quantity: int) -> tuple[bool, str]:
        """Validate option contract quantity."""
        if quantity <= 0:
            return False, "Quantity must be positive"
        
        # Options trade in whole contracts
        if quantity % self.spec.lot_size != 0:
            return False, f"Must trade whole contracts"
        
        return True, ""
    
    def calculate_position_value(self, quantity: int, price: float) -> float:
        """Calculate option position value (premium paid/received)."""
        multiplier = self.spec.metadata.get("multiplier", 100)
        return quantity * price * multiplier
    
    def calculate_margin_required(self, quantity: int, price: float) -> float:
        """
        Calculate option margin.
        
        SIMPLIFIED: For buying options, margin = premium paid.
        For selling naked options, margin is much more complex (broker-specific).
        """
        return self.calculate_position_value(quantity, price)
    
    def get_supported_order_types(self) -> List[str]:
        """Options typically support market and limit only."""
        return ["market", "limit"]


class CryptoInstrument(Instrument):
    """
    Cryptocurrency instrument.
    
    CHARACTERISTICS:
    - Lot size: Varies (can be fractional)
    - Settlement: Instant (T+0)
    - Margin: 1x-125x depending on exchange
    - Order types: Market, Limit, Stop-Loss, Take-Profit
    - 24/7 trading
    """
    
    def __init__(
        self,
        symbol: str,
        min_quantity: float = 0.00000001,  # 1 satoshi for BTC
        margin_pct: float = 1.0,
    ):
        """
        Initialize crypto instrument.
        
        Args:
            symbol: Crypto pair (e.g., BTC/USD, ETH/USD)
            min_quantity: Minimum tradable quantity
            margin_pct: Margin requirement (can be < 1.0 for leverage)
        """
        spec = InstrumentSpec(
            symbol=symbol,
            instrument_type="crypto",
            lot_size=1,  # Crypto supports fractional
            tick_size=Decimal("0.01"),
            margin_required_pct=margin_pct,
            settlement_days=0,  # Instant
            tradable=True,
            metadata={"min_quantity": min_quantity}
        )
        super().__init__(spec)
    
    def validate_quantity(self, quantity: int) -> tuple[bool, str]:
        """Validate crypto quantity."""
        min_qty = self.spec.metadata.get("min_quantity", 0.00000001)
        
        if quantity <= 0:
            return False, "Quantity must be positive"
        
        if quantity < min_qty:
            return False, f"Quantity below minimum ({min_qty})"
        
        return True, ""
    
    def calculate_position_value(self, quantity: int, price: float) -> float:
        """Calculate crypto position value."""
        return quantity * price
    
    def calculate_margin_required(self, quantity: int, price: float) -> float:
        """Calculate margin for crypto (can use leverage)."""
        position_value = self.calculate_position_value(quantity, price)
        return position_value * self.spec.margin_required_pct
    
    def get_supported_order_types(self) -> List[str]:
        """Crypto supports rich order types."""
        return ["market", "limit", "stop_loss", "take_profit", "stop_limit"]
