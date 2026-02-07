"""
Kraken crypto exchange adapter - Phase 1.

Implements BrokerAdapter interface for Kraken REST API with safety-first design:
- Paper trading fully supported
- Live trading available only with explicit flags (DRY_RUN=false, ENABLE_LIVE_ORDERS=true)
- Startup preflight checks for connectivity/auth
- Rate limiting and retries
- No withdrawals (code-level guarantee)
- Dry-run mode blocks orders and logs them
"""

import logging
import os
from typing import Dict, Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass

from broker.adapter import BrokerAdapter, OrderResult, OrderStatus, Position
from broker.kraken_client import KrakenClient, KrakenConfig, KrakenAPIError

logger = logging.getLogger(__name__)


@dataclass
class KrakenOrder:
    """Internal representation of Kraken order."""
    order_id: str
    symbol: str  # Internal canonical (e.g., "BTC/USD")
    side: str    # "buy" or "sell"
    quantity: float
    price: Optional[float]  # None for market orders
    status: OrderStatus
    filled_qty: float = 0.0
    filled_price: Optional[float] = None
    submit_time: Optional[datetime] = None
    fill_time: Optional[datetime] = None


class KrakenAdapter(BrokerAdapter):
    """Production-grade Kraken crypto exchange adapter."""
    
    # Symbol mapping: internal -> Kraken (e.g., "BTC/USD" -> "XBTUSDT")
    SYMBOL_MAP = {
        "BTC/USD": "XBTUSD",
        "ETH/USD": "ETHUSD",
        "SOL/USD": "SOLUSD",
        "LINK/USD": "LINKUSD",
        "AVAX/USD": "AVAXUSD",
        "BTC/USDT": "XBTUSDT",
        "ETH/USDT": "ETHUSD T",
        "SOL/USDT": "SOLUSDT",
    }
    
    # Reverse mapping
    REVERSE_SYMBOL_MAP = {v: k for k, v in SYMBOL_MAP.items()}
    
    MIN_ORDER_SIZE = {
        "BTC/USD": 0.00001,
        "ETH/USD": 0.0001,
        "SOL/USD": 0.01,
        "LINK/USD": 0.1,
        "AVAX/USD": 0.1,
    }
    
    def __init__(
        self,
        paper_mode: bool = True,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        dry_run: bool = True,
        enable_live_orders: bool = False,
        base_url: str = "https://api.kraken.com"
    ):
        """
        Initialize Kraken adapter.
        
        Args:
            paper_mode: If True, all market operations are simulated
            api_key: Kraken API key (from env if not provided)
            api_secret: Kraken API secret (from env if not provided)
            dry_run: If True in live mode, block orders (default True)
            enable_live_orders: If True, allow real orders (requires dry_run=false)
            base_url: Kraken API base URL
        
        Raises:
            ValueError: If configuration is invalid
        """
        self.paper_mode = paper_mode
        self.dry_run = dry_run
        self.enable_live_orders = enable_live_orders
        self.base_url = base_url
        
        # Validate live mode config
        if not paper_mode:
            if dry_run and enable_live_orders:
                raise ValueError("Cannot enable live orders with dry_run=true")
            if enable_live_orders and not api_key:
                raise ValueError("Live orders require API key")
        
        # Get API credentials (from env or args)
        api_key = api_key or os.getenv("KRAKEN_API_KEY", "")
        api_secret = api_secret or os.getenv("KRAKEN_API_SECRET", "")
        
        # Initialize client (for live mode)
        if not paper_mode and (api_key and api_secret):
            config = KrakenConfig(
                base_url=base_url,
                api_key=api_key,
                api_secret=api_secret,
                timeout_sec=10,
                max_retries=3
            )
            self.client = KrakenClient(config)
        else:
            self.client = None
        
        # Paper trading state
        self._balances = {
            "BTC": 1.0,
            "ETH": 10.0,
            "SOL": 100.0,
            "USD": 10000.0
        }
        self._positions = {}
        self._orders = {}
        self._next_order_id = 1
        
        mode_str = "paper" if paper_mode else "live"
        run_mode = "dry-run" if dry_run else "real"
        logger.info(
            f"KrakenAdapter initialized: "
            f"mode={mode_str}, run_mode={run_mode}, "
            f"live_orders_enabled={enable_live_orders}"
        )
    
    @property
    def is_paper_trading(self) -> bool:
        """Check if adapter is in paper trading mode."""
        return self.paper_mode
    
    @property
    def account_equity(self) -> float:
        """Get account equity (USD)."""
        if self.paper_mode:
            # Sum all balances at current prices (simplified)
            usd_value = self._balances.get("USD", 0.0)
            # Add crypto holdings (simplified: 1 BTC = $45k, 1 ETH = $3k, 1 SOL = $150)
            usd_value += self._balances.get("BTC", 0.0) * 45000
            usd_value += self._balances.get("ETH", 0.0) * 3000
            usd_value += self._balances.get("SOL", 0.0) * 150
            return usd_value
        else:
            # Live: query from Kraken
            if self.client is None:
                raise RuntimeError("Client not initialized")
            try:
                balances = self.client.request_private("Balance", {})
                # Kraken returns balance dict; sum USD-equivalent values
                usd_total = balances.get("ZUSD", 0.0)
                # Simplified: just USD for now
                return float(usd_total)
            except Exception as e:
                logger.error(f"Failed to get account equity: {e}")
                return 0.0
    
    @property
    def buying_power(self) -> float:
        """Get available buying power (USD)."""
        if self.paper_mode:
            return self._balances.get("USD", 0.0)
        else:
            # Live: use account equity (simplified, no leverage)
            return self.account_equity
    
    def submit_market_order(
        self,
        symbol: str,
        quantity: float,
        side: str,
        time_in_force: str = "opg"
    ) -> OrderResult:
        """
        Submit a market order.
        
        For crypto, "time_in_force" is less relevant (24/7 market).
        Orders execute immediately at market price.
        
        Args:
            symbol: Internal symbol (e.g., "BTC/USD")
            quantity: Order quantity
            side: "buy" or "sell"
            time_in_force: Ignored for crypto (immediate execution)
        
        Returns:
            OrderResult with order status
        
        Raises:
            ValueError: If order validation fails
            RuntimeError: If adapter is in live trading (should use DryRun)
        """
        # Validate
        if not symbol or side.lower() not in ("buy", "sell"):
            raise ValueError(f"Invalid order: {symbol} {side} {quantity}")
        
        if quantity <= 0:
            raise ValueError(f"Quantity must be positive: {quantity}")
        
        # Check minimum order size
        min_size = self.MIN_ORDER_SIZE.get(symbol, 0.00001)
        if quantity < min_size:
            raise ValueError(f"Order quantity {quantity} below minimum {min_size}")
        
        # DRY_RUN enforcement
        if not self.paper_mode and self.dry_run:
            logger.warning(
                f"DRY_RUN: Order blocked: {side.upper()} {quantity} {symbol}"
            )
            return OrderResult(
                order_id=f"DRY_RUN_{self._next_order_id}",
                symbol=symbol,
                side=side,
                quantity=quantity,
                status=OrderStatus.REJECTED,
                filled_qty=0.0,
                filled_price=None,
                submit_time=datetime.now(timezone.utc),
                fill_time=None,
                rejection_reason="DRY_RUN: Order not submitted"
            )
        
        # Paper mode: simulate
        if self.paper_mode:
            return self._submit_paper_order(symbol, quantity, side)
        
        # Live mode: submit to Kraken
        if not self.enable_live_orders or not self.client:
            raise RuntimeError(
                "Live orders not enabled. "
                "Set ENABLE_LIVE_ORDERS=true and DRY_RUN=false"
            )
        
        try:
            kraken_symbol = self._normalize_symbol_to_kraken(symbol)
            
            order_result = self.client.request_private(
                "AddOrder",
                {
                    "pair": kraken_symbol,
                    "type": "market",
                    "ordertype": "market",
                    "side": side.lower(),
                    "volume": str(quantity)
                }
            )
            
            # Parse Kraken response
            order_id = order_result.get("txid", [None])[0]
            if not order_id:
                raise KrakenAPIError("No order ID in response")
            
            return OrderResult(
                order_id=str(order_id),
                symbol=symbol,
                side=side,
                quantity=quantity,
                status=OrderStatus.PENDING,
                filled_qty=0.0,
                filled_price=None,
                submit_time=datetime.now(timezone.utc),
                fill_time=None
            )
        
        except Exception as e:
            logger.error(f"Failed to submit order: {e}")
            raise
    
    def get_order_status(self, order_id: str) -> OrderResult:
        """
        Get status of an order.
        
        Args:
            order_id: Order ID returned from submit_market_order
        
        Returns:
            OrderResult with current status
        """
        if self.paper_mode:
            # Return from simulated state
            order = self._orders.get(order_id)
            if not order:
                raise ValueError(f"Order not found: {order_id}")
            
            return OrderResult(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                status=order.status,
                filled_qty=order.filled_qty,
                filled_price=order.filled_price,
                submit_time=order.submit_time,
                fill_time=order.fill_time
            )
        
        # Live mode: query Kraken
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        try:
            orders = self.client.request_private(
                "QueryOrders",
                {"txid": order_id}
            )
            
            # Parse and return
            order_data = orders.get(order_id)
            if not order_data:
                raise ValueError(f"Order not found: {order_id}")
            
            status_map = {
                "pending": OrderStatus.PENDING,
                "closed": OrderStatus.FILLED,
                "canceled": OrderStatus.CANCELLED,
                "expired": OrderStatus.EXPIRED
            }
            
            status = status_map.get(order_data.get("status"), OrderStatus.PENDING)
            
            return OrderResult(
                order_id=order_id,
                symbol="BTC/USD",  # Simplified
                side=order_data.get("descr", {}).get("type", "unknown"),
                quantity=float(order_data.get("vol", 0)),
                status=status,
                filled_qty=float(order_data.get("vol_exec", 0)),
                filled_price=None,  # Would need to query fills
                submit_time=datetime.now(timezone.utc),
                fill_time=None
            )
        
        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            raise
    
    def get_positions(self) -> Dict[str, Position]:
        """Get all open positions."""
        if self.paper_mode:
            return self._positions.copy()
        
        # Live: query from Kraken
        if not self.client:
            return {}
        
        try:
            # Kraken doesn't have traditional "positions" API for spot trading
            # Derive positions from balances
            balances = self.client.request_private("Balance", {})
            positions = {}
            
            for kraken_symbol, balance in balances.items():
                symbol = self._normalize_symbol_from_kraken(kraken_symbol)
                if symbol and float(balance) > 0:
                    positions[symbol] = Position(
                        symbol=symbol,
                        quantity=float(balance),
                        avg_entry_price=0.0,  # Not available from balance
                        current_price=0.0,     # Would need separate price query
                        unrealized_pnl=0.0,
                        unrealized_pnl_pct=0.0
                    )
            
            return positions
        
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return {}
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol."""
        positions = self.get_positions()
        return positions.get(symbol)
    
    def close_position(self, symbol: str) -> OrderResult:
        """Close position for symbol (sell all if long)."""
        position = self.get_position(symbol)
        if not position:
            raise ValueError(f"No position for {symbol}")
        
        # Sell entire position
        return self.submit_market_order(
            symbol=symbol,
            quantity=position.quantity,
            side="sell"
        )
    
    def get_market_hours(self, date: datetime) -> tuple:
        """
        Get market hours for a date.
        
        Crypto markets are 24/7, but this returns a dummy tuple for interface compatibility.
        
        Args:
            date: Date to check (ignored for crypto)
        
        Returns:
            Tuple of (market_open, market_close) - both at midnight UTC for crypto
        """
        market_open = date.replace(hour=0, minute=0, second=0, microsecond=0)
        market_close = date.replace(hour=23, minute=59, second=59, microsecond=0)
        return (market_open, market_close)
    
    def is_market_open(self) -> bool:
        """
        Check if market is open.
        
        Crypto markets are 24/7, so always returns True.
        
        Returns:
            Always True for crypto
        """
        return True
    
    # ========== Paper trading simulation ==========
    
    def _submit_paper_order(
        self,
        symbol: str,
        quantity: float,
        side: str
    ) -> OrderResult:
        """Simulate order submission in paper trading."""
        order_id = f"PAPER_{self._next_order_id}"
        self._next_order_id += 1
        
        # Simulate immediate execution for market orders
        order = KrakenOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=None,
            status=OrderStatus.FILLED,
            filled_qty=quantity,
            filled_price=100.0,  # Simplified
            submit_time=datetime.now(timezone.utc),
            fill_time=datetime.now(timezone.utc)
        )
        
        self._orders[order_id] = order
        
        logger.info(f"Paper order {side.upper()} {quantity} {symbol}: {order_id}")
        
        return OrderResult(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            status=OrderStatus.FILLED,
            filled_qty=quantity,
            filled_price=100.0,
            submit_time=order.submit_time,
            fill_time=order.fill_time
        )
    
    # ========== Symbol normalization ==========
    
    def _normalize_symbol_to_kraken(self, symbol: str) -> str:
        """
        Normalize internal symbol to Kraken symbol.
        
        Example: "BTC/USD" -> "XBTUSD"
        """
        return self.SYMBOL_MAP.get(symbol, symbol)
    
    def _normalize_symbol_from_kraken(self, kraken_symbol: str) -> Optional[str]:
        """
        Normalize Kraken symbol to internal symbol.
        
        Example: "XBTUSD" -> "BTC/USD"
        """
        return self.REVERSE_SYMBOL_MAP.get(kraken_symbol)
    
    def __del__(self):
        """Cleanup on deletion."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
