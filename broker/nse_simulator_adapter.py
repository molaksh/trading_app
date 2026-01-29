"""
NSE Simulated Broker Adapter for India Paper Trading.

This adapter acts as the SOURCE OF TRUTH for India paper trading:
- Maintains in-memory + persisted positions
- Simulates realistic order execution
- Tracks account balance and buying power
- Persists broker state across restarts

Execution Model:
- Orders placed before close execute at next-day open
- Slippage: ±0.05%-0.15% randomized
- Brokerage: ₹20 flat per order
- Full fills only (v1)

State Persistence:
- state/<scope>/broker_state.json
"""

import logging
import json
import random
from typing import Optional, Dict, List
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict

from broker.adapter import BrokerAdapter, OrderStatus, OrderResult, Position
from config.scope import get_scope
from config.scope_paths import get_scope_path

logger = logging.getLogger(__name__)


@dataclass
class SimulatedPosition:
    """Simulated position state."""
    symbol: str
    quantity: float
    avg_entry_price: float
    entry_date: str
    total_cost: float  # Including brokerage


@dataclass
class SimulatedOrder:
    """Simulated order state."""
    order_id: str
    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    status: str  # "pending", "filled", "cancelled"
    submit_time: str
    fill_time: Optional[str] = None
    fill_price: Optional[float] = None
    slippage_pct: Optional[float] = None


@dataclass
class BrokerState:
    """Persistent broker state."""
    account_equity: float
    cash: float
    positions: Dict[str, dict]  # symbol -> position dict
    pending_orders: List[dict]  # list of order dicts
    filled_orders: List[dict]
    last_update: str


