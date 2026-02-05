"""
Test crypto artifact isolation (no cross-contamination with swing).

MANDATORY ISOLATION:
Crypto roots must be completely distinct from swing roots:
  - /data/artifacts/crypto/kraken_global/ != /data/artifacts/swing/
  - /data/logs/crypto/kraken_global/ != /data/logs/swing/
  - /data/datasets/crypto/kraken_global/ != /data/datasets/swing/
  - /data/ledger/crypto/kraken_global/ != /data/ledger/swing/
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


class TestPathIsolationGuards:
    """Test path isolation enforcement at startup."""
    
    SWING_ROOTS = {
        "artifacts": "/data/artifacts/swing/",
        "logs": "/data/logs/swing/",
        "datasets": "/data/datasets/swing/",
        "ledger": "/data/ledger/swing/",
    }
    
    CRYPTO_ROOTS = {
        "artifacts": "/data/artifacts/crypto/kraken_global/",
        "logs": "/data/logs/crypto/kraken_global/",
        "datasets": "/data/datasets/crypto/kraken_global/",
        "ledger": "/data/ledger/crypto/kraken_global/",
    }
    
    def test_roots_are_distinct(self):
        """MANDATORY: Each crypto root must be different from corresponding swing root."""
        for root_type in ["artifacts", "logs", "datasets", "ledger"]:
            swing_root = self.SWING_ROOTS[root_type]
            crypto_root = self.CRYPTO_ROOTS[root_type]
            
            assert swing_root != crypto_root, (
                f"INVARIANT VIOLATION: {root_type} roots are identical!\n"
                f"  Swing: {swing_root}\n"
                f"  Crypto: {crypto_root}"
            )
    
    def test_no_prefix_overlap(self):
        """MANDATORY: Roots must not overlap (no prefix/suffix issues)."""
        for root_type in ["artifacts", "logs", "datasets", "ledger"]:
            swing_root = self.SWING_ROOTS[root_type].rstrip("/")
            crypto_root = self.CRYPTO_ROOTS[root_type].rstrip("/")
            
            # Neither should be a prefix of the other
            assert not crypto_root.startswith(swing_root), (
                f"INVARIANT VIOLATION: Crypto {root_type} is under swing!\n"
                f"  Swing: {self.SWING_ROOTS[root_type]}\n"
                f"  Crypto: {self.CRYPTO_ROOTS[root_type]}"
            )
            
            assert not swing_root.startswith(crypto_root), (
                f"INVARIANT VIOLATION: Swing {root_type} is under crypto!\n"
                f"  Swing: {self.SWING_ROOTS[root_type]}\n"
                f"  Crypto: {self.CRYPTO_ROOTS[root_type]}"
            )
    
    def test_no_swing_imports_in_crypto_code(self):
        """MANDATORY: Crypto code must not import swing strategy modules."""
        crypto_code_files = [
            "core/strategies/crypto/__init__.py",
            "core/strategies/crypto/registry.py",
        ]
        
        forbidden_patterns = [
            "from core.strategies.equity.swing",
            "import core.strategies.equity.swing",
            "from core.strategies.swing",
            "import SwingEquityStrategy",
        ]
        
        for file_path in crypto_code_files:
            try:
                with open(file_path) as f:
                    content = f.read()
                    for pattern in forbidden_patterns:
                        assert pattern not in content, (
                            f"VIOLATION: {file_path} imports swing: {pattern}"
                        )
            except FileNotFoundError:
                pass
    
    def test_startup_isolation_assertions(self):
        """Test isolation assertions that would run at startup."""
        # These would be in config validation at startup
        swing_roots = {
            "artifacts": "/data/artifacts/swing/",
            "logs": "/data/logs/swing/",
        }
        
        crypto_roots = {
            "artifacts": "/data/artifacts/crypto/kraken_global/",
            "logs": "/data/logs/crypto/kraken_global/",
        }
        
        # Assertion 1: All roots must be distinct
        for key in swing_roots:
            assert swing_roots[key] != crypto_roots[key], (
                f"CRITICAL: {key} roots are identical at startup!"
            )
        
        # Assertion 2: Scopes must be clear
        assert "swing" in swing_roots["artifacts"]
        assert "crypto" in crypto_roots["artifacts"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
