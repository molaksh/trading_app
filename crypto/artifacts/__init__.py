"""
Crypto-specific artifact management system.

Paths:
- CRYPTO_ARTIFACT_ROOT=/data/artifacts/crypto/kraken_global/
- CRYPTO_LOG_ROOT=/data/logs/crypto/kraken_global/
- CRYPTO_DATASET_ROOT=/data/datasets/crypto/kraken_global/
- CRYPTO_LEDGER_ROOT=/data/ledger/crypto/kraken_global/

NO cross-contamination with swing artifacts.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)


class CryptoArtifactStore:
    """
    Manages all crypto artifacts with strict isolation.
    Prevents cross-contamination with swing paths.
    """
    
    def __init__(self, root: Optional[str] = None):
        """
        Initialize artifact store.
        
        Args:
            root: Root directory for crypto artifacts
                  Default: /data/artifacts/crypto/kraken_global/
        """
        self.root = Path(root or "/data/artifacts/crypto/kraken_global")
        self.models_dir = self.root / "models"
        self.candidates_dir = self.models_dir / "candidates"
        self.validations_dir = self.models_dir / "validations"
        self.shadow_dir = self.models_dir / "shadow"
        
        # Verify isolation from swing
        self._verify_isolation()
        
        # Create directories
        for dir_path in [self.root, self.models_dir, self.candidates_dir, 
                         self.validations_dir, self.shadow_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Artifact directory ready: {dir_path}")
    
    def _verify_isolation(self):
        """Ensure crypto paths don't overlap with swing paths."""
        swing_roots = [
            "/data/artifacts/swing",
            "/data/logs/swing",
            "/data/datasets/swing",
            "/data/ledger/swing",
        ]
        
        for swing_root in swing_roots:
            if str(self.root).startswith(swing_root):
                raise ValueError(
                    f"SECURITY: Crypto artifacts root {self.root} "
                    f"would write to swing root {swing_root}. Forbidden."
                )
        
        logger.info("✓ Artifact isolation verified (no swing cross-contamination)")
    
    def save_candidate(self, model_id: str, model_data: Dict[str, Any], 
                      metadata: Dict[str, Any], metrics: Dict[str, Any]) -> Path:
        """
        Save a candidate model with metadata and metrics.
        
        Args:
            model_id: Unique model identifier
            model_data: Model binary/weights
            metadata: Feature schema, data range, params
            metrics: Train/OOS metrics, DD, turnover
        
        Returns:
            Path to candidate directory
        """
        candidate_dir = self.candidates_dir / model_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        
        # Save model
        model_path = candidate_dir / "model.pkl"
        with open(model_path, 'wb') as f:
            import pickle
            pickle.dump(model_data, f)
        
        # Save metadata
        with open(candidate_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Save metrics
        with open(candidate_dir / "metrics.json", 'w') as f:
            json.dump(metrics, f, indent=2)
        
        # Compute SHA256 hashes
        hashes = {}
        for file in [model_path, candidate_dir / "metadata.json", candidate_dir / "metrics.json"]:
            hashes[file.name] = self._sha256_file(file)
        
        with open(candidate_dir / "sha256.txt", 'w') as f:
            for filename, hash_val in hashes.items():
                f.write(f"{hash_val}  {filename}\n")
        
        logger.info(f"✓ Candidate saved: {candidate_dir}")
        return candidate_dir
    
    def load_approved_model(self) -> Optional[Dict[str, Any]]:
        """
        Load approved model pointer.
        
        Returns:
            Model metadata if approved model exists, None otherwise
        """
        approved_file = self.models_dir / "approved_model.json"
        
        if not approved_file.exists():
            logger.warning("No approved model found")
            return None
        
        with open(approved_file, 'r') as f:
            pointer = json.load(f)
        
        logger.info(f"Loaded approved model pointer: {pointer.get('model_id')}")
        return pointer
    
    def verify_candidate_integrity(self, model_id: str) -> bool:
        """
        Verify candidate model integrity (SHA256 hashes).
        
        Args:
            model_id: Candidate model ID
        
        Returns:
            True if all hashes match, False otherwise
        """
        candidate_dir = self.candidates_dir / model_id
        sha256_file = candidate_dir / "sha256.txt"
        
        if not sha256_file.exists():
            logger.error(f"No sha256.txt for candidate {model_id}")
            return False
        
        with open(sha256_file, 'r') as f:
            expected_hashes = {}
            for line in f:
                if line.strip():
                    hash_val, filename = line.strip().split()
                    expected_hashes[filename] = hash_val
        
        for filename, expected_hash in expected_hashes.items():
            file_path = candidate_dir / filename
            if not file_path.exists():
                logger.error(f"Missing file: {filename}")
                return False
            
            actual_hash = self._sha256_file(file_path)
            if actual_hash != expected_hash:
                logger.error(f"Hash mismatch for {filename}")
                return False
        
        logger.info(f"✓ Integrity verified: {model_id}")
        return True
    
    def _sha256_file(self, file_path: Path) -> str:
        """Compute SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def get_models_dir(self) -> Path:
        """Get models directory path."""
        return self.models_dir


class CryptoLogStore:
    """Manages crypto-specific logs (isolated from swing)."""
    
    def __init__(self, root: Optional[str] = None):
        """
        Initialize log store.
        
        Args:
            root: Log root directory
                  Default: /data/logs/crypto/kraken_global/
        """
        self.root = Path(root or "/data/logs/crypto/kraken_global")
        self.root.mkdir(parents=True, exist_ok=True)
        
        self.observation_log = self.root / "observations.jsonl"
        self.trades_ledger = self.root / "trades.jsonl"
        self.approval_log = self.root / "approvals.jsonl"
        self.registry_log = self.root / "registry.jsonl"
        
        logger.info(f"✓ Crypto log store initialized: {self.root}")


class CryptoDatasetStore:
    """Manages crypto training datasets (isolated from swing)."""
    
    def __init__(self, root: Optional[str] = None):
        """
        Initialize dataset store.
        
        Args:
            root: Dataset root directory
                  Default: /data/datasets/crypto/kraken_global/
        """
        self.root = Path(root or "/data/datasets/crypto/kraken_global")
        self.root.mkdir(parents=True, exist_ok=True)
        
        self.training_dir = self.root / "training"
        self.training_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"✓ Crypto dataset store initialized: {self.root}")


class CryptoLedgerStore:
    """Manages crypto trading ledger (isolated from swing)."""
    
    def __init__(self, root: Optional[str] = None):
        """
        Initialize ledger store.
        
        Args:
            root: Ledger root directory
                  Default: /data/ledger/crypto/kraken_global/
        """
        self.root = Path(root or "/data/ledger/crypto/kraken_global")
        self.root.mkdir(parents=True, exist_ok=True)
        
        self.positions_dir = self.root / "positions"
        self.positions_dir.mkdir(parents=True, exist_ok=True)
        
        self.trades_dir = self.root / "trades"
        self.trades_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"✓ Crypto ledger store initialized: {self.root}")