class NSESimulatedBrokerAdapter(BrokerAdapter):
    """
    Simulated broker adapter for NSE India paper trading.
    
    Acts as source of truth for:
    - Account balance
    - Open positions
    - Order execution
    - Trade history
    
    Configuration:
    - Starting capital: ₹10,00,000 (10 lakhs)
    - Brokerage: ₹20 per order
    - Slippage: 0.05% - 0.15% random
    """
    
    # Configuration
    STARTING_CAPITAL = 1_000_000.0  # ₹10 lakhs
    BROKERAGE_PER_ORDER = 20.0  # ₹20 flat
    MIN_SLIPPAGE_PCT = 0.05  # 0.05%
    MAX_SLIPPAGE_PCT = 0.15  # 0.15%
    
    def __init__(self, state_dir: Optional[Path] = None):
        """
        Initialize NSE simulator.
        
        Args:
            state_dir: Directory for broker state persistence
        """
        if state_dir is None:
            scope = get_scope()
            state_dir = get_scope_path(scope, "state")

        self.state_dir = Path(state_dir)
        self.state_file = state_dir / "broker_state.json"
        
        # In-memory state
        self.account_equity = self.STARTING_CAPITAL
        self.cash = self.STARTING_CAPITAL
        self.positions: Dict[str, SimulatedPosition] = {}
        self.pending_orders: List[SimulatedOrder] = []
        self.filled_orders: List[SimulatedOrder] = []
        
        # Load persisted state if exists
        self._load_state()
        
        logger.info("=" * 80)
        logger.info("NSE SIMULATED BROKER ADAPTER INITIALIZED")
        logger.info("=" * 80)
        logger.info(f"Starting Capital: ₹{self.STARTING_CAPITAL:,.2f}")
        logger.info(f"Brokerage: ₹{self.BROKERAGE_PER_ORDER} per order")
        logger.info(f"Slippage Range: {self.MIN_SLIPPAGE_PCT}% - {self.MAX_SLIPPAGE_PCT}%")
        logger.info(f"State File: {self.state_file}")
        logger.info(f"Current Equity: ₹{self.account_equity:,.2f}")
        logger.info(f"Current Cash: ₹{self.cash:,.2f}")
        logger.info(f"Open Positions: {len(self.positions)}")
        logger.info(f"Pending Orders: {len(self.pending_orders)}")
        logger.info("=" * 80)
    
    @property
    def client(self) -> Optional[object]:
        """
        Broker API client.
        
        For NSE simulator, return None to indicate no external API.
        Scheduler checks this for mock mode compatibility.
        """
        return None
    
    def _load_state(self) -> None:
        """Load broker state from disk."""
        if not self.state_file.exists():
            logger.info("No existing broker state - starting fresh")
            return
        
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            
            state = BrokerState(**data)
            
            self.account_equity = state.account_equity
            self.cash = state.cash
            
            # Restore positions
            self.positions = {
                symbol: SimulatedPosition(**pos_dict)
                for symbol, pos_dict in state.positions.items()
            }
            
            # Restore orders
            self.pending_orders = [
                SimulatedOrder(**order_dict)
                for order_dict in state.pending_orders
            ]
            self.filled_orders = [
                SimulatedOrder(**order_dict)
                for order_dict in state.filled_orders
            ]
            
            logger.info(f"Loaded broker state from {self.state_file}")
            logger.info(f"  Equity: ₹{self.account_equity:,.2f}")
            logger.info(f"  Positions: {len(self.positions)}")
            logger.info(f"  Pending: {len(self.pending_orders)}")
            
        except Exception as e:
            logger.error(f"Failed to load broker state: {e}")
            logger.warning("Starting with fresh state")
    
    def _save_state(self) -> None:
        """Persist broker state to disk."""
        try:
            state = BrokerState(
                account_equity=self.account_equity,
                cash=self.cash,
                positions={
                    symbol: asdict(pos)
                    for symbol, pos in self.positions.items()
                },
                pending_orders=[asdict(order) for order in self.pending_orders],
                filled_orders=[asdict(order) for order in self.filled_orders],
                last_update=datetime.now(timezone.utc).isoformat()
            )
            
            self.state_dir.mkdir(parents=True, exist_ok=True)
            
            with open(self.state_file, 'w') as f:
                json.dump(asdict(state), f, indent=2)
            
            logger.debug(f"Saved broker state to {self.state_file}")
            
        except Exception as e:
            logger.error(f"Failed to save broker state: {e}")
    
    def _generate_slippage(self, side: str) -> float:
        """
        Generate realistic slippage percentage.
        
        Args:
            side: "buy" or "sell"
        
        Returns:
            Slippage percentage (positive for buy, negative for sell)
        """
        slippage_pct = random.uniform(self.MIN_SLIPPAGE_PCT, self.MAX_SLIPPAGE_PCT)
        
        # Buy orders slip up, sell orders slip down
        if side.lower() == "buy":
            return slippage_pct
        else:
            return -slippage_pct
    
    @property
    def is_paper_trading(self) -> bool:
        """Always returns True for simulator."""
        return True
    
    @property
    def account_equity(self) -> float:
        """Get current account equity (cash + positions value)."""
        return self._account_equity
    
    @account_equity.setter
    def account_equity(self, value: float) -> None:
        """Set account equity."""
        self._account_equity = value
    
    @property
    def buying_power(self) -> float:
        """Get available buying power (cash)."""
        return self.cash
    
    def submit_market_order(
        self,
        symbol: str,
        quantity: float,
        side: str,
        time_in_force: str = "day",
    ) -> OrderResult:
        """
        Submit a market order for next-day execution.
        
        Orders submitted before close will execute at next open with:
        - Simulated slippage
        - Brokerage charges
        
        Args:
            symbol: NSE symbol (e.g., "RELIANCE", "TCS")
            quantity: Number of shares
            side: "buy" or "sell"
            time_in_force: Ignored for simulator
        
        Returns:
            OrderResult with pending status
        """
        # Validate inputs
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"Invalid symbol: {symbol}")
        
        if quantity <= 0:
            raise ValueError(f"Quantity must be positive: {quantity}")
        
        if side.lower() not in ("buy", "sell"):
            raise ValueError(f"Side must be 'buy' or 'sell': {side}")
        
        # Generate order ID
        order_id = f"NSE-{symbol}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Create pending order
        order = SimulatedOrder(
            order_id=order_id,
            symbol=symbol.upper(),
            side=side.lower(),
            quantity=quantity,
            status="pending",
            submit_time=datetime.now(timezone.utc).isoformat()
        )
        
        self.pending_orders.append(order)
        self._save_state()
        
        logger.info(f"Order submitted: {order_id} | {side.upper()} {quantity} {symbol}")
        
        return OrderResult(
            order_id=order_id,
            symbol=symbol.upper(),
            side=side.lower(),
            quantity=quantity,
            status=OrderStatus.PENDING,
            timestamp=datetime.now(timezone.utc),
            filled_quantity=0.0,
            filled_price=None,
            avg_fill_price=None,
        )
    
    def execute_pending_orders(self, market_prices: Dict[str, float]) -> List[OrderResult]:
        """
        Execute all pending orders at market open.
        
        This should be called by the scheduler at market open with
        current market prices.
        
        Args:
            market_prices: Dict of symbol -> open price
        
        Returns:
            List of OrderResult for filled orders
        """
        if not self.pending_orders:
            return []
        
        filled_results = []
        
        for order in self.pending_orders[:]:  # Copy to allow modification
            if order.symbol not in market_prices:
                logger.warning(f"No price data for {order.symbol} - order remains pending")
                continue
            
            # Get market price and apply slippage
            market_price = market_prices[order.symbol]
            slippage_pct = self._generate_slippage(order.side)
            fill_price = market_price * (1 + slippage_pct / 100)
            
            # Calculate costs
            gross_value = fill_price * order.quantity
            brokerage = self.BROKERAGE_PER_ORDER
            total_cost = gross_value + brokerage
            
            # Execute based on side
            if order.side == "buy":
                # Check sufficient cash
                if total_cost > self.cash:
                    logger.error(
                        f"Insufficient cash for {order.order_id}: "
                        f"need ₹{total_cost:.2f}, have ₹{self.cash:.2f}"
                    )
                    order.status = "rejected"
                    continue
                
                # Deduct cash
                self.cash -= total_cost
                
                # Add/update position
                if order.symbol in self.positions:
                    pos = self.positions[order.symbol]
                    total_qty = pos.quantity + order.quantity
                    total_cost_cum = pos.total_cost + total_cost
                    pos.quantity = total_qty
                    pos.avg_entry_price = (total_cost_cum - brokerage) / total_qty
                    pos.total_cost = total_cost_cum
                else:
                    self.positions[order.symbol] = SimulatedPosition(
                        symbol=order.symbol,
                        quantity=order.quantity,
                        avg_entry_price=fill_price,
                        entry_date=datetime.now(timezone.utc).isoformat(),
                        total_cost=total_cost
                    )
                
                logger.info(
                    f"BUY FILLED: {order.symbol} | {order.quantity} @ ₹{fill_price:.2f} "
                    f"(slippage: {slippage_pct:+.2f}%) | Cost: ₹{total_cost:.2f}"
                )
            
            else:  # sell
                # Check position exists
                if order.symbol not in self.positions:
                    logger.error(f"No position to sell: {order.symbol}")
                    order.status = "rejected"
                    continue
                
                pos = self.positions[order.symbol]
                
                # Check sufficient quantity
                if order.quantity > pos.quantity:
                    logger.error(
                        f"Insufficient quantity for {order.symbol}: "
                        f"need {order.quantity}, have {pos.quantity}"
                    )
                    order.status = "rejected"
                    continue
                
                # Add cash (net of brokerage)
                net_proceeds = gross_value - brokerage
                self.cash += net_proceeds
                
                # Update/remove position
                if order.quantity == pos.quantity:
                    del self.positions[order.symbol]
                else:
                    pos.quantity -= order.quantity
                    # Pro-rata cost reduction
                    pos.total_cost *= (pos.quantity / (pos.quantity + order.quantity))
                
                logger.info(
                    f"SELL FILLED: {order.symbol} | {order.quantity} @ ₹{fill_price:.2f} "
                    f"(slippage: {slippage_pct:+.2f}%) | Proceeds: ₹{net_proceeds:.2f}"
                )
            
            # Update order
            order.status = "filled"
            order.fill_time = datetime.now(timezone.utc).isoformat()
            order.fill_price = fill_price
            order.slippage_pct = slippage_pct
            
            self.filled_orders.append(order)
            
            # Create result
            filled_results.append(OrderResult(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                status=OrderStatus.FILLED,
                timestamp=datetime.fromisoformat(order.fill_time),
                filled_quantity=order.quantity,
                filled_price=fill_price,
                avg_fill_price=fill_price,
            ))
        
        # Remove filled/rejected orders from pending
        self.pending_orders = [
            o for o in self.pending_orders
            if o.status == "pending"
        ]
        
        # Recalculate equity
        positions_value = sum(
            pos.quantity * market_prices.get(pos.symbol, pos.avg_entry_price)
            for pos in self.positions.values()
        )
        self.account_equity = self.cash + positions_value
        
        # Persist state
        self._save_state()
        
        logger.info(f"Executed {len(filled_results)} orders | Equity: ₹{self.account_equity:,.2f}")
        
        return filled_results
    
    def get_order_status(self, order_id: str) -> OrderResult:
        """Get order status by ID."""
        # Check filled orders
        for order in self.filled_orders:
            if order.order_id == order_id:
                return OrderResult(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=order.quantity,
                    status=OrderStatus.FILLED,
                    timestamp=datetime.fromisoformat(order.submit_time),
                    filled_quantity=order.quantity,
                    filled_price=order.fill_price,
                    avg_fill_price=order.fill_price,
                )
        
        # Check pending orders
        for order in self.pending_orders:
            if order.order_id == order_id:
                return OrderResult(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=order.quantity,
                    status=OrderStatus.PENDING,
                    timestamp=datetime.fromisoformat(order.submit_time),
                    filled_quantity=0.0,
                    filled_price=None,
                    avg_fill_price=None,
                )
        
        raise ValueError(f"Order not found: {order_id}")
    
    def get_positions(self) -> Dict[str, Position]:
        """Get all open positions."""
        # TODO: Need current market prices for unrealized P&L
        # For now, use entry price
        return {
            symbol: Position(
                symbol=symbol,
                quantity=pos.quantity,
                avg_entry_price=pos.avg_entry_price,
                current_price=pos.avg_entry_price,  # Placeholder
                unrealized_pnl=0.0,  # Placeholder
                unrealized_pnl_pct=0.0,  # Placeholder
            )
            for symbol, pos in self.positions.items()
        }
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol."""
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]
        return Position(
            symbol=symbol,
            quantity=pos.quantity,
            avg_entry_price=pos.avg_entry_price,
            current_price=pos.avg_entry_price,  # Placeholder
            unrealized_pnl=0.0,  # Placeholder
            unrealized_pnl_pct=0.0,  # Placeholder
        )
    
    def close_position(self, symbol: str) -> OrderResult:
        """Submit order to close a position."""
        position = self.get_position(symbol)
        if not position:
            raise ValueError(f"No position found for {symbol}")
        
        return self.submit_market_order(
            symbol=symbol,
            quantity=abs(position.quantity),
            side="sell" if position.is_long() else "buy",
            time_in_force="day"
        )
    
    def get_market_hours(self, date: datetime) -> tuple[datetime, datetime]:
        """
        Get NSE market hours for a specific date.
        
        Args:
            date: Date to check (any timezone)
        
        Returns:
            Tuple of (market_open, market_close) as datetime in IST
            
        Raises:
            ValueError: If market is closed on that date
        """
        from zoneinfo import ZoneInfo
        from policies.market_hours.india_equity_market_hours import IndiaEquityMarketHours
        
        market_hours_policy = IndiaEquityMarketHours()
        
        # Check if trading day
        if not market_hours_policy.is_trading_day(date):
            raise ValueError(f"Market is closed on {date.date()}")
        
        # Get market open and close times
        market_open = market_hours_policy.get_market_open(date)
        market_close = market_hours_policy.get_market_close(date)
        
        return (market_open, market_close)
    
    def is_market_open(self) -> bool:
        """
        Check if NSE market is open.
        
        Note: This is a simplified check. Real implementation
        should use market hours policy.
        """
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        
        # Monday-Friday only
        if now.weekday() >= 5:
            return False
        
        # 9:15 AM - 3:30 PM IST
        market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        return market_start <= now <= market_end
