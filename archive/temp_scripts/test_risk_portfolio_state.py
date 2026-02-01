"""
Unit tests for risk/portfolio_state.py

Tests portfolio state tracking, position management, and exposure calculation.
"""

import unittest
import pandas as pd
from risk.portfolio_state import OpenPosition, PortfolioState


class TestOpenPosition(unittest.TestCase):
    """Test OpenPosition class for individual position tracking."""
    
    def test_creation(self):
        """Test creating a position."""
        pos = OpenPosition(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=10,
            risk_amount=100.0,
            confidence=4
        )
        
        self.assertEqual(pos.symbol, "AAPL")
        self.assertEqual(pos.entry_price, 150.0)
        self.assertEqual(pos.position_size, 10)
        self.assertEqual(pos.risk_amount, 100.0)
        self.assertEqual(pos.confidence, 4)
        self.assertEqual(pos.unrealized_pnl, 0.0)
    
    def test_winning_trade(self):
        """Test position with profit."""
        pos = OpenPosition(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=10,
            risk_amount=100.0,
            confidence=4
        )
        
        # Update price with profit
        pos.update_price(160.0)
        
        self.assertEqual(pos.current_price, 160.0)
        self.assertEqual(pos.unrealized_pnl, 100.0)  # (160-150)*10
    
    def test_losing_trade(self):
        """Test position with loss."""
        pos = OpenPosition(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=10,
            risk_amount=100.0,
            confidence=4
        )
        
        # Update price with loss
        pos.update_price(145.0)
        
        self.assertEqual(pos.current_price, 145.0)
        self.assertEqual(pos.unrealized_pnl, -50.0)  # (145-150)*10


