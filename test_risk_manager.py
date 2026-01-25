"""
Unit tests for risk/risk_manager.py

Tests trade approval logic, position sizing, and risk constraints.
"""

import unittest
import pandas as pd
from risk.portfolio_state import PortfolioState
from risk.risk_manager import RiskManager, TradeDecision
from config.settings import (
    RISK_PER_TRADE,
    MAX_RISK_PER_SYMBOL,
    MAX_PORTFOLIO_HEAT,
    MAX_TRADES_PER_DAY,
    MAX_CONSECUTIVE_LOSSES,
    DAILY_LOSS_LIMIT,
    CONFIDENCE_RISK_MULTIPLIER
)


class TestTradeDecision(unittest.TestCase):
    """Test TradeDecision dataclass."""
    
    def test_approval(self):
        """Test creating approved decision."""
        decision = TradeDecision(
            approved=True,
            position_size=100,
            risk_amount=1000.0,
            reason="All checks passed"
        )
        
        self.assertTrue(decision.approved)
        self.assertEqual(decision.position_size, 100)
        self.assertEqual(decision.risk_amount, 1000.0)
        self.assertIn("All checks passed", decision.reason)
    
    def test_rejection(self):
        """Test creating rejected decision."""
        decision = TradeDecision(
            approved=False,
            position_size=0,
            risk_amount=0.0,
            reason="Max consecutive losses exceeded"
        )
        
        self.assertFalse(decision.approved)
        self.assertEqual(decision.position_size, 0)
        self.assertEqual(decision.risk_amount, 0.0)


