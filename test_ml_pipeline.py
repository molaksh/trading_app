"""
Integration tests for ML validation pipeline.

Tests:
1. Training pipeline (load → prepare → split → train → evaluate)
2. Prediction pipeline (probability → confidence mapping)
3. ML vs Rules comparison on backtest
"""

import logging
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

from ml.train_model import (
    load_dataset,
    prepare_features,
    time_based_split,
    train_model,
    evaluate_model,
    train_and_evaluate,
)
from ml.predict import (
    probability_to_confidence,
    predict_probabilities,
    predict_confidence_scores,
    predict_with_probabilities,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestDataLoading(unittest.TestCase):
    """Test dataset loading."""
    
    def test_load_dataset_csv(self):
        """Test loading CSV dataset."""
        dataset_path = "./data/ml_dataset_20260124_032739.csv"
        
        # Skip if dataset doesn't exist
        if not Path(dataset_path).exists():
            self.skipTest(f"Dataset not found: {dataset_path}")
        
        df = load_dataset(dataset_path)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertGreater(len(df), 0)
        self.assertIn("label", df.columns)
        self.assertIn("dist_20sma", df.columns)


class TestFeaturePreperation(unittest.TestCase):
    """Test feature preparation."""
    
    def setUp(self):
        """Create synthetic dataset for testing."""
        # Create synthetic data
        n_samples = 100
        self.df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=n_samples),
            "symbol": ["TEST"] * n_samples,
            "close": np.random.uniform(100, 150, n_samples),
            "sma_20": np.random.uniform(100, 150, n_samples),
            "sma_200": np.random.uniform(100, 150, n_samples),
            "dist_20sma": np.random.uniform(-0.1, 0.1, n_samples),
            "dist_200sma": np.random.uniform(-0.1, 0.1, n_samples),
            "sma20_slope": np.random.uniform(-0.1, 0.1, n_samples),
            "atr_pct": np.random.uniform(0.01, 0.05, n_samples),
            "vol_ratio": np.random.uniform(0.8, 1.5, n_samples),
            "pullback_depth": np.random.uniform(0, 0.2, n_samples),
            "confidence": np.random.randint(1, 6, n_samples),
            "label": np.random.randint(0, 2, n_samples),
        })
    
    def test_prepare_features_without_confidence(self):
        """Test feature preparation without rule confidence."""
        X, y, features = prepare_features(self.df, include_confidence=False)
        
        self.assertEqual(X.shape[0], len(self.df))
        self.assertEqual(len(features), 6)  # 6 feature columns
        self.assertEqual(len(y), len(self.df))
    
    def test_prepare_features_with_confidence(self):
        """Test feature preparation with rule confidence."""
        X, y, features = prepare_features(self.df, include_confidence=True)
        
        self.assertEqual(X.shape[0], len(self.df))
        self.assertEqual(len(features), 7)  # 6 + confidence
        self.assertIn("confidence", features)


class TestTimeSplit(unittest.TestCase):
    """Test time-based splitting."""
    
    def test_time_based_split(self):
        """Test temporal split preserves order."""
        X = np.arange(100).reshape(100, 1)
        y = np.arange(100) % 2
        
        X_train, X_test, y_train, y_test = time_based_split(X, y, train_ratio=0.7)
        
        # Check sizes
        self.assertEqual(len(X_train), 70)
        self.assertEqual(len(X_test), 30)
        self.assertEqual(len(y_train), 70)
        self.assertEqual(len(y_test), 30)
        
        # Check temporal order is preserved (last train < first test)
        self.assertTrue(np.all(X_train[-1] < X_test[0]))


class TestModelTraining(unittest.TestCase):
    """Test model training."""
    
    def setUp(self):
        """Create synthetic training data."""
        n_samples = 200
        n_features = 6
        
        self.X_train = np.random.randn(n_samples, n_features)
        self.y_train = np.random.randint(0, 2, n_samples)
    
    def test_train_model(self):
        """Test model training."""
        model, scaler, features = train_model(self.X_train, self.y_train)
        
        self.assertIsNotNone(model)
        self.assertIsNotNone(scaler)
        self.assertEqual(len(features), 6)


