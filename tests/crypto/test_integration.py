"""
Integration test guide for crypto trading system.

This module provides step-by-step integration tests for the entire crypto system,
validating that all components work together correctly.

Test Phases:
1. Unit tests (individual components)
2. Integration tests (component interactions)
3. End-to-end tests (full system workflows)
4. Chaos tests (edge cases, error handling)
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
import pytz

from crypto.artifacts import CryptoArtifactStore
from crypto.universe import CryptoUniverse
from crypto.scheduling import DowntimeScheduler
from crypto.regime import CryptoRegimeEngine
from crypto.strategies import StrategySelector
from broker.kraken.paper import PaperKrakenSimulator
from crypto.ml_pipeline import MLPipeline


class TestIntegrationArtifactLifecycle:
    """Test complete artifact lifecycle."""
    
    @pytest.fixture
    def artifact_store(self):
        """Create artifact store for testing."""
        tmpdir = tempfile.mkdtemp()
        return CryptoArtifactStore(root=f"{tmpdir}/crypto")
    
    def test_candidate_to_approved_workflow(self, artifact_store):
        """Test workflow from candidate creation to approval."""
        # 1. Create candidate
        model_id = 'model_v1'
        model_data = {'weights': [0.5, 0.3, 0.2]}
        metadata = {'version': '1.0', 'features': ['rsi', 'macd', 'bb']}
        metrics = {'sharpe': 0.8, 'dd': 0.12}
        
        artifact_store.save_candidate(model_id, model_data, metadata, metrics)
        
        # 2. Verify integrity
        assert artifact_store.verify_candidate_integrity(model_id)
        
        # 3. Create validation record
        validation_result = {
            'model_id': model_id,
            'passed': True,
            'timestamp': datetime.utcnow().isoformat(),
        }
        
        with open(artifact_store.validations_dir / f"{model_id}.json", 'w') as f:
            json.dump(validation_result, f)
        
        # 4. Create approved pointer
        approved_pointer = {
            'model_id': model_id,
            'promoted_at': datetime.utcnow().isoformat(),
        }
        
        with open(artifact_store.models_dir / "approved_model.json", 'w') as f:
            json.dump(approved_pointer, f)
        
        # 5. Load and verify
        loaded = artifact_store.load_approved_model()
        assert loaded['model_id'] == model_id


class TestIntegrationTradingCycle:
    """Test complete trading cycle."""
    
    @pytest.fixture
    def trading_setup(self):
        """Set up trading environment."""
        simulator = PaperKrakenSimulator(
            starting_balance_usd=50000,
            maker_fee=0.0016,
            taker_fee=0.0026,
            slippage_bps=5,
            seed=42,
        )
        
        universe = CryptoUniverse()
        scheduler = DowntimeScheduler()
        regime_engine = CryptoRegimeEngine()
        strategy_selector = StrategySelector(max_concurrent=2)
        
        return {
            'simulator': simulator,
            'universe': universe,
            'scheduler': scheduler,
            'regime_engine': regime_engine,
            'strategy_selector': strategy_selector,
        }
    
    def test_market_entry_and_exit(self, trading_setup):
        """Test entering and exiting trades."""
        sim = trading_setup['simulator']
        
        # Entry: Buy 0.5 BTC at $50k
        entry = sim.submit_market_order('BTC/USD', 0.5, 'buy', 50000.0)
        assert entry.status.value == 'filled'
        assert entry.filled_qty == 0.5
        
        # Check position
        positions = sim.get_positions()
        assert positions['BTC']['quantity'] == 0.5
        
        # Exit: Sell at $52k (profit)
        exit_order = sim.submit_market_order('BTC/USD', 0.5, 'sell', 52000.0)
        assert exit_order.status.value == 'filled'
        
        # Position closed
        positions = sim.get_positions()
        assert positions['BTC']['quantity'] == 0.0
    
    def test_multi_asset_trading(self, trading_setup):
        """Test trading multiple assets simultaneously."""
        sim = trading_setup['simulator']
        
        # Buy multiple assets
        bt_order = sim.submit_market_order('BTC/USD', 0.2, 'buy', 50000.0)
        eth_order = sim.submit_market_order('ETH/USD', 2.0, 'buy', 3000.0)
        sol_order = sim.submit_market_order('SOL/USD', 20.0, 'buy', 150.0)
        
        assert bt_order.status.value == 'filled'
        assert eth_order.status.value == 'filled'
        assert sol_order.status.value == 'filled'
        
        # Verify portfolio
        balances = sim.get_balances()
        assert 'BTC' in balances
        assert 'ETH' in balances
        assert 'SOL' in balances
        assert balances['USD'] < 50000  # Reduced by purchases


class TestIntegrationSchedulingAndTraining:
    """Test scheduling and ML training integration."""
    
    def test_downtime_window_enforcement(self):
        """Test that trading is blocked during downtime."""
        scheduler = DowntimeScheduler()
        
        # Trading time: 10:00 UTC
        trading_time = datetime(2026, 2, 5, 10, 0, 0, tzinfo=pytz.UTC)
        assert scheduler.is_trading_allowed(trading_time)
        assert not scheduler.is_training_allowed(trading_time)
        
        # Downtime: 04:00 UTC
        downtime = datetime(2026, 2, 5, 4, 0, 0, tzinfo=pytz.UTC)
        assert not scheduler.is_trading_allowed(downtime)
        assert scheduler.is_training_allowed(downtime)


class TestIntegrationRegimeAndStrategy:
    """Test regime detection and strategy selection."""
    
    def test_regime_strategy_mapping(self):
        """Test that strategies are selected based on regime."""
        from crypto.regime import MarketRegime
        
        selector = StrategySelector(max_concurrent=2)
        
        # During RISK_ON, should prefer growth strategies
        available_capital = 10000
        
        # Allocations should sum to available capital
        allocations = selector.select_strategies(
            regime=MarketRegime.RISK_ON,
            available_capital=available_capital,
        )
        
        total_allocated = sum(a.capital_allocation for a in allocations)
        assert total_allocated <= available_capital
        assert len(allocations) <= 2  # Max concurrent


class TestIntegrationErrorHandling:
    """Test error handling across system."""
    
    def test_insufficient_balance_cascade(self):
        """Test that insufficient balance errors cascade properly."""
        sim = PaperKrakenSimulator(starting_balance_usd=100)
        
        # Try to buy expensive BTC
        order = sim.submit_market_order('BTC/USD', 1.0, 'buy', 50000.0)
        
        assert order.status.value == 'rejected'
        
        # Balance unchanged
        assert sim.get_balances()['USD'] == 100
    
    def test_invalid_symbol_handling(self):
        """Test handling of invalid symbols."""
        universe = CryptoUniverse()
        
        # Should raise KeyError for non-existent symbol
        with pytest.raises(KeyError):
            universe.get_kraken_pair('INVALID_SYMBOL')
    
    def test_artifact_isolation_guardrails(self):
        """Test that artifact store enforces isolation."""
        tmpdir = tempfile.mkdtemp()
        
        # Try to create store pointing to swing directory
        with pytest.raises(ValueError, match="swing"):
            CryptoArtifactStore(root=f"{tmpdir}/swing/artifacts")


class TestIntegrationFullWorkflow:
    """Test complete end-to-end workflow."""
    
    def test_startup_to_trading_sequence(self):
        """Test startup sequence and initial trading."""
        # 1. Initialize components
        universe = CryptoUniverse()
        scheduler = DowntimeScheduler()
        sim = PaperKrakenSimulator(starting_balance_usd=10000)
        
        # 2. Verify startup state
        assert len(universe.all_canonical_symbols()) > 0
        assert sim.get_balances()['USD'] == 10000
        
        # 3. Attempt trading (trading hours)
        now = datetime(2026, 2, 5, 10, 0, 0, tzinfo=pytz.UTC)
        assert scheduler.is_trading_allowed(now)
        
        # 4. Execute first trade
        order = sim.submit_market_order('BTC/USD', 0.1, 'buy', 50000.0)
        assert order.status.value == 'filled'
        
        # 5. Verify state after trade
        balances = sim.get_balances()
        assert balances['BTC'] == 0.1
        assert balances['USD'] < 10000
