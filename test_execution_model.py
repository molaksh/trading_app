"""
Unit tests for execution/execution_model.py

Tests execution realism without any real data or live trading.
"""

import unittest
from datetime import datetime

import pandas as pd
import numpy as np

from execution.execution_model import (
    apply_slippage,
    compute_entry_price,
    compute_exit_price,
    check_liquidity,
    compute_slippage_cost,
    ExecutionModel,
)


class TestSlippage(unittest.TestCase):
    """Test slippage calculations."""
    
    def test_entry_slippage_worse_price(self):
        """Entry slippage should result in worse (higher) entry price."""
        base_price = 100.0
        slipped_price = apply_slippage(base_price, 5, direction="entry")
        
        # 5 bps = 0.05% → 100.00 * 1.0005 = 100.05
        self.assertAlmostEqual(slipped_price, 100.05, places=4)
        self.assertGreater(slipped_price, base_price)
    
    def test_exit_slippage_worse_price(self):
        """Exit slippage should result in worse (lower) exit price."""
        base_price = 100.0
        slipped_price = apply_slippage(base_price, 5, direction="exit")
        
        # 5 bps = 0.05% → 100.00 * 0.9995 = 99.95
        self.assertAlmostEqual(slipped_price, 99.95, places=4)
        self.assertLess(slipped_price, base_price)
    
    def test_zero_slippage(self):
        """Zero slippage should return same price."""
        base_price = 100.0
        
        entry = apply_slippage(base_price, 0, direction="entry")
        exit_price = apply_slippage(base_price, 0, direction="exit")
        
        self.assertEqual(entry, base_price)
        self.assertEqual(exit_price, base_price)
    
    def test_large_slippage(self):
        """Test with large slippage (100 bps = 1%)."""
        base_price = 100.0
        
        entry = apply_slippage(base_price, 100, direction="entry")
        exit_price = apply_slippage(base_price, 100, direction="exit")
        
        self.assertAlmostEqual(entry, 101.0, places=4)
        self.assertAlmostEqual(exit_price, 99.0, places=4)


class TestLiquidity(unittest.TestCase):
    """Test liquidity checks."""
    
    def test_position_within_limits(self):
        """Position within 5% of ADV should pass."""
        position_notional = 500_000  # $500k
        avg_daily_volume = 10_000_000  # $10M ADV
        
        passed, reason = check_liquidity(position_notional, avg_daily_volume, max_adv_pct=0.05)
        
        self.assertTrue(passed)
        self.assertIsNone(reason)
    
    def test_position_exceeds_limits(self):
        """Position exceeding 5% of ADV should fail."""
        position_notional = 600_000  # $600k = 6% of $10M
        avg_daily_volume = 10_000_000  # $10M ADV
        
        passed, reason = check_liquidity(position_notional, avg_daily_volume, max_adv_pct=0.05)
        
        self.assertFalse(passed)
        self.assertIsNotNone(reason)
        self.assertIn("Position too large", reason)
    
    def test_position_at_limit(self):
        """Position exactly at limit should pass."""
        position_notional = 500_000  # $500k = 5% of $10M
        avg_daily_volume = 10_000_000  # $10M ADV
        
        passed, reason = check_liquidity(position_notional, avg_daily_volume, max_adv_pct=0.05)
        
        self.assertTrue(passed)
        self.assertIsNone(reason)
    
    def test_invalid_adv(self):
        """Invalid ADV should fail."""
        position_notional = 100_000
        avg_daily_volume = 0  # Invalid
        
        passed, reason = check_liquidity(position_notional, avg_daily_volume)
        
        self.assertFalse(passed)
        self.assertIsNotNone(reason)


class TestComputeEntryPrice(unittest.TestCase):
    """Test entry price computation."""
    
    def setUp(self):
        """Set up test price data."""
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        self.price_data = pd.DataFrame({
            "Open": [100 + i for i in range(10)],
            "High": [101 + i for i in range(10)],
            "Low": [99 + i for i in range(10)],
            "Close": [100.5 + i for i in range(10)],
            "Volume": [1_000_000] * 10,
        }, index=dates)
    
    def test_next_open_entry(self):
        """Test entry at next day's open with slippage."""
        signal_date = self.price_data.index[0]  # 2024-01-01
        
        entry_price = compute_entry_price(signal_date, self.price_data, use_next_open=True)
        
        # Next day (2024-01-02) open = 101
        # With 5 bps slippage: 101 * 1.0005 = 101.0505
        expected = 101.0 * 1.0005
        
        self.assertIsNotNone(entry_price)
        self.assertAlmostEqual(entry_price, expected, places=4)
    
    def test_same_day_close_entry(self):
        """Test entry at same day's close (optimistic)."""
        signal_date = self.price_data.index[0]  # 2024-01-01
        
        entry_price = compute_entry_price(signal_date, self.price_data, use_next_open=False)
        
        # Same day (2024-01-01) close = 100.5
        # With 5 bps slippage: 100.5 * 1.0005 = 100.55025
        expected = 100.5 * 1.0005
        
        self.assertIsNotNone(entry_price)
        self.assertAlmostEqual(entry_price, expected, places=4)
    
    def test_no_next_day_available(self):
        """Test when next day is not available."""
        signal_date = self.price_data.index[-1]  # Last day
        
        entry_price = compute_entry_price(signal_date, self.price_data, use_next_open=True)
        
        # Should return None (no next day)
        self.assertIsNone(entry_price)
    
    def test_signal_date_not_in_data(self):
        """Test when signal date is not in price data."""
        signal_date = pd.Timestamp("2024-12-31")  # Not in data
        
        entry_price = compute_entry_price(signal_date, self.price_data)
        
        self.assertIsNone(entry_price)