class TestPortfolioState(unittest.TestCase):
    """Test PortfolioState class for portfolio-level tracking."""
    
    def setUp(self):
        """Set up portfolio for each test."""
        self.portfolio = PortfolioState(initial_equity=100000.0)
    
    def test_initialization(self):
        """Test portfolio initialization."""
        self.assertEqual(self.portfolio.initial_equity, 100000.0)
        self.assertEqual(self.portfolio.current_equity, 100000.0)
        self.assertEqual(self.portfolio.open_positions, {})
        self.assertEqual(len(self.portfolio.trades_closed), 0)
        self.assertEqual(self.portfolio.daily_pnl, 0.0)
    
    def test_open_single_position(self):
        """Test opening a single position."""
        self.portfolio.open_trade(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=10,
            risk_amount=100.0,
            confidence=4
        )
        
        self.assertIn("AAPL", self.portfolio.open_positions)
        self.assertEqual(len(self.portfolio.open_positions["AAPL"]), 1)
        self.assertEqual(self.portfolio.open_positions["AAPL"][0].position_size, 10)
    
    def test_open_multiple_positions(self):
        """Test opening multiple positions in different symbols."""
        symbols = ["AAPL", "MSFT", "GOOGL"]
        for i, symbol in enumerate(symbols):
            self.portfolio.open_trade(
                symbol=symbol,
                entry_date=pd.Timestamp("2024-01-01"),
                entry_price=150.0 + i*50,
                position_size=10,
                risk_amount=100.0,
                confidence=3
            )
        
        self.assertEqual(len(self.portfolio.open_positions), 3)
        for symbol in symbols:
            self.assertIn(symbol, self.portfolio.open_positions)
    
    def test_open_position_same_symbol_raises_error(self):
        """Test that opening position in same symbol is allowed (FIFO)."""
        self.portfolio.open_trade(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=10,
            risk_amount=100.0,
            confidence=4
        )
        
        # Can open multiple positions in same symbol (stacked)
        self.portfolio.open_trade(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=151.0,
            position_size=10,
            risk_amount=100.0,
            confidence=4
        )
        
        # Should have 2 positions for AAPL
        self.assertEqual(len(self.portfolio.open_positions["AAPL"]), 2)
    
    def test_close_position_with_profit(self):
        """Test closing position with profit."""
        self.portfolio.open_trade(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=10,
            risk_amount=100.0,
            confidence=4
        )
        
        initial_equity = self.portfolio.current_equity
        
        self.portfolio.close_trade(
            symbol="AAPL",
            exit_date=pd.Timestamp("2024-01-05"),
            exit_price=160.0
        )
        
        # Position should be removed
        self.assertEqual(len(self.portfolio.open_positions.get("AAPL", [])), 0)
        self.assertEqual(len(self.portfolio.trades_closed), 1)
        
        # Equity should increase by PnL (profit)
        self.assertEqual(self.portfolio.current_equity, initial_equity + 100.0)
    
    def test_close_position_with_loss(self):
        """Test closing position with loss."""
        self.portfolio.open_trade(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=10,
            risk_amount=100.0,
            confidence=4
        )
        
        initial_equity = self.portfolio.current_equity
        
        self.portfolio.close_trade(
            symbol="AAPL",
            exit_date=pd.Timestamp("2024-01-05"),
            exit_price=145.0
        )
        
        # Equity should decrease by loss
        self.assertEqual(self.portfolio.current_equity, initial_equity - 50.0)
        self.assertEqual(self.portfolio.daily_pnl, -50.0)
    
    def test_consecutive_losses_tracking(self):
        """Test consecutive loss counter."""
        # Open and close first losing trade
        self.portfolio.open_trade(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=10,
            risk_amount=100.0,
            confidence=4
        )
        self.portfolio.close_trade(
            symbol="AAPL",
            exit_date=pd.Timestamp("2024-01-02"),
            exit_price=145.0  # Loss
        )
        
        self.assertEqual(self.portfolio.consecutive_losses, 1)
        
        # Open and close second losing trade
        self.portfolio.open_trade(
            symbol="MSFT",
            entry_date=pd.Timestamp("2024-01-03"),
            entry_price=300.0,
            position_size=5,
            risk_amount=100.0,
            confidence=3
        )
        self.portfolio.close_trade(
            symbol="MSFT",
            exit_date=pd.Timestamp("2024-01-04"),
            exit_price=295.0  # Loss
        )
        
        self.assertEqual(self.portfolio.consecutive_losses, 2)
        
        # Winning trade resets counter
        self.portfolio.open_trade(
            symbol="GOOGL",
            entry_date=pd.Timestamp("2024-01-05"),
            entry_price=100.0,
            position_size=20,
            risk_amount=100.0,
            confidence=5
        )
        self.portfolio.close_trade(
            symbol="GOOGL",
            exit_date=pd.Timestamp("2024-01-06"),
            exit_price=105.0  # Win
        )
        
        self.assertEqual(self.portfolio.consecutive_losses, 0)
    
    def test_daily_trades_counter(self):
        """Test daily trade counter."""
        # Open multiple trades on same day
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN"]
        for i, symbol in enumerate(symbols):
            self.portfolio.open_trade(
                symbol=symbol,
                entry_date=pd.Timestamp("2024-01-01"),
                entry_price=150.0 + i*10,
                position_size=5,
                risk_amount=50.0,
                confidence=3
            )
        
        self.assertEqual(self.portfolio.daily_trades_opened, 4)
    
    def test_daily_loss_pct_calculation(self):
        """Test daily loss percentage."""
        initial_equity = 100000.0
        
        # Open and close losing trade
        self.portfolio.open_trade(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=100,
            risk_amount=100.0,
            confidence=4
        )
        self.portfolio.close_trade(
            symbol="AAPL",
            exit_date=pd.Timestamp("2024-01-01"),
            exit_price=140.0
        )
        
        # Loss: (140-150)*100 = -1000
        daily_loss_pct = abs(self.portfolio.daily_pnl) / initial_equity
        self.assertAlmostEqual(daily_loss_pct, 1000.0 / initial_equity, places=5)
    
    def test_portfolio_heat_no_positions(self):
        """Test portfolio heat with no open positions."""
        current_prices = {}
        heat = self.portfolio.get_portfolio_heat(current_prices)
        self.assertEqual(heat, 0.0)
    
    def test_portfolio_heat_single_position(self):
        """Test portfolio heat with single position."""
        self.portfolio.open_trade(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=10,
            risk_amount=1000.0,  # 1% of 100k equity
            confidence=4
        )
        
        heat = self.portfolio.get_portfolio_heat({"AAPL": 150.0})
        self.assertAlmostEqual(heat, 0.01, places=5)
    
    def test_portfolio_heat_multiple_positions(self):
        """Test portfolio heat with multiple positions."""
        self.portfolio.open_trade(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=10,
            risk_amount=1000.0,
            confidence=4
        )
        
        self.portfolio.open_trade(
            symbol="MSFT",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=300.0,
            position_size=5,
            risk_amount=1000.0,
            confidence=3
        )
        
        heat = self.portfolio.get_portfolio_heat({"AAPL": 150.0, "MSFT": 300.0})
        self.assertAlmostEqual(heat, 0.02, places=5)
    
    def test_symbol_exposure_calculation(self):
        """Test per-symbol exposure calculation."""
        self.portfolio.open_trade(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=10,
            risk_amount=1000.0,
            confidence=4
        )
        
        # Position value: 150*10 = 1500
        # Exposure: 1500 / 100000 = 0.015 (1.5%)
        exposure = self.portfolio.get_symbol_exposure("AAPL")
        self.assertAlmostEqual(exposure, 0.015, places=5)
    
    def test_cumulative_return(self):
        """Test cumulative return calculation."""
        # Trade 1: +1000
        self.portfolio.open_trade(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=100,
            risk_amount=100.0,
            confidence=4
        )
        self.portfolio.close_trade(
            symbol="AAPL",
            exit_date=pd.Timestamp("2024-01-02"),
            exit_price=160.0
        )
        
        # Trade 2: -500
        self.portfolio.open_trade(
            symbol="MSFT",
            entry_date=pd.Timestamp("2024-01-03"),
            entry_price=300.0,
            position_size=50,
            risk_amount=100.0,
            confidence=3
        )
        self.portfolio.close_trade(
            symbol="MSFT",
            exit_date=pd.Timestamp("2024-01-04"),
            exit_price=290.0
        )
        
        # Net: +500, daily_pnl should be +500
        self.assertAlmostEqual(self.portfolio.daily_pnl, 500.0, places=1)
    
    def test_summary_generation(self):
        """Test summary generation."""
        self.portfolio.open_trade(
            symbol="AAPL",
            entry_date=pd.Timestamp("2024-01-01"),
            entry_price=150.0,
            position_size=10,
            risk_amount=100.0,
            confidence=4
        )
        self.portfolio.close_trade(
            symbol="AAPL",
            exit_date=pd.Timestamp("2024-01-02"),
            exit_price=155.0
        )
        
        summary = self.portfolio.get_summary()
        
        self.assertIn("current_equity", summary)
        self.assertIn("available_capital", summary)
        self.assertIn("open_positions", summary)
        self.assertIn("daily_pnl", summary)
        self.assertIn("total_trades_closed", summary)
        self.assertIn("consecutive_losses", summary)
        
        self.assertEqual(summary["total_trades_closed"], 1)
        self.assertEqual(summary["daily_pnl"], 50.0)


if __name__ == "__main__":
    unittest.main()
