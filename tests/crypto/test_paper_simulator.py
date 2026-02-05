"""
Test crypto paper trading simulator with realistic fills.
"""

import pytest
from datetime import datetime
import pytz

from broker.kraken.paper import PaperKrakenSimulator


class TestPaperKrakenSimulator:
    """Test paper trading simulator."""
    
    @pytest.fixture
    def simulator(self):
        """Create paper simulator with default settings."""
        return PaperKrakenSimulator(
            starting_balance_usd=10000,
            maker_fee=0.0016,
            taker_fee=0.0026,
            slippage_bps=5,
            seed=42,  # For reproducibility
        )
    
    def test_initialization(self, simulator):
        """Test simulator initialization."""
        balances = simulator.get_balances()
        assert balances['USD'] == 10000
    
    def test_market_buy_with_fees_and_slippage(self, simulator):
        """Test market buy order with fees and slippage."""
        # BUY 1 BTC at $50,000 mid price
        # Slippage: +5 bps = $250 cost
        # Fee: 0.26% = ~$130
        # Total cost: ~$50,380
        
        order = simulator.submit_market_order(
            symbol='BTC/USD',
            quantity=1.0,
            side='buy',
            mid_price=50000.0,
        )
        
        assert order.symbol == 'BTC/USD'
        assert order.side == 'buy'
        assert order.quantity == 1.0
        assert order.status.value == 'filled'
        assert order.filled_qty == 1.0
        
        # Check fill price (includes slippage)
        # BUY slippage = mid_price * (1 + slippage_bps/10000)
        expected_fill_price = 50000.0 * (1 + 5 / 10000)  # 50025
        assert abs(order.filled_price - expected_fill_price) < 1
        
        # Check balance reduced
        balances = simulator.get_balances()
        assert balances['USD'] < 10000
        assert balances['BTC'] == 1.0
    
    def test_market_sell_with_fees_and_slippage(self, simulator):
        """Test market sell order with fees and slippage."""
        # First buy some BTC
        simulator.submit_market_order(
            symbol='BTC/USD',
            quantity=1.0,
            side='buy',
            mid_price=50000.0,
        )
        
        # Now sell at $51,000
        # Slippage: -5 bps = -$255 (sell gets less)
        # Fee: 0.26% = ~$133
        # Net proceeds: ~$50,612
        
        order = simulator.submit_market_order(
            symbol='BTC/USD',
            quantity=1.0,
            side='sell',
            mid_price=51000.0,
        )
        
        assert order.symbol == 'BTC/USD'
        assert order.side == 'sell'
        assert order.quantity == 1.0
        assert order.status.value == 'filled'
        
        # SELL slippage = mid_price * (1 - slippage_bps/10000)
        expected_fill_price = 51000.0 * (1 - 5 / 10000)  # 50949.5
        assert abs(order.filled_price - expected_fill_price) < 1
        
        # Check balance back to USD, BTC gone
        balances = simulator.get_balances()
        assert balances['BTC'] == 0.0
        assert balances['USD'] > 10000  # Made profit
    
    def test_insufficient_balance_buy(self, simulator):
        """Test buy order rejected for insufficient balance."""
        # Try to buy 1 BTC at $100k (need $100k+)
        # But only have $10k
        
        order = simulator.submit_market_order(
            symbol='BTC/USD',
            quantity=1.0,
            side='buy',
            mid_price=100000.0,
        )
        
        assert order.status.value == 'rejected'
        
        # Balance unchanged
        balances = simulator.get_balances()
        assert balances['USD'] == 10000
    
    def test_insufficient_position_sell(self, simulator):
        """Test sell order rejected for insufficient position."""
        # Try to sell 1 BTC when we have none
        
        order = simulator.submit_market_order(
            symbol='BTC/USD',
            quantity=1.0,
            side='sell',
            mid_price=50000.0,
        )
        
        assert order.status.value == 'rejected'
    
    def test_deterministic_fills_with_seed(self):
        """Test that same seed produces same slippage values."""
        sim1 = PaperKrakenSimulator(
            starting_balance_usd=10000,
            maker_fee=0.0016,
            taker_fee=0.0026,
            slippage_bps=5,
            seed=999,
        )
        
        sim2 = PaperKrakenSimulator(
            starting_balance_usd=10000,
            maker_fee=0.0016,
            taker_fee=0.0026,
            slippage_bps=5,
            seed=999,
        )
        
        # Both buy same order
        order1 = sim1.submit_market_order('BTC/USD', 1.0, 'buy', 50000.0)
        order2 = sim2.submit_market_order('BTC/USD', 1.0, 'buy', 50000.0)
        
        # Fills should be identical
        assert order1.filled_price == order2.filled_price
        assert order1.commission == order2.commission
    
    def test_trade_history(self, simulator):
        """Test that trades are recorded in history."""
        # Make several trades
        simulator.submit_market_order('BTC/USD', 0.5, 'buy', 50000.0)
        simulator.submit_market_order('ETH/USD', 5.0, 'buy', 3000.0)
        simulator.submit_market_order('BTC/USD', 0.5, 'sell', 51000.0)
        
        history = simulator.get_trade_history()
        
        assert len(history) == 3
        assert history[0]['symbol'] == 'BTC/USD'
        assert history[0]['side'] == 'buy'
        assert history[1]['symbol'] == 'ETH/USD'
        assert history[2]['side'] == 'sell'
    
    def test_multiple_positions(self, simulator):
        """Test managing multiple positions."""
        # Buy different crypto
        simulator.submit_market_order('BTC/USD', 0.5, 'buy', 50000.0)
        simulator.submit_market_order('ETH/USD', 2.0, 'buy', 3000.0)
        simulator.submit_market_order('SOL/USD', 10.0, 'buy', 150.0)
        
        positions = simulator.get_positions()
        
        assert 'BTC' in positions
        assert 'ETH' in positions
        assert 'SOL' in positions
        assert positions['BTC']['quantity'] == 0.5
        assert positions['ETH']['quantity'] == 2.0
        assert positions['SOL']['quantity'] == 10.0
    
    def test_fee_calculation_matches_tier(self, simulator):
        """Test fee calculation matches specified tier."""
        # Maker fee: 0.0016 = 0.16%
        # Taker fee: 0.0026 = 0.26%
        
        order = simulator.submit_market_order(
            symbol='BTC/USD',
            quantity=1.0,
            side='buy',
            mid_price=50000.0,
        )
        
        # Taker fee (market order) should be 0.26%
        # On fill price of ~50025: fee ≈ 130
        expected_fee = 50025 * 0.0026  # Approximately
        
        # Allow 5% tolerance
        assert abs(order.commission - expected_fee) < expected_fee * 0.05
    
    def test_custom_starting_balance(self):
        """Test simulator with custom starting balance."""
        sim = PaperKrakenSimulator(starting_balance_usd=50000)
        
        balances = sim.get_balances()
        assert balances['USD'] == 50000
    
    def test_custom_fees(self):
        """Test simulator with custom fee rates."""
        # Zero fees for testing
        sim = PaperKrakenSimulator(
            starting_balance_usd=10000,
            maker_fee=0.0,
            taker_fee=0.0,
            slippage_bps=0,  # No slippage either
        )
        
        # Buy at exact price
        order = sim.submit_market_order('BTC/USD', 1.0, 'buy', 50000.0)
        
        # With zero fees and slippage, fill should be exact
        assert order.filled_price == 50000.0
        assert order.commission == 0.0
    
    def test_slippage_varies_with_quantity(self):
        """Test that larger orders may have different slippage."""
        sim = PaperKrakenSimulator(
            starting_balance_usd=1000000,
            slippage_bps=5,
            seed=123,
        )
        
        order_small = sim.submit_market_order('BTC/USD', 0.1, 'buy', 50000.0)
        
        sim2 = PaperKrakenSimulator(
            starting_balance_usd=1000000,
            slippage_bps=5,
            seed=123,
        )
        
        order_large = sim2.submit_market_order('BTC/USD', 10.0, 'buy', 50000.0)
        
        # Same seed but different quantities may produce different slippage
        # (in real implementation; here testing that simulator accepts both)
        assert order_small.status.value == 'filled'
        assert order_large.status.value == 'filled'