class TestComputeExitPrice(unittest.TestCase):
    """Test exit price computation."""
    
    def setUp(self):
        """Set up test price data."""
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        self.price_data = pd.DataFrame({
            "Open": [100 + i for i in range(10)],
            "High": [101 + i for i in range(10)],
            "Low": [99 + i for i in range(10)],
            "Close": [100.5 + i for i in range(10)],
            "Volume": [1_000_000] * 10,
        }, index=dates)
    
    def test_open_exit(self):
        """Test exit at open with slippage."""
        exit_date = self.price_data.index[5]
        
        exit_price = compute_exit_price(exit_date, self.price_data, use_next_open=True)
        
        # Day 5 open = 105
        # With 5 bps exit slippage: 105 * 0.9995 = 104.9475
        expected = 105.0 * 0.9995
        
        self.assertIsNotNone(exit_price)
        self.assertAlmostEqual(exit_price, expected, places=4)
    
    def test_close_exit(self):
        """Test exit at close (end of day)."""
        exit_date = self.price_data.index[5]
        
        exit_price = compute_exit_price(exit_date, self.price_data, use_next_open=False)
        
        # Day 5 close = 105.5
        # With 5 bps exit slippage: 105.5 * 0.9995 = 105.4475
        expected = 105.5 * 0.9995
        
        self.assertIsNotNone(exit_price)
        self.assertAlmostEqual(exit_price, expected, places=4)
    
    def test_exit_date_not_in_data(self):
        """Test when exit date is not in price data."""
        exit_date = pd.Timestamp("2024-12-31")  # Not in data
        
        exit_price = compute_exit_price(exit_date, self.price_data)
        
        self.assertIsNone(exit_price)


class TestSlippageCost(unittest.TestCase):
    """Test slippage cost calculation."""
    
    def test_slippage_cost_calculation(self):
        """Test total slippage cost computation."""
        entry_ideal = 100.0
        exit_ideal = 105.0
        entry_realistic = 100.05  # 5 bps worse
        exit_realistic = 104.95   # 5 bps worse
        position_size = 1000  # shares
        
        costs = compute_slippage_cost(
            entry_ideal, exit_ideal, entry_realistic, exit_realistic, position_size
        )
        
        # Entry slippage: (100.05 - 100.0) * 1000 = $50
        # Exit slippage: (105.0 - 104.95) * 1000 = $50
        # Total: $100
        
        self.assertAlmostEqual(costs["entry_slippage_cost"], 50.0, places=2)
        self.assertAlmostEqual(costs["exit_slippage_cost"], 50.0, places=2)
        self.assertAlmostEqual(costs["total_slippage_cost"], 100.0, places=2)
    
    def test_slippage_bps_calculation(self):
        """Test slippage in basis points."""
        entry_ideal = 100.0
        exit_ideal = 100.0
        entry_realistic = 100.05  # 5 bps
        exit_realistic = 99.95    # 5 bps
        position_size = 1
        
        costs = compute_slippage_cost(
            entry_ideal, exit_ideal, entry_realistic, exit_realistic, position_size
        )
        
        self.assertAlmostEqual(costs["entry_slippage_bps"], 5.0, places=1)
        self.assertAlmostEqual(costs["exit_slippage_bps"], 5.0, places=1)


class TestExecutionModel(unittest.TestCase):
    """Test ExecutionModel class."""
    
    def setUp(self):
        """Set up execution model and test data."""
        self.model = ExecutionModel(
            entry_slippage_bps=5,
            exit_slippage_bps=5,
            max_adv_pct=0.05,
            use_next_open=True,
        )
        
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        self.price_data = pd.DataFrame({
            "Open": [100 + i for i in range(10)],
            "Close": [100.5 + i for i in range(10)],
            "Volume": [1_000_000] * 10,
        }, index=dates)
    
    def test_get_entry_price(self):
        """Test get_entry_price method."""
        signal_date = self.price_data.index[0]
        
        entry_price = self.model.get_entry_price(signal_date, self.price_data)
        
        # Next day open with slippage
        expected = 101.0 * 1.0005
        self.assertAlmostEqual(entry_price, expected, places=4)
    
    def test_get_exit_price(self):
        """Test get_exit_price method."""
        exit_date = self.price_data.index[5]
        
        exit_price = self.model.get_exit_price(exit_date, self.price_data)
        
        # Day open with slippage
        expected = 105.0 * 0.9995
        self.assertAlmostEqual(exit_price, expected, places=4)
    
    def test_liquidity_check(self):
        """Test liquidity check method."""
        # Position within limits
        passed, reason = self.model.check_liquidity_for_position(
            position_notional=500_000,
            avg_daily_dollar_volume=10_000_000,
        )
        self.assertTrue(passed)
        self.assertIsNone(reason)
        
        # Position exceeding limits
        passed, reason = self.model.check_liquidity_for_position(
            position_notional=600_000,
            avg_daily_dollar_volume=10_000_000,
        )
        self.assertFalse(passed)
        self.assertIsNotNone(reason)
        self.assertEqual(self.model.trades_rejected_liquidity, 1)
    
    def test_get_summary(self):
        """Test summary generation."""
        summary = self.model.get_summary()
        
        self.assertIn("trades_rejected_liquidity", summary)
        self.assertIn("total_slippage_cost", summary)
        self.assertIn("total_slippage_trades", summary)
        
        self.assertEqual(summary["trades_rejected_liquidity"], 0)
        self.assertEqual(summary["total_slippage_cost"], 0.0)


if __name__ == "__main__":
    unittest.main()
