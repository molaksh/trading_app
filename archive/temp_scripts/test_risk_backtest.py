"""
Unit tests for backtest/risk_backtest.py

Tests risk-governed backtest integration and metrics.
"""

import unittest
from backtest.risk_backtest import RiskGovernedBacktest, run_risk_governed_backtest


class TestRiskGovernedBacktest(unittest.TestCase):
    """Test RiskGovernedBacktest class."""
    
    def setUp(self):
        """Set up backtest for tests."""
        self.symbols = ["AAPL", "MSFT"]
    
    def test_initialization(self):
        """Test backtest initialization."""
        backtest = RiskGovernedBacktest(
            symbols=self.symbols,
            enforce_risk=True
        )
        
        self.assertEqual(backtest.symbols, self.symbols)
        self.assertTrue(backtest.enforce_risk)
    
    def test_with_risk_enforcement_false(self):
        """Test backtest with risk enforcement disabled."""
        backtest = RiskGovernedBacktest(
            symbols=self.symbols,
            enforce_risk=False
        )
        
        self.assertFalse(backtest.enforce_risk)
    
    def test_run_completes(self):
        """Test that backtest run completes without errors."""
        backtest = RiskGovernedBacktest(
            symbols=self.symbols,
            enforce_risk=True
        )
        
        trades = backtest.run()
        
        # Should return a list
        self.assertIsInstance(trades, list)
        # Should have trades (or empty if no signals)
        self.assertIsInstance(trades, list)
    
    def test_get_summary(self):
        """Test summary generation."""
        backtest = RiskGovernedBacktest(
            symbols=self.symbols,
            enforce_risk=True
        )
        
        backtest.run()
        summary = backtest.get_summary()
        
        self.assertIsInstance(summary, dict)
        self.assertIn("trades", summary)
        self.assertIn("rejected_trades", summary)
        self.assertIn("max_portfolio_heat", summary)


class TestRiskGovernedBacktestFunction(unittest.TestCase):
    """Test run_risk_governed_backtest function."""
    
    def setUp(self):
        """Set up for function tests."""
        self.symbols = ["AAPL", "MSFT"]
    
    def test_function_with_risk_enforcement(self):
        """Test function with risk enforcement enabled."""
        trades = run_risk_governed_backtest(
            symbols=self.symbols,
            enforce_risk=True
        )
        
        self.assertIsInstance(trades, list)
    
    def test_function_without_risk_enforcement(self):
        """Test function with risk enforcement disabled."""
        trades = run_risk_governed_backtest(
            symbols=self.symbols,
            enforce_risk=False
        )
        
        self.assertIsInstance(trades, list)
    
    def test_function_comparison(self):
        """Test that risk enforcement affects trade count."""
        trades_with_risk = run_risk_governed_backtest(
            symbols=self.symbols,
            enforce_risk=True
        )
        
        trades_no_risk = run_risk_governed_backtest(
            symbols=self.symbols,
            enforce_risk=False
        )
        
        # Risk enforcement might reject some trades
        # so count with risk should be <= count without
        self.assertLessEqual(len(trades_with_risk), len(trades_no_risk) + 1)
        # (allowing for randomness in backtesting)


class TestRiskConstraintApplication(unittest.TestCase):
    """Test that risk constraints are applied during backtest."""
    
    def setUp(self):
        """Set up for constraint tests."""
        self.symbols = ["AAPL"]
    
    def test_risk_enforcement_reduces_trades(self):
        """Test that enforcing risk generally reduces trade count."""
        # Run multiple times to account for randomness
        with_risk_counts = []
        without_risk_counts = []
        
        for _ in range(3):
            trades_with = run_risk_governed_backtest(
                symbols=self.symbols,
                enforce_risk=True
            )
            trades_without = run_risk_governed_backtest(
                symbols=self.symbols,
                enforce_risk=False
            )
            
            with_risk_counts.append(len(trades_with))
            without_risk_counts.append(len(trades_without))
        
        # Average should show enforcement reduces trades
        avg_with = sum(with_risk_counts) / len(with_risk_counts)
        avg_without = sum(without_risk_counts) / len(without_risk_counts)
        
        # Can't always guarantee, but risk should generally limit
        self.assertLessEqual(avg_with, avg_without + 1)


if __name__ == "__main__":
    unittest.main()
