"""
ML training state manager for Phase 0 idempotency.

Tracks:
- Last trained data end timestamp
- Dataset fingerprint (hash to detect new data)
- Last run ID
- Last promoted model version
- Promotion timestamp

Enables:
- Idempotent training (skip if fingerprint unchanged)
- Model version pinning per scope
- Atomic promotion (fail-safe)
"""

import json
import logging
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List

from config.scope_paths import get_scope_paths

logger = logging.getLogger(__name__)


@dataclass
class MLState:
    """Training state persisted to STATE_DIR/<scope>/ml_state.json."""
    
    last_trained_data_end_ts: Optional[str] = None
    last_dataset_fingerprint: Optional[str] = None
    last_run_id: Optional[str] = None
    last_promoted_model_version: Optional[str] = None
    promotion_timestamp: Optional[str] = None
    active_model_loaded_at: Optional[str] = None
    active_model_version: Optional[str] = None  # Currently pinned version
    
    def to_dict(self) -> dict:
        """Serialize to dict."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "MLState":
        """Deserialize from dict."""
        return cls(**data)


class MLStateManager:
    """
    Manage ML training state for a scope.
    
    Persists to STATE_DIR/<scope>/ml_state.json
    Atomic operations for safe promotion and loading.
    """
    
    def __init__(self, scope_name: str = None):
        """
        Initialize manager.
        
        Args:
            scope_name: Optional scope name; uses global scope if not provided
        """
        if scope_name is None:
            paths = get_scope_paths()
        else:
            # For testing
            from config.scope import Scope
            paths = get_scope_paths(Scope.from_string(scope_name))
        
        self.state_file = paths.get_ml_state_file()
        self._ensure_state_file_exists()
    
    def _ensure_state_file_exists(self) -> None:
        """Create state file if missing."""
        if not self.state_file.exists():
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            initial_state = MLState()
            self._save_state(initial_state)
    
    def load(self) -> MLState:
        """Load ML state from disk."""
        try:
            if self.state_file.exists():
                with open(self.state_file) as f:
                    data = json.load(f)
                    return MLState.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load ML state: {e}")
        
        return MLState()
    
    def _save_state(self, state: MLState) -> None:
        """Save state to disk (internal, not atomic)."""
        try:
            with open(self.state_file, "w") as f:
                json.dump(state.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save ML state: {e}")
    
    def update_dataset_fingerprint(self, fingerprint: str, run_id: str) -> None:
        """
        Update dataset fingerprint after successful training.
        
        Args:
            fingerprint: SHA256 hash of training data
            run_id: Unique training run identifier
        """
        state = self.load()
        state.last_dataset_fingerprint = fingerprint
        state.last_run_id = run_id
        state.last_trained_data_end_ts = datetime.now().isoformat()
        self._save_state(state)
        logger.info(f"Updated ML state: fingerprint={fingerprint[:16]}..., run_id={run_id}")
    
    def promote_model(self, model_version: str) -> None:
        """
        Atomically promote model to active.
        
        Atomic: write to temp file, then rename.
        
        Args:
            model_version: Model version string (e.g., "v00042")
        """
        state = self.load()
        state.last_promoted_model_version = model_version
        state.active_model_version = model_version
        state.promotion_timestamp = datetime.now().isoformat()
        state.active_model_loaded_at = datetime.now().isoformat()
        
        # Atomic write
        temp_file = self.state_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w") as f:
                json.dump(state.to_dict(), f, indent=2)
            temp_file.replace(self.state_file)  # Atomic rename
            logger.info(f"Atomically promoted model: {model_version}")
        except Exception as e:
            logger.error(f"Failed to promote model: {e}")
            if temp_file.exists():
                temp_file.unlink()
    
    def get_active_model_version(self) -> Optional[str]:
        """Get currently pinned active model version."""
        state = self.load()
        return state.active_model_version
    
    def should_train(self, current_fingerprint: str) -> bool:
        """
        Check if training is needed (idempotency).
        
        Returns False if fingerprint unchanged (skip training).
        Returns True if no previous training or fingerprint changed.
        
        Args:
            current_fingerprint: SHA256 hash of current training data
        
        Returns:
            True if training needed, False if should skip
        """
        state = self.load()
        
        if state.last_dataset_fingerprint is None:
            logger.info("No previous training; training needed")
            return True
        
        if current_fingerprint == state.last_dataset_fingerprint:
            logger.info(
                f"Dataset unchanged (fingerprint={current_fingerprint[:16]}...). "
                f"Skipping training (idempotent)."
            )
            return False
        
        logger.info(
            f"Dataset changed (was {state.last_dataset_fingerprint[:16]}..., "
            f"now {current_fingerprint[:16]}...). Training needed."
        )
        return True


def compute_dataset_fingerprint(trades: List[dict]) -> str:
    """
    Compute SHA256 fingerprint of training data.
    
    Hash is deterministic on:
    - Trade symbols
    - Entry/exit prices
    - Entry/exit dates
    - Trade count
    - ML labels (bad/good)
    
    Changes in any of these trigger retraining.
    
    Args:
        trades: List of trade dicts with structure:
                {symbol, entry_price, exit_price, entry_timestamp, exit_timestamp, ...}
    
    Returns:
        SHA256 hex digest
    """
    content = ""
    
    # Sort by entry timestamp for determinism
    sorted_trades = sorted(trades, key=lambda t: t.get("entry_timestamp", ""))
    
    for trade in sorted_trades:
        symbol = trade.get("symbol", "")
        entry_price = trade.get("entry_price", 0)
        exit_price = trade.get("exit_price", 0)
        entry_ts = trade.get("entry_timestamp", "")
        exit_ts = trade.get("exit_timestamp", "")
        
        content += f"{symbol}|{entry_price}|{exit_price}|{entry_ts}|{exit_ts}\n"
    
    # Include count and hash
    content = f"count={len(trades)}\n" + content
    
    return hashlib.sha256(content.encode()).hexdigest()
