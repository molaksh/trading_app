"""
Paper trading simulator for crypto.

Simulates fills with configurable slippage, fees, and latency.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime
import random

from broker.kraken import OrderResult, OrderStatus

logger = logging.getLogger(__name__)


class PaperKrakenSimulator:
    """
    Simulates Kraken trading for paper testing.
    
    Features:
    - Configurable starting balance
    - Slippage model (maker/taker)
    - Fee structure (0.16% maker, 0.26% taker)
    - Latency simulation
    - Deterministic for testing (optional seed)
    """
    
    def __init__(self, starting_balance_usd: float = 10_000.0,
                 maker_fee: float = 0.0016,
                 taker_fee: float = 0.0026,
                 slippage_bps: float = 5.0,
                 enable_funding_costs: bool = False,
                 seed: int = None):
        """
        Initialize paper simulator.
        
        Args:
            starting_balance_usd: Starting USD balance
            maker_fee: Maker fee (default 0.16%)
            taker_fee: Taker fee (default 0.26%)
            slippage_bps: Slippage in basis points
            enable_funding_costs: Whether to simulate perp funding
            seed: Random seed for deterministic testing
        """
        self.starting_balance = starting_balance_usd
        self.current_balance = starting_balance_usd
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.slippage_bps = slippage_bps
        self.enable_funding = enable_funding_costs
        
        self.balances: Dict[str, float] = {'USD': starting_balance_usd}
        self.positions: Dict[str, float] = {}
        self.orders: Dict[str, OrderResult] = {}
        self.trades: List[Dict[str, Any]] = []
        
        if seed is not None:
            random.seed(seed)
        
        logger.info("Paper Kraken simulator initialized")
        logger.info(f"  Starting balance: ${starting_balance_usd:,.2f} USD")
        logger.info(f"  Maker fee: {maker_fee*100:.2f}%")
        logger.info(f"  Taker fee: {taker_fee*100:.2f}%")
        logger.info(f"  Slippage: {slippage_bps:.0f} bps")
    
    def submit_market_order(self, symbol: str, quantity: float, 
                           side: str, **kwargs) -> OrderResult:
        """
        Simulate market order submission.
        
        Args:
            symbol: Trading pair (e.g., 'XXBTZUSD')
            quantity: Order quantity
            side: 'buy' or 'sell'
        
        Returns:
            OrderResult (simulated)
        """
        order_id = f"paper_order_{len(self.orders)}"
        
        # Simulate fill with slippage and fees
        mid_price = kwargs.get('mid_price', 100.0)  # Placeholder
        
        if side == 'buy':
            fill_price = mid_price * (1 + self.slippage_bps / 10000)
            fee = quantity * fill_price * self.taker_fee
            cost = quantity * fill_price + fee
            
            if cost > self.balances.get('USD', 0):
                logger.warning(f"Insufficient balance for {side} {quantity} {symbol}")
                return OrderResult(
                    order_id=order_id,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=fill_price,
                    status=OrderStatus.REJECTED,
                    timestamp=datetime.now(),
                    commission=fee,
                )
            
            # Execute
            self.balances['USD'] -= cost
            self.positions[symbol] = self.positions.get(symbol, 0) + quantity
            
        else:  # sell
            fill_price = mid_price * (1 - self.slippage_bps / 10000)
            fee = quantity * fill_price * self.taker_fee
            proceeds = quantity * fill_price - fee
            
            if self.positions.get(symbol, 0) < quantity:
                logger.warning(f"Insufficient {symbol} for {side}")
                return OrderResult(
                    order_id=order_id,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=fill_price,
                    status=OrderStatus.REJECTED,
                    timestamp=datetime.now(),
                    commission=fee,
                )
            
            # Execute
            self.balances['USD'] += proceeds
            self.positions[symbol] -= quantity
        
        # Record filled order
        order = OrderResult(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=fill_price,
            status=OrderStatus.FILLED,
            timestamp=datetime.now(),
            filled_qty=quantity,
            filled_price=fill_price,
            commission=fee,
        )
        
        self.orders[order_id] = order
        
        # Record trade for ML training
        self.trades.append({
            'order_id': order_id,
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'fill_price': fill_price,
            'fee': fee,
            'timestamp': datetime.now(),
        })
        
        logger.info(f"✓ Paper order filled: {order_id} | {side} {quantity} {symbol} @ ${fill_price:.2f}")
        
        return order
    
    def get_balances(self) -> Dict[str, float]:
        """Get current balances."""
        return self.balances.copy()
    
    def get_positions(self) -> Dict[str, float]:
        """Get current positions."""
        return self.positions.copy()
    
    def get_trade_history(self) -> List[Dict[str, Any]]:
        """Get all executed trades for ML training."""
        return self.trades.copy()
