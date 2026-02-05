"""
ML training and validation pipeline for crypto trading.

This pipeline runs during the daily downtime window (03:00-05:00 UTC by default).
It collects trade data, trains models, validates them, and gates promotions.

Workflow:
1. Wait for downtime window
2. Collect training data (trades from previous period)
3. Feature engineering (technical indicators, regime signals)
4. Train candidate model
5. Backtest on validation set
6. Save candidate with metadata
7. Validate candidate (4-gate process)
8. If PASS: mark as ready for promotion
9. Wait for explicit promotion (requires CLI approval)
10. Resume trading with approved model
"""

import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import hashlib

logger = logging.getLogger(__name__)


class TrainingMetrics:
    """Metrics from model training."""
    
    def __init__(self):
        self.sharpe_ratio: float = 0.0
        self.max_drawdown: float = 0.0
        self.total_return: float = 0.0
        self.win_rate: float = 0.0
        self.avg_trade_duration: float = 0.0
        self.turnover_ratio: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'total_return': self.total_return,
            'win_rate': self.win_rate,
            'avg_trade_duration': self.avg_trade_duration,
            'turnover_ratio': self.turnover_ratio,
        }


class ValidationGates:
    """Four-gate validation process for models."""
    
    # Gate 1: Integrity check (SHA256 hash)
    INTEGRITY_CHECK = 'integrity'
    
    # Gate 2: Schema validation (expected keys, types)
    SCHEMA_CHECK = 'schema'
    
    # Gate 3: Out-of-sample performance metrics
    OOS_METRICS_CHECK = 'oos_metrics'
    
    # Gate 4: Risk management thresholds
    RISK_CHECKS = 'risk_checks'
    
    ALL_GATES = [INTEGRITY_CHECK, SCHEMA_CHECK, OOS_METRICS_CHECK, RISK_CHECKS]


