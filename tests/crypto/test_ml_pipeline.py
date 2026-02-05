"""
Test crypto ML pipeline training and validation.
"""

import pytest
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import pytz

from crypto.ml_pipeline import MLPipeline, TrainingMetrics, ValidationGates
from crypto.artifacts import CryptoArtifactStore
from crypto.universe import CryptoUniverse
from crypto.scheduling import DowntimeScheduler


class MockLedgerStore:
    """Mock ledger store for testing."""
    
    def get_trades(self, symbol, start_date, end_date):
        """Return mock trades."""
        trades = []
        current = start_date
        
        while current < end_date:
            trades.append({
                'timestamp': current.isoformat(),
                'symbol': symbol,
                'quantity': 0.1,
                'price': 50000.0,
                'pnl': 10.0,
            })
            current += timedelta(hours=1)
        
        return trades


class MockDatasetStore:
    """Mock dataset store."""
    pass


class MockLogStore:
    """Mock log store."""
    
    def __init__(self, root):
        self.registry_dir = Path(root) / "logs/registry"
        self.registry_dir.mkdir(parents=True, exist_ok=True)


class TestMLPipeline:
    """Test ML pipeline training and validation."""
    
    @pytest.fixture
    def test_setup(self):
        """Set up test environment."""
        tmpdir = tempfile.mkdtemp()
        
        artifact_store = CryptoArtifactStore(root=f"{tmpdir}/artifacts")
        ledger_store = MockLedgerStore()
        dataset_store = MockDatasetStore()
        log_store = MockLogStore(tmpdir)
        universe = CryptoUniverse()
        downtime_scheduler = DowntimeScheduler()
        
        config = {
            'TRAINING_LOOKBACK_DAYS': 7,
            'VALIDATION_SPLIT': 0.2,
            'MIN_OOS_SHARPE': 0.5,
            'MAX_MAX_DRAWDOWN': 0.15,
            'MAX_TAIL_LOSS': 0.05,
            'MAX_TURNOVER': 2.0,
        }
        
        pipeline = MLPipeline(
            artifact_store=artifact_store,
            ledger_store=ledger_store,
            dataset_store=dataset_store,
            log_store=log_store,
            universe=universe,
            downtime_scheduler=downtime_scheduler,
            config=config,
        )
        
        return {
            'tmpdir': tmpdir,
            'pipeline': pipeline,
            'artifact_store': artifact_store,
            'ledger_store': ledger_store,
        }
    
    def test_should_train_during_downtime(self, test_setup):
        """Test that training starts during downtime window."""
        pipeline = test_setup['pipeline']
        
        # 04:00 UTC = during downtime (03:00-05:00)
        now = datetime(2026, 2, 5, 4, 0, 0, tzinfo=pytz.UTC)
        
        assert pipeline.should_train(now)
    
    def test_should_not_train_outside_downtime(self, test_setup):
        """Test that training doesn't start outside downtime."""
        pipeline = test_setup['pipeline']
        
        # 10:00 UTC = outside downtime
        now = datetime(2026, 2, 5, 10, 0, 0, tzinfo=pytz.UTC)
        
        assert not pipeline.should_train(now)
    
    def test_should_not_train_if_already_training(self, test_setup):
        """Test that training doesn't start if already in progress."""
        pipeline = test_setup['pipeline']
        pipeline.training_in_progress = True
        
        # During downtime but already training
        now = datetime(2026, 2, 5, 4, 0, 0, tzinfo=pytz.UTC)
        
        assert not pipeline.should_train(now)
    
    def test_train_model_success(self, test_setup):
        """Test successful model training."""
        pipeline = test_setup['pipeline']
        now = datetime(2026, 2, 5, 4, 0, 0, tzinfo=pytz.UTC)
        
        success, model_id = pipeline.train_model(now)
        
        assert success
        assert model_id.startswith('crypto_kraken_model_')
        assert pipeline.latest_candidate_id == model_id
        assert not pipeline.training_in_progress
    
    def test_model_id_generation(self, test_setup):
        """Test model ID generation."""
        pipeline = test_setup['pipeline']
        now = datetime(2026, 2, 5, 14, 30, 45, tzinfo=pytz.UTC)
        
        model_id = pipeline._generate_model_id(now)
        
        assert 'crypto_kraken_model_' in model_id
        assert '20260205' in model_id  # Date part
        assert '143045' in model_id    # Time part
    
    def test_feature_extraction(self, test_setup):
        """Test feature extraction from trades."""
        pipeline = test_setup['pipeline']
        
        trades = [
            {
                'timestamp': datetime(2026, 2, 5, 10, 0, 0).isoformat(),
                'symbol': 'BTC',
                'quantity': 0.5,
                'price': 50000.0,
                'pnl': 100.0,
            },
            {
                'timestamp': datetime(2026, 2, 5, 10, 30, 0).isoformat(),
                'symbol': 'ETH',
                'quantity': 2.0,
                'price': 3000.0,
                'pnl': 50.0,
            },
        ]
        
        now = datetime(2026, 2, 5, 11, 0, 0, tzinfo=pytz.UTC)
        features = pipeline._extract_features(trades, now)
        
        assert len(features) > 0
        assert all(isinstance(f, list) for f in features)
        assert all(len(f) == 5 for f in features)  # 5 features per window
    
    def test_data_splitting(self, test_setup):
        """Test train/validation split."""
        pipeline = test_setup['pipeline']
        
        features = [
            [1.0, 2.0, 3.0, 4.0, 5.0],
            [2.0, 3.0, 4.0, 5.0, 6.0],
            [3.0, 4.0, 5.0, 6.0, 7.0],
            [4.0, 5.0, 6.0, 7.0, 8.0],
            [5.0, 6.0, 7.0, 8.0, 9.0],
        ]
        
        train, val = pipeline._split_data(features)
        
        # 80/20 split
        assert len(train) == 4
        assert len(val) == 1
        assert len(train) + len(val) == len(features)
    
    def test_model_training(self, test_setup):
        """Test candidate model training."""
        pipeline = test_setup['pipeline']
        
        train_features = [
            [1.0, 2.0, 3.0, 4.0, 5.0],
            [2.0, 3.0, 4.0, 5.0, 6.0],
        ]
        
        weights = pipeline._train_candidate(train_features)
        
        assert len(weights) == 5  # Same as feature count
        assert all(isinstance(w, float) for w in weights)
    
    def test_model_evaluation(self, test_setup):
        """Test model evaluation metrics."""
        pipeline = test_setup['pipeline']
        
        weights = [1.0, 2.0, 3.0, 4.0, 5.0]
        val_features = [
            [1.0, 1.0, 1.0, 1.0, 1.0],
            [2.0, 2.0, 2.0, 2.0, 2.0],
        ]
        
        metrics = pipeline._evaluate_model(weights, val_features)
        
        assert isinstance(metrics, TrainingMetrics)
        assert metrics.sharpe_ratio > 0.0
        assert metrics.max_drawdown > 0.0
        assert metrics.win_rate > 0.0
    
    def test_validation_gates_pass(self, test_setup):
        """Test validation gates when all pass."""
        pipeline = test_setup['pipeline']
        artifact_store = test_setup['artifact_store']
        
        # Create a valid candidate
        model_id = 'test_model_001'
        model_data = {'weights': [1.0, 2.0, 3.0]}
        metadata = {'version': '1.0'}
        metrics = {'sharpe': 0.8}
        
        artifact_store.save_candidate(model_id, model_data, metadata, metrics)
        
        # Evaluate with good metrics
        train_metrics = TrainingMetrics()
        train_metrics.sharpe_ratio = 0.9  # > 0.5 min
        train_metrics.max_drawdown = 0.10  # < 0.15 max
        train_metrics.turnover_ratio = 1.5  # < 2.0 max
        
        result = pipeline._validate_candidate(model_id, train_metrics)
        
        assert result['passed']
        assert result['checks'][ValidationGates.INTEGRITY_CHECK]
        assert result['checks'][ValidationGates.SCHEMA_CHECK]
    
    def test_validation_gates_fail_sharpe(self, test_setup):
        """Test validation fails on low Sharpe ratio."""
        pipeline = test_setup['pipeline']
        artifact_store = test_setup['artifact_store']
        
        model_id = 'test_model_low_sharpe'
        model_data = {'weights': [1.0]}
        artifact_store.save_candidate(model_id, model_data, {}, {})
        
        train_metrics = TrainingMetrics()
        train_metrics.sharpe_ratio = 0.3  # < 0.5 min
        train_metrics.max_drawdown = 0.10
        
        result = pipeline._validate_candidate(model_id, train_metrics)
        
        assert not result['passed']
        assert any('Sharpe' in f or 'sharpe' in f for f in result['failures'])
    
    def test_validation_gates_fail_drawdown(self, test_setup):
        """Test validation fails on high max drawdown."""
        pipeline = test_setup['pipeline']
        artifact_store = test_setup['artifact_store']
        
        model_id = 'test_model_high_dd'
        model_data = {'weights': [1.0]}
        artifact_store.save_candidate(model_id, model_data, {}, {})
        
        train_metrics = TrainingMetrics()
        train_metrics.sharpe_ratio = 0.8
        train_metrics.max_drawdown = 0.20  # > 0.15 max
        
        result = pipeline._validate_candidate(model_id, train_metrics)
        
        assert not result['passed']
        assert any('drawdown' in f.lower() for f in result['failures'])
    
    def test_mark_ready_for_promotion(self, test_setup):
        """Test marking model ready for promotion."""
        pipeline = test_setup['pipeline']
        artifact_store = test_setup['artifact_store']
        
        model_id = 'test_model_ready'
        artifact_store.save_candidate(
            model_id,
            {'weights': [1.0]},
            {},
            {},
        )
        
        pipeline._mark_ready_for_promotion(model_id)
        
        # Check that ready file exists
        ready_file = artifact_store.validations_dir / f"{model_id}.ready"
        assert ready_file.exists()
        
        # Verify contents
        with open(ready_file, 'r') as f:
            data = json.load(f)
        
        assert data['model_id'] == model_id
        assert data['ready_for_promotion']
    
    def test_training_event_logging(self, test_setup):
        """Test training event logging to registry."""
        pipeline = test_setup['pipeline']
        
        model_id = 'test_model_001'
        pipeline.log_training_event(model_id, success=True, message="Training completed")
        
        # Verify logged
        registry_file = pipeline.log_store.registry_dir / "training_registry.jsonl"
        assert registry_file.exists()
        
        with open(registry_file, 'r') as f:
            lines = f.readlines()
        
        assert len(lines) > 0
        
        last_event = json.loads(lines[-1])
        assert last_event['model_id'] == model_id
        assert last_event['success']
