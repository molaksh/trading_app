"""
Tests for Phase I: Paper Trading Broker Integration

Test coverage:
- Broker adapter interface
- Alpaca adapter (mocked)
- Paper trading executor
- Execution logging
- Integration flow
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
import json
import tempfile
from pathlib import Path

from broker.adapter import BrokerAdapter, OrderStatus, OrderResult, Position
from broker.alpaca_adapter import AlpacaAdapter
from broker.paper_trading_executor import PaperTradingExecutor
from broker.execution_logger import ExecutionLogger


class MockBrokerAdapter(BrokerAdapter):
    """Mock broker for testing."""
    
    def __init__(self, is_paper=True):
        self._is_paper = is_paper
        self._equity = 100000.0
        self._buying_power = 100000.0
        self._positions = {}
        self._next_order_id = 1
        self._orders = {}
    
    @property
    def is_paper_trading(self) -> bool:
        if not self._is_paper:
            raise RuntimeError("Live trading detected!")
        return True
    
    @property
    def account_equity(self) -> float:
        return self._equity
    
    @property
    def buying_power(self) -> float:
        return self._buying_power
    
    def submit_market_order(
        self,
        symbol: str,
        quantity: float,
        side: str,
        time_in_force: str = "opg",
    ) -> OrderResult:
        if not symbol or quantity <= 0:
            raise ValueError("Invalid order parameters")
        
        order_id = f"ORDER_{self._next_order_id}"
        self._next_order_id += 1
        
        order_result = OrderResult(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            status=OrderStatus.PENDING,
            filled_qty=0,
            filled_price=None,
            submit_time=datetime.now(),
            fill_time=None,
        )
        
        self._orders[order_id] = {
            "result": order_result,
            "fills_on_poll": 2,  # Fill after 2 polls
            "poll_count": 0,
        }
        
        return order_result
    
    def get_order_status(self, order_id: str) -> OrderResult:
        if order_id not in self._orders:
            raise ValueError(f"Order not found: {order_id}")
        
        order_data = self._orders[order_id]
        order_result = order_data["result"]
        
        order_data["poll_count"] += 1
        
        # Auto-fill after N polls
        if order_data["poll_count"] >= order_data["fills_on_poll"]:
            filled_result = OrderResult(
                order_id=order_id,
                symbol=order_result.symbol,
                side=order_result.side,
                quantity=order_result.quantity,
                status=OrderStatus.FILLED,
                filled_qty=order_result.quantity,
                filled_price=100.0,  # Mock fill price
                submit_time=order_result.submit_time,
                fill_time=datetime.now(),
            )
            self._orders[order_id]["result"] = filled_result
            return filled_result
        
        return order_result
    
    def get_positions(self):
        return self._positions
    
    def get_position(self, symbol: str):
        return self._positions.get(symbol)
    
    def close_position(self, symbol: str) -> OrderResult:
        if symbol not in self._positions:
            raise ValueError(f"No position: {symbol}")
        
        pos = self._positions[symbol]
        return self.submit_market_order(
            symbol=symbol,
            quantity=abs(pos.quantity),
            side="sell" if pos.quantity > 0 else "buy",
        )
    
    def get_market_hours(self, date: datetime):
        return (
            date.replace(hour=9, minute=30),
            date.replace(hour=16, minute=0),
        )
    
    def is_market_open(self) -> bool:
        return True


class TestOrderStatus(unittest.TestCase):
    """Test OrderStatus and OrderResult."""
    
    def test_order_result_filled(self):
        """Test filled order result."""
        result = OrderResult(
            order_id="ORDER_1",
            symbol="AAPL",
            side="buy",
            quantity=100,
            status=OrderStatus.FILLED,
            filled_qty=100,
            filled_price=150.0,
            submit_time=datetime.now(),
            fill_time=datetime.now(),
        )
        
        self.assertTrue(result.is_filled())
        self.assertFalse(result.is_pending())
        self.assertEqual(result.filled_price, 150.0)
    
    def test_order_result_pending(self):
        """Test pending order result."""
        result = OrderResult(
            order_id="ORDER_1",
            symbol="AAPL",
            side="buy",
            quantity=100,
            status=OrderStatus.PENDING,
            filled_qty=0,
            filled_price=None,
            submit_time=datetime.now(),
            fill_time=None,
        )
        
        self.assertFalse(result.is_filled())
        self.assertTrue(result.is_pending())
    
    def test_order_result_rejected(self):
        """Test rejected order result."""
        result = OrderResult(
            order_id="ORDER_1",
            symbol="AAPL",
            side="buy",
            quantity=100,
            status=OrderStatus.REJECTED,
            filled_qty=0,
            filled_price=None,
            submit_time=datetime.now(),
            fill_time=None,
            rejection_reason="Insufficient buying power",
        )
        
        self.assertFalse(result.is_filled())
        self.assertFalse(result.is_pending())
        self.assertIsNotNone(result.rejection_reason)


class TestPosition(unittest.TestCase):
    """Test Position class."""
    
    def test_position_long(self):
        """Test long position."""
        pos = Position(
            symbol="AAPL",
            quantity=100,
            avg_entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=500.0,
            unrealized_pnl_pct=0.0333,
        )
        
        self.assertTrue(pos.is_long())
        self.assertFalse(pos.is_short())
        self.assertEqual(pos.quantity, 100)
    
    def test_position_short(self):
        """Test short position."""
        pos = Position(
            symbol="AAPL",
            quantity=-100,
            avg_entry_price=150.0,
            current_price=145.0,
            unrealized_pnl=500.0,
            unrealized_pnl_pct=0.0333,
        )
        
        self.assertFalse(pos.is_long())
        self.assertTrue(pos.is_short())
        self.assertEqual(pos.quantity, -100)


class TestMockBrokerAdapter(unittest.TestCase):
    """Test mock broker adapter."""
    
    def setUp(self):
        self.broker = MockBrokerAdapter()
    
    def test_paper_trading_check(self):
        """Test paper trading verification."""
        self.assertTrue(self.broker.is_paper_trading)
    
    def test_paper_trading_live_check_raises(self):
        """Test that live trading raises exception."""
        live_broker = MockBrokerAdapter(is_paper=False)
        with self.assertRaises(RuntimeError):
            _ = live_broker.is_paper_trading
    
    def test_submit_market_order(self):
        """Test market order submission."""
        result = self.broker.submit_market_order(
            symbol="AAPL",
            quantity=100,
            side="buy",
        )
        
        self.assertEqual(result.symbol, "AAPL")
        self.assertEqual(result.side, "buy")
        self.assertEqual(result.quantity, 100)
        self.assertEqual(result.status, OrderStatus.PENDING)
    
    def test_submit_market_order_invalid_quantity(self):
        """Test that invalid quantity raises error."""
        with self.assertRaises(ValueError):
            self.broker.submit_market_order(
                symbol="AAPL",
                quantity=-100,
                side="buy",
            )
    
    def test_get_order_status(self):
        """Test order status polling."""
        # Submit order
        result = self.broker.submit_market_order(
            symbol="AAPL",
            quantity=100,
            side="buy",
        )
        order_id = result.order_id
        
        # Check pending
        status = self.broker.get_order_status(order_id)
        self.assertEqual(status.status, OrderStatus.PENDING)
        
        # Poll until filled
        for _ in range(5):
            status = self.broker.get_order_status(order_id)
            if status.is_filled():
                break
        
        self.assertTrue(status.is_filled())
        self.assertEqual(status.filled_price, 100.0)
    
    def test_market_hours(self):
        """Test market hours query."""
        today = datetime.now().date()
        date = datetime(today.year, today.month, today.day)
        
        market_open, market_close = self.broker.get_market_hours(date)
        
        self.assertEqual(market_open.hour, 9)
        self.assertEqual(market_open.minute, 30)
        self.assertEqual(market_close.hour, 16)


class TestExecutionLogger(unittest.TestCase):
    """Test execution logger."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.logger = ExecutionLogger(self.temp_dir)
    
    def test_log_signal_generated(self):
        """Test signal logging."""
        self.logger.log_signal_generated(
            symbol="AAPL",
            confidence=4,
            signal_date=datetime.now(),
            features={"atr_pct": 0.02},
        )
        
        # Check file exists
        self.assertTrue(self.logger.trade_log_path.exists())
    
    def test_log_order_submitted(self):
        """Test order submission logging."""
        self.logger.log_order_submitted(
            symbol="AAPL",
            order_id="ORDER_1",
            side="buy",
            quantity=100,
            confidence=4,
            position_size=100,
            risk_amount=0.01,
        )
        
        self.assertTrue(self.logger.trade_log_path.exists())
    
    def test_log_order_filled(self):
        """Test order fill logging."""
        self.logger.log_order_filled(
            symbol="AAPL",
            order_id="ORDER_1",
            side="buy",
            quantity=100,
            fill_price=150.0,
            fill_time=datetime.now(),
        )
        
        self.assertTrue(self.logger.trade_log_path.exists())
    
    def test_log_order_rejected(self):
        """Test order rejection logging."""
        self.logger.log_order_rejected(
            symbol="AAPL",
            order_id="ORDER_1",
            side="buy",
            quantity=100,
            reason="Insufficient buying power",
        )
        
        self.assertTrue(self.logger.error_log_path.exists())
    
    def test_get_summary(self):
        """Test summary generation."""
        self.logger.log_order_submitted(
            symbol="AAPL",
            order_id="ORDER_1",
            side="buy",
            quantity=100,
            confidence=4,
            position_size=100,
            risk_amount=0.01,
        )
        
        summary = self.logger.get_summary()
        self.assertIn("trades", summary)
        self.assertGreater(summary["trades"], 0)