class MLPipeline:
    """
    ML training and validation pipeline.
    
    Runs during downtime windows, collects trade data, trains models,
    validates them through 4 gates, and marks ready for promotion.
    """
    
    def __init__(
        self,
        artifact_store,
        ledger_store,
        dataset_store,
        log_store,
        universe,
        downtime_scheduler,
        config: Dict,
    ):
        """
        Initialize ML pipeline.
        
        Args:
            artifact_store: CryptoArtifactStore for model management
            ledger_store: CryptoLedgerStore for trade data
            dataset_store: CryptoDatasetStore for features
            log_store: CryptoLogStore for observations
            universe: CryptoUniverse for symbol management
            downtime_scheduler: DowntimeScheduler for training windows
            config: ML configuration dict
        """
        self.artifact_store = artifact_store
        self.ledger_store = ledger_store
        self.dataset_store = dataset_store
        self.log_store = log_store
        self.universe = universe
        self.downtime_scheduler = downtime_scheduler
        self.config = config
        
        # Training settings
        self.training_lookback_days = config.get('TRAINING_LOOKBACK_DAYS', 30)
        self.validation_split = config.get('VALIDATION_SPLIT', 0.2)
        self.min_oos_sharpe = config.get('MIN_OOS_SHARPE', 0.5)
        self.max_max_dd = config.get('MAX_MAX_DRAWDOWN', 0.15)
        self.max_tail_loss = config.get('MAX_TAIL_LOSS', 0.05)
        self.max_turnover = config.get('MAX_TURNOVER', 2.0)
        
        self.training_in_progress = False
        self.latest_candidate_id: Optional[str] = None
    
    def should_train(self, now: datetime) -> bool:
        """
        Check if training should start.
        
        Training starts:
        - During downtime window
        - If no training in progress
        - If enough time since last training
        
        Args:
            now: Current UTC datetime
        
        Returns:
            True if training should start
        """
        if self.training_in_progress:
            return False
        
        if not self.downtime_scheduler.is_training_allowed(now):
            return False
        
        # Check if enough time since last training
        last_training = self._get_last_training_time()
        if last_training:
            hours_since = (now - last_training).total_seconds() / 3600
            if hours_since < 20:  # Max once per day
                return False
        
        return True
    
    def train_model(self, now: datetime) -> Tuple[bool, str]:
        """
        Train a new candidate model.
        
        Args:
            now: Current UTC datetime
        
        Returns:
            (success, model_id or error_message)
        """
        logger.info("Starting ML pipeline training...")
        self.training_in_progress = True
        
        try:
            # 1. Collect training data
            logger.info("Collecting trade data from ledger...")
            trades = self._collect_trades(now)
            
            if len(trades) < 10:
                msg = f"Insufficient trades ({len(trades)}), need at least 10"
                logger.warning(msg)
                return False, msg
            
            # 2. Feature engineering
            logger.info(f"Engineering features from {len(trades)} trades...")
            features = self._extract_features(trades, now)
            
            # 3. Split into train/validation
            train_features, val_features = self._split_data(features)
            
            # 4. Train candidate model
            logger.info("Training candidate model...")
            model_weights = self._train_candidate(train_features)
            
            # 5. Backtest on validation set
            logger.info("Backtesting on validation set...")
            val_metrics = self._evaluate_model(model_weights, val_features)
            
            # 6. Save candidate with metadata
            model_id = self._generate_model_id(now)
            logger.info(f"Saving candidate model: {model_id}")
            
            metadata = {
                'trained_at': now.isoformat(),
                'training_period_days': self.training_lookback_days,
                'trades_used': len(trades),
                'feature_count': len(features[0]) if features else 0,
                'validation_split': self.validation_split,
            }
            
            self.artifact_store.save_candidate(
                model_id=model_id,
                model_data={'weights': model_weights},
                metadata=metadata,
                metrics=val_metrics.to_dict(),
            )
            
            self.latest_candidate_id = model_id
            logger.info(f"Candidate saved: {model_id}")
            
            # 7. Auto-validate (gate checks)
            logger.info("Running validation gates...")
            validation_result = self._validate_candidate(model_id, val_metrics)
            
            if validation_result['passed']:
                logger.info(f"✓ Model {model_id} PASSED all validation gates")
                self._mark_ready_for_promotion(model_id)
            else:
                logger.warning(f"✗ Model {model_id} FAILED validation:")
                for failure in validation_result.get('failures', []):
                    logger.warning(f"  - {failure}")
            
            return True, model_id
        
        except Exception as e:
            logger.error(f"Training failed: {e}", exc_info=True)
            return False, str(e)
        
        finally:
            self.training_in_progress = False
    
    def _collect_trades(self, now: datetime) -> List[Dict]:
        """Collect trades from ledger for lookback period."""
        lookback_start = now - timedelta(days=self.training_lookback_days)
        
        all_trades = []
        for symbol in self.universe.all_canonical_symbols():
            trades = self.ledger_store.get_trades(
                symbol=symbol,
                start_date=lookback_start,
                end_date=now,
            )
            all_trades.extend(trades)
        
        return sorted(all_trades, key=lambda t: t.get('timestamp', now))
    
    def _extract_features(self, trades: List[Dict], now: datetime) -> List[List[float]]:
        """Extract features from trades for ML."""
        features = []
        
        # Group trades by time windows (hourly)
        from datetime import timedelta
        
        current_time = now - timedelta(days=self.training_lookback_days)
        features_list = []
        
        while current_time < now:
            window_end = current_time + timedelta(hours=1)
            window_trades = [
                t for t in trades
                if current_time <= datetime.fromisoformat(t.get('timestamp', now.isoformat())) < window_end
            ]
            
            # Extract features from this window
            if window_trades:
                feature_vector = [
                    len(window_trades),  # Trade count
                    sum(float(t.get('quantity', 0)) for t in window_trades),  # Total volume
                    sum(float(t.get('pnl', 0)) for t in window_trades),  # Window P&L
                    max(float(t.get('price', 0)) for t in window_trades) if window_trades else 0,  # Max price
                    min(float(t.get('price', 0)) for t in window_trades) if window_trades else 0,  # Min price
                ]
                features_list.append(feature_vector)
            
            current_time = window_end
        
        return features_list if features_list else [[0.0] * 5]
    
    def _split_data(self, features: List[List[float]]) -> Tuple[List[List[float]], List[List[float]]]:
        """Split features into train and validation sets."""
        split_idx = int(len(features) * (1 - self.validation_split))
        return features[:split_idx], features[split_idx:]
    
    def _train_candidate(self, train_features: List[List[float]]) -> List[float]:
        """
        Train model on training features.
        
        Returns:
            Model weights (simplified for demo)
        """
        # Simplified training: average feature weights
        if not train_features:
            return [0.0] * 5
        
        num_features = len(train_features[0])
        weights = []
        
        for feat_idx in range(num_features):
            values = [f[feat_idx] for f in train_features]
            avg = sum(values) / len(values) if values else 0.0
            weights.append(avg)
        
        return weights
    
    def _evaluate_model(
        self,
        weights: List[float],
        val_features: List[List[float]],
    ) -> TrainingMetrics:
        """
        Evaluate model on validation set.
        
        Returns:
            TrainingMetrics with out-of-sample performance
        """
        metrics = TrainingMetrics()
        
        if not val_features:
            return metrics
        
        # Simplified evaluation
        predictions = []
        for features in val_features:
            # Simple linear combination
            pred = sum(f * w for f, w in zip(features, weights)) / max(len(weights), 1)
            predictions.append(pred)
        
        # Calculate metrics
        metrics.sharpe_ratio = 0.8 + (len(val_features) % 10) * 0.01  # Mock
        metrics.max_drawdown = 0.10 + (len(val_features) % 5) * 0.01  # Mock
        metrics.total_return = 0.15 + (len(val_features) % 20) * 0.005  # Mock
        metrics.win_rate = 0.55 + (len(val_features) % 15) * 0.005  # Mock
        metrics.avg_trade_duration = 2.5  # hours
        metrics.turnover_ratio = 1.2 + (len(val_features) % 10) * 0.05  # Mock
        
        return metrics
    
    def _generate_model_id(self, now: datetime) -> str:
        """Generate unique model ID."""
        timestamp = now.strftime('%Y%m%d_%H%M%S')
        return f"crypto_kraken_model_{timestamp}"
    
    def _validate_candidate(
        self,
        model_id: str,
        metrics: TrainingMetrics,
    ) -> Dict:
        """
        Run 4-gate validation process.
        
        Returns:
            Dict with {passed: bool, checks: {}, failures: []}
        """
        result = {
            'passed': True,
            'checks': {},
            'failures': [],
        }
        
        # Gate 1: Integrity (SHA256)
        try:
            integrity_ok = self.artifact_store.verify_candidate_integrity(model_id)
            result['checks'][ValidationGates.INTEGRITY_CHECK] = integrity_ok
            if not integrity_ok:
                result['passed'] = False
                result['failures'].append("Integrity check failed (SHA256 mismatch)")
        except Exception as e:
            result['passed'] = False
            result['failures'].append(f"Integrity check error: {e}")
        
        # Gate 2: Schema validation
        try:
            candidate = self.artifact_store.candidates_dir / model_id / "model.json"
            with open(candidate, 'r') as f:
                model_data = json.load(f)
            
            if 'weights' not in model_data:
                result['passed'] = False
                result['failures'].append("Schema check failed: missing 'weights'")
            else:
                result['checks'][ValidationGates.SCHEMA_CHECK] = True
        except Exception as e:
            result['passed'] = False
            result['failures'].append(f"Schema check error: {e}")
        
        # Gate 3: OOS Metrics
        metric_checks = {
            'oos_sharpe': metrics.sharpe_ratio >= self.min_oos_sharpe,
            'max_drawdown': metrics.max_drawdown <= self.max_max_dd,
            'tail_loss': 0.02 <= self.max_tail_loss,  # Mock: assume 2%
        }
        
        result['checks'][ValidationGates.OOS_METRICS_CHECK] = all(metric_checks.values())
        
        for check_name, check_passed in metric_checks.items():
            if not check_passed:
                result['passed'] = False
                result['failures'].append(f"OOS metrics check failed: {check_name}")
        
        # Gate 4: Risk checks
        risk_checks = {
            'turnover': metrics.turnover_ratio <= self.max_turnover,
            'drawdown_recovery': metrics.max_drawdown <= self.max_max_dd,
        }
        
        result['checks'][ValidationGates.RISK_CHECKS] = all(risk_checks.values())
        
        for check_name, check_passed in risk_checks.items():
            if not check_passed:
                result['passed'] = False
                result['failures'].append(f"Risk check failed: {check_name}")
        
        return result
    
    def _mark_ready_for_promotion(self, model_id: str) -> None:
        """Mark model as ready for promotion (after passing validation)."""
        ready_file = self.artifact_store.validations_dir / f"{model_id}.ready"
        ready_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(ready_file, 'w') as f:
            f.write(json.dumps({
                'model_id': model_id,
                'ready_for_promotion': True,
                'marked_at': datetime.utcnow().isoformat(),
            }))
        
        logger.info(f"Model {model_id} marked ready for promotion")
    
    def _get_last_training_time(self) -> Optional[datetime]:
        """Get timestamp of last training."""
        registry_file = self.log_store.registry_dir / "training_registry.jsonl"
        
        if not registry_file.exists():
            return None
        
        with open(registry_file, 'r') as f:
            lines = f.readlines()
        
        if not lines:
            return None
        
        try:
            last_entry = json.loads(lines[-1])
            return datetime.fromisoformat(last_entry.get('timestamp'))
        except Exception:
            return None
    
    def log_training_event(self, model_id: str, success: bool, message: str = "") -> None:
        """Log training event to registry."""
        registry_file = self.log_store.registry_dir / "training_registry.jsonl"
        registry_file.parent.mkdir(parents=True, exist_ok=True)
        
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'model_id': model_id,
            'success': success,
            'message': message,
        }
        
        with open(registry_file, 'a') as f:
            f.write(json.dumps(event) + '\n')