class TestRiskManager(unittest.TestCase):
    """Test RiskManager class for trade approval logic."""
    
    def setUp(self):
        """Set up risk manager and portfolio for each test."""
        self.portfolio = PortfolioState(initial_equity=100000.0)
        self.risk_manager = RiskManager(self.portfolio)
    
    def test_initialization(self):
        """Test risk manager initialization."""
        self.assertEqual(self.risk_manager.portfolio, self.portfolio)
    
    def test_approval_basic_trade(self):
        """Test approval of basic trade with all constraints met."""
        decision = self.risk_manager.evaluate_trade(
            symbol="AAPL",
            entry_price=150.0,
            confidence=3,
            current_prices={"AAPL": 150.0}
        )
        
        self.assertTrue(decision.approved)
        self.assertGreater(decision.position_size, 0)
        self.assertGreater(decision.risk_amount, 0)
    
    def test_rejection_consecutive_losses(self):
        """Test rejection when consecutive losses exceed limit."""
        # Simulate max consecutive losses
        self.portfolio.consecutive_losses = MAX_CONSECUTIVE_LOSSES
        
        decision = self.risk_manager.evaluate_trade(
            symbol="AAPL",
            entry_price=150.0,
            confidence=3,
            current_prices={"AAPL": 150.0}
        )
        
        self.assertFalse(decision.approved)
        self.assertIn("consecutive loss", decision.reason.lower())
    
    def test_rejection_daily_loss_limit(self):
        """Test rejection when daily loss limit exceeded."""
        # Open and close losing trade to trigger daily loss
        self.portfolio.open_trade(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=1000,
            risk_amount=100.0,
            confidence=3
        )
        self.portfolio.close_trade(
            symbol="AAPL",
            exit_date=pd.Timestamp("2024-01-01"),
            exit_price=149.0
        )
        
        # Daily loss is now ~0.1%, need bigger loss to exceed limit
        # Manually set to exceed limit for testing
        self.portfolio.daily_pnl = -self.portfolio.current_equity * DAILY_LOSS_LIMIT * 1.5
        
        decision = self.risk_manager.evaluate_trade(
            symbol="MSFT",
            entry_price=300.0,
            confidence=3,
            current_prices={"MSFT": 300.0}
        )
        
        self.assertFalse(decision.approved)
        self.assertIn("daily loss", decision.reason.lower())
    
    def test_rejection_max_daily_trades(self):
        """Test rejection when max daily trades exceeded."""
        # Open multiple trades on same day
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN"]
        for symbol in symbols:
            self.portfolio.open_trade(
                symbol=symbol,
                entry_date=pd.Timestamp("2024-01-01"),
                entry_price=150.0,
                position_size=10,
                risk_amount=100.0,
                confidence=3
            )
        
        # Now at max daily trades, next should be rejected
        decision = self.risk_manager.evaluate_trade(
            symbol="TSLA",
            entry_price=200.0,
            confidence=3,
            current_prices={"TSLA": 200.0}
        )
        
        self.assertFalse(decision.approved)
        self.assertIn("max trades", decision.reason.lower())
    
    def test_rejection_per_symbol_exposure(self):
        """Test rejection when per-symbol exposure too high."""
        # Open large position in AAPL
        self.portfolio.open_trade(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=2000,  # Large position
            risk_amount=1000.0,  # 1% of 100k
            confidence=3
        )
        
        # Try to add more to AAPL - should be rejected
        decision = self.risk_manager.evaluate_trade(
            symbol="AAPL",
            entry_price=150.0,
            confidence=3,
            current_prices={"AAPL": 150.0}
        )
        
        # Position already open, so this should be rejected or error
        self.assertFalse(decision.approved)
    
    def test_rejection_portfolio_heat(self):
        """Test rejection when portfolio heat too high."""
        # Open positions to reach high heat
        heat_positions = [
            ("AAPL", 150.0, 1000),
            ("MSFT", 300.0, 400),
            ("GOOGL", 100.0, 1000),
            ("AMZN", 150.0, 800),
        ]
        
        for symbol, price, size in heat_positions:
            self.portfolio.open_trade(
                symbol=symbol,
                entry_date=pd.Timestamp("2024-01-01"),
                entry_price=price,
                position_size=size,
                risk_amount=1000.0,
                confidence=3
            )
        
        # Portfolio heat should now be high
        current_prices = {sym: price for sym, price, _ in heat_positions}
        heat = self.portfolio.get_portfolio_heat(current_prices)
        
        if heat >= MAX_PORTFOLIO_HEAT:
            decision = self.risk_manager.evaluate_trade(
                symbol="NEW",
                entry_price=100.0,
                confidence=3,
                current_prices={**current_prices, "NEW": 100.0}
            )
            
            self.assertFalse(decision.approved)
            self.assertIn("portfolio heat", decision.reason.lower())
    
    def test_confidence_affects_position_size(self):
        """Test that confidence multiplier affects position size."""
        # Get position size with low confidence
        decision_low = self.risk_manager.evaluate_trade(
            symbol="AAPL",
            entry_price=150.0,
            confidence=1,
            current_prices={"AAPL": 150.0}
        )
        
        # Get position size with high confidence
        decision_high = self.risk_manager.evaluate_trade(
            symbol="MSFT",
            entry_price=150.0,
            confidence=5,
            current_prices={"MSFT": 150.0}
        )
        
        # High confidence should result in larger position
        self.assertGreater(decision_high.position_size, decision_low.position_size)
    
    def test_confidence_multiplier_mapping(self):
        """Test confidence to multiplier mapping."""
        # Check all confidence levels
        for confidence in range(1, 6):
            multiplier = self.risk_manager._get_confidence_multiplier(confidence)
            self.assertIn(multiplier, CONFIDENCE_RISK_MULTIPLIER.values())
    
    def test_position_size_calculation(self):
        """Test position size calculation formula."""
        equity = self.portfolio.current_equity
        entry_price = 150.0
        confidence = 3
        
        decision = self.risk_manager.evaluate_trade(
            symbol="AAPL",
            entry_price=entry_price,
            confidence=confidence,
            current_prices={"AAPL": entry_price}
        )
        
        multiplier = CONFIDENCE_RISK_MULTIPLIER[confidence]
        expected_risk = equity * RISK_PER_TRADE * multiplier
        expected_position_size = expected_risk / entry_price
        
        self.assertAlmostEqual(
            decision.position_size,
            expected_position_size,
            delta=1.0  # Allow 1 share rounding
        )
    
    def test_approval_log_updated(self):
        """Test that decision count increases."""
        summary_before = self.risk_manager.get_summary()
        before_count = summary_before["total_decisions"]
        
        self.risk_manager.evaluate_trade(
            symbol="AAPL",
            entry_price=150.0,
            confidence=3,
            current_prices={"AAPL": 150.0}
        )
        
        summary_after = self.risk_manager.get_summary()
        after_count = summary_after["total_decisions"]
        
        self.assertEqual(after_count, before_count + 1)
    
    def test_rejection_log_updated(self):
        """Test that rejection records are tracked."""
        # Trigger rejection
        self.portfolio.consecutive_losses = MAX_CONSECUTIVE_LOSSES + 1
        
        self.risk_manager.evaluate_trade(
            symbol="AAPL",
            entry_price=150.0,
            confidence=3,
            current_prices={"AAPL": 150.0}
        )
        
        summary = self.risk_manager.get_summary()
        self.assertGreater(summary["rejections"], 0)
    
    def test_get_summary(self):
        """Test summary generation."""
        # Make some trades
        for i in range(3):
            decision = self.risk_manager.evaluate_trade(
                symbol=f"SYM{i}",
                entry_price=150.0 + i*10,
                confidence=3,
                current_prices={f"SYM{i}": 150.0 + i*10}
            )
        
        summary = self.risk_manager.get_summary()
        
        self.assertIn("total_decisions", summary)
        self.assertIn("approvals", summary)
        self.assertIn("rejections", summary)
        self.assertIn("approval_rate", summary)
    
    def test_risk_manager_factory(self):
        """Test that risk manager can be created."""
        risk_manager = RiskManager(self.portfolio)
        
        self.assertIsInstance(risk_manager, RiskManager)
        self.assertEqual(risk_manager.portfolio, self.portfolio)


class TestRiskConstraints(unittest.TestCase):
    """Test all risk constraints together."""
    
    def setUp(self):
        """Set up for constraint tests."""
        self.portfolio = PortfolioState(initial_equity=100000.0)
        self.risk_manager = RiskManager(self.portfolio)
    
    def test_kill_switches_priority(self):
        """Test that kill switches are checked before position sizing."""
        # Set up kill switch condition
        self.portfolio.consecutive_losses = MAX_CONSECUTIVE_LOSSES
        
        # Trade should be rejected even with valid entry
        decision = self.risk_manager.evaluate_trade(
            symbol="AAPL",
            entry_price=150.0,
            confidence=5,  # High confidence
            current_prices={"AAPL": 150.0}
        )
        
        self.assertFalse(decision.approved)
        self.assertEqual(decision.position_size, 0)
    
    def test_normal_trade_flow(self):
        """Test normal trade approval with all constraints satisfied."""
        # Start fresh
        decision = self.risk_manager.evaluate_trade(
            symbol="AAPL",
            entry_price=150.0,
            confidence=3,
            current_prices={"AAPL": 150.0}
        )
        
        self.assertTrue(decision.approved)
        self.assertGreater(decision.position_size, 0)
        self.assertGreater(decision.risk_amount, 0)
        self.assertIn("approved", decision.reason.lower())


if __name__ == "__main__":
    unittest.main()