class TestProbabilityMapping(unittest.TestCase):
    """Test probability to confidence mapping."""
    
    def test_probability_to_confidence_boundaries(self):
        """Test confidence boundaries."""
        # Boundary tests
        self.assertEqual(probability_to_confidence(0.50), 1)
        self.assertEqual(probability_to_confidence(0.55), 2)
        self.assertEqual(probability_to_confidence(0.60), 3)
        self.assertEqual(probability_to_confidence(0.65), 4)
        self.assertEqual(probability_to_confidence(0.72), 5)
        self.assertEqual(probability_to_confidence(0.80), 5)
    
    def test_probability_to_confidence_range(self):
        """Test output is always in [1, 5]."""
        for p in np.linspace(0, 1, 100):
            conf = probability_to_confidence(p)
            self.assertIn(conf, [1, 2, 3, 4, 5])


class TestPrediction(unittest.TestCase):
    """Test prediction pipeline."""
    
    def setUp(self):
        """Create model and test data."""
        # Synthetic training
        X_train = np.random.randn(100, 6)
        y_train = np.random.randint(0, 2, 100)
        
        self.model, self.scaler, self.features = train_model(X_train, y_train)
        self.X_test = np.random.randn(50, 6)
    
    def test_predict_probabilities(self):
        """Test probability predictions."""
        probs = predict_probabilities(self.model, self.scaler, self.X_test)
        
        self.assertEqual(len(probs), len(self.X_test))
        self.assertTrue(np.all(probs >= 0))
        self.assertTrue(np.all(probs <= 1))
    
    def test_predict_confidence_scores(self):
        """Test confidence score predictions."""
        confs = predict_confidence_scores(self.model, self.scaler, self.X_test)
        
        self.assertEqual(len(confs), len(self.X_test))
        self.assertTrue(np.all(confs >= 1))
        self.assertTrue(np.all(confs <= 5))
    
    def test_predict_with_probabilities(self):
        """Test joint prediction."""
        probs, confs = predict_with_probabilities(self.model, self.scaler, self.X_test)
        
        self.assertEqual(len(probs), len(self.X_test))
        self.assertEqual(len(confs), len(self.X_test))


class TestFullPipeline(unittest.TestCase):
    """Test end-to-end ML pipeline."""
    
    def test_train_and_evaluate_with_synthetic_data(self):
        """Test complete training pipeline."""
        # Create synthetic dataset
        n_samples = 300
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=n_samples),
            "symbol": ["TEST"] * n_samples,
            "close": np.random.uniform(100, 150, n_samples),
            "sma_20": np.random.uniform(100, 150, n_samples),
            "sma_200": np.random.uniform(100, 150, n_samples),
            "dist_20sma": np.random.uniform(-0.1, 0.1, n_samples),
            "dist_200sma": np.random.uniform(-0.1, 0.1, n_samples),
            "sma20_slope": np.random.uniform(-0.1, 0.1, n_samples),
            "atr_pct": np.random.uniform(0.01, 0.05, n_samples),
            "vol_ratio": np.random.uniform(0.8, 1.5, n_samples),
            "pullback_depth": np.random.uniform(0, 0.2, n_samples),
            "confidence": np.random.randint(1, 6, n_samples),
            "label": np.random.randint(0, 2, n_samples),
        })
        
        # Save synthetic dataset
        test_dataset = "./data/test_ml_dataset.csv"
        Path("./data").mkdir(exist_ok=True)
        df.to_csv(test_dataset, index=False)
        
        try:
            # Run full pipeline
            result = train_and_evaluate(test_dataset, include_confidence=False)
            
            # Verify results
            self.assertIn("model", result)
            self.assertIn("scaler", result)
            self.assertIn("features", result)
            self.assertIn("metrics", result)
            self.assertIn("X_test", result)
            self.assertIn("y_test", result)
            
            # Check metrics exist
            metrics = result["metrics"]
            self.assertIn("accuracy", metrics)
            self.assertIn("precision", metrics)
            self.assertIn("recall", metrics)
            self.assertIn("f1", metrics)
        
        finally:
            # Clean up
            Path(test_dataset).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