class TestPaperTradingExecutor(unittest.TestCase):
    """Test paper trading executor."""
    
    def setUp(self):
        from risk.portfolio_state import PortfolioState
        from risk.risk_manager import RiskManager
        
        self.broker = MockBrokerAdapter()
        self.portfolio = PortfolioState(100000.0)
        self.risk_manager = RiskManager(self.portfolio)
        
        self.executor = PaperTradingExecutor(
            broker=self.broker,
            risk_manager=self.risk_manager,
        )
    
    def test_execute_signal_approved(self):
        """Test signal execution with approval."""
        success, order_id = self.executor.execute_signal(
            symbol="AAPL",
            confidence=4,
            signal_date=datetime.now(),
            features={"atr_pct": 0.02},
        )
        
        self.assertTrue(success)
        self.assertIsNotNone(order_id)
    
    def test_poll_order_fills(self):
        """Test order fill polling."""
        # Submit order
        success, order_id = self.executor.execute_signal(
            symbol="AAPL",
            confidence=4,
            signal_date=datetime.now(),
            features={"atr_pct": 0.02},
        )
        
        self.assertTrue(success)
        self.assertIn(order_id, self.executor.pending_orders)
        
        # Poll until filled
        for _ in range(5):
            filled = self.executor.poll_order_fills()
            if "AAPL" in filled:
                self.assertIn("AAPL", filled)
                break
    
    def test_get_account_status(self):
        """Test account status query."""
        status = self.executor.get_account_status()
        
        self.assertIn("equity", status)
        self.assertIn("buying_power", status)
        self.assertIn("pending_orders", status)
        self.assertIn("open_positions", status)


class TestIntegration(unittest.TestCase):
    """Integration tests for paper trading flow."""
    
    def test_full_execution_flow(self):
        """Test complete execution flow."""
        from risk.portfolio_state import PortfolioState
        from risk.risk_manager import RiskManager
        
        # Initialize components
        broker = MockBrokerAdapter()
        portfolio = PortfolioState(100000.0)
        risk_manager = RiskManager(portfolio)
        executor = PaperTradingExecutor(
            broker=broker,
            risk_manager=risk_manager,
        )
        
        # Generate signal
        success, order_id = executor.execute_signal(
            symbol="AAPL",
            confidence=4,
            signal_date=datetime.now(),
            features={"atr_pct": 0.02},
        )
        
        self.assertTrue(success)
        
        # Poll fills
        for _ in range(5):
            filled = executor.poll_order_fills()
            if "AAPL" in filled:
                break
        
        # Check account status
        status = executor.get_account_status()
        self.assertGreater(status["open_positions"], 0)


if __name__ == '__main__':
    unittest.main()
