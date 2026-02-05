"""
Test crypto artifact isolation (no cross-contamination with swing).
"""

import pytest
import tempfile
from pathlib import Path

from crypto.artifacts import CryptoArtifactStore


class TestArtifactIsolation:
    """Test that crypto artifacts are isolated from swing."""
    
    def test_isolation_from_swing_artifacts(self):
        """Test that crypto root doesn't write to swing paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Try to create store pointing to swing root (should fail)
            crypto_root = f"{tmpdir}/swing/artifacts"
            
            with pytest.raises(ValueError, match="would write to swing root"):
                CryptoArtifactStore(root=crypto_root)
    
    def test_isolation_from_swing_logs(self):
        """Test that crypto logs don't write to swing paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            crypto_root = f"{tmpdir}/swing/logs"
            
            with pytest.raises(ValueError, match="would write to swing root"):
                CryptoArtifactStore(root=crypto_root)
    
    def test_crypto_root_isolation_valid(self):
        """Test that valid crypto roots are accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            crypto_root = f"{tmpdir}/artifacts/crypto/kraken_global"
            store = CryptoArtifactStore(root=crypto_root)
            
            # Should not raise
            assert store.root == Path(crypto_root)
    
    def test_directories_created_in_crypto_root(self):
        """Test that directories are created under crypto root only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            crypto_root = f"{tmpdir}/artifacts/crypto/kraken_global"
            store = CryptoArtifactStore(root=crypto_root)
            
            # Verify directories exist
            assert store.models_dir.exists()
            assert store.candidates_dir.exists()
            assert store.validations_dir.exists()
            assert store.shadow_dir.exists()
            
            # Verify all are under crypto_root
            for dir_path in [store.models_dir, store.candidates_dir, 
                            store.validations_dir, store.shadow_dir]:
                assert str(dir_path).startswith(crypto_root)
    
    def test_no_swing_files_written(self):
        """Test that crypto operations don't create swing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            crypto_root = f"{tmpdir}/crypto/kraken"
            swing_root = f"{tmpdir}/swing/alpaca"
            
            store = CryptoArtifactStore(root=crypto_root)
            
            # Verify swing root has no files
            swing_path = Path(swing_root)
            assert not swing_path.exists() or len(list(swing_path.rglob('*'))) == 0
    
    def test_isolation_guards_on_save(self):
        """Test that save operations respect isolation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            crypto_root = f"{tmpdir}/crypto/kraken"
            store = CryptoArtifactStore(root=crypto_root)
            
            # Save a candidate
            model_data = {'weights': [1, 2, 3]}
            metadata = {'version': '1.0', 'features': ['rsi', 'macd']}
            metrics = {'sharpe': 0.75, 'dd': 0.12}
            
            candidate_path = store.save_candidate(
                'model_test_001',
                model_data,
                metadata,
                metrics,
            )
            
            # Verify saved under crypto_root
            assert str(candidate_path).startswith(crypto_root)
            assert candidate_path.exists()
            
            # Verify files inside
            assert (candidate_path / "model.pkl").exists()
            assert (candidate_path / "metadata.json").exists()
            assert (candidate_path / "metrics.json").exists()
            assert (candidate_path / "sha256.txt").exists()
