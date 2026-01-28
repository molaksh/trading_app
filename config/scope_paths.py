"""
Scope-aware persistent storage path resolver for Phase 0.

All data, logs, models, state must be stored OUTSIDE the container
in mounted persistent volumes, organized by SCOPE.

Expected filesystem layout:
  <BASE_DIR>/
    <SCOPE>/
      logs/
        execution_log.jsonl
        trade_ledger.json
        observations.jsonl
      models/
        <strategy_name>/
          v00001/
            model.pkl
            metadata.json
          v00002/
            ...
          active.json  (which version is active)
      state/
        ml_state.json
        scheduler_state.json
      features/
        features_YYYY-MM-DD.csv
      labels/
        labels_YYYY-MM-DD.csv
      data/
        trades.jsonl
        market_data.csv
"""

import os
import logging
from pathlib import Path
from typing import Optional

from config.scope import Scope, get_scope

logger = logging.getLogger(__name__)


class ScopePathResolver:
    """
    Resolve all persistent storage paths for a given scope.
    
    Ensures:
    - All paths are outside container filesystem
    - All paths are organized by scope
    - Directories are created on demand
    - Validation fails fast if misconfigured
    """
    
    def __init__(self, scope: Scope):
        """
        Initialize path resolver for a scope.
        
        Args:
            scope: Scope instance
        
        Raises:
            ValueError: If paths not properly configured
        """
        self.scope = scope
        
        # Get base directory (required)
        base_dir = os.getenv("BASE_DIR")
        if not base_dir:
            raise ValueError(
                "BASE_DIR env var not set. "
                "Must point to persistent storage directory (e.g., /persistent/data)"
            )
        
        self.base_dir = Path(base_dir)
        self.scope_dir = self.base_dir / str(scope)
        
        # Validate base directory is accessible
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ValueError(
                f"Cannot create BASE_DIR {self.base_dir}: {e}. "
                f"Ensure it's a mounted persistent volume."
            )
        
        # Create scope-specific subdirectories
        self._ensure_subdirectories()
        
        logger.info(f"ScopePathResolver initialized for {scope}")
        logger.info(f"  Base directory: {self.base_dir.absolute()}")
        logger.info(f"  Scope directory: {self.scope_dir.absolute()}")
    
    def _ensure_subdirectories(self) -> None:
        """Create all required subdirectories."""
        subdirs = [
            self.get_logs_dir(),
            self.get_models_dir(),
            self.get_state_dir(),
            self.get_features_dir(),
            self.get_labels_dir(),
            self.get_data_dir(),
        ]
        
        for path in subdirs:
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning(f"Could not create {path}: {e}")
    
    # =========================================================================
    # Logs (execution_log.jsonl, trade_ledger.json, observations.jsonl)
    # =========================================================================
    
    def get_logs_dir(self) -> Path:
        """Get logs directory."""
        return self.scope_dir / "logs"
    
    def get_execution_log_path(self) -> Path:
        """Path to execution log (all orders and fills)."""
        return self.get_logs_dir() / "execution_log.jsonl"
    
    def get_trade_ledger_path(self) -> Path:
        """Path to trade ledger (completed trades only)."""
        return self.get_logs_dir() / "trade_ledger.json"
    
    def get_observation_log_path(self) -> Path:
        """Path to observation log (monitoring without trading)."""
        return self.get_logs_dir() / "observations.jsonl"
    
    def get_error_log_path(self) -> Path:
        """Path to error log."""
        return self.get_logs_dir() / "errors.jsonl"
    
    # =========================================================================
    # Models (versioned ML artifacts)
    # =========================================================================
    
    def get_models_dir(self) -> Path:
        """Get models root directory."""
        return self.scope_dir / "models"
    
    def get_strategy_models_dir(self, strategy_name: str) -> Path:
        """Get models directory for specific strategy."""
        return self.get_models_dir() / strategy_name
    
    def get_model_version_dir(self, strategy_name: str, version: str) -> Path:
        """Get specific model version directory (e.g., v00001)."""
        return self.get_strategy_models_dir(strategy_name) / version
    
    def get_active_model_file(self, strategy_name: str) -> Path:
        """Get active.json file that pins current model version."""
        return self.get_strategy_models_dir(strategy_name) / "active.json"
    
    # =========================================================================
    # State (ml_state.json, scheduler_state.json, etc.)
    # =========================================================================
    
    def get_state_dir(self) -> Path:
        """Get state directory."""
        return self.scope_dir / "state"
    
    def get_ml_state_file(self) -> Path:
        """Get ML training state file (tracks fingerprint, active version, etc.)."""
        return self.get_state_dir() / "ml_state.json"
    
    def get_scheduler_state_file(self) -> Path:
        """Get scheduler state file (tracks last run times)."""
        return self.get_state_dir() / "scheduler_state.json"
    
    # =========================================================================
    # Features & Labels (ML training data)
    # =========================================================================
    
    def get_features_dir(self) -> Path:
        """Get features directory."""
        return self.scope_dir / "features"
    
    def get_labels_dir(self) -> Path:
        """Get labels directory."""
        return self.scope_dir / "labels"
    
    def get_dataset_dir(self) -> Path:
        """Get dataset directory (combined features+labels)."""
        return self.scope_dir / "dataset"
    
    # =========================================================================
    # Raw Data
    # =========================================================================
    
    def get_data_dir(self) -> Path:
        """Get data directory for raw market data, trades, etc."""
        return self.scope_dir / "data"
    
    def get_trades_file(self) -> Path:
        """Get file for serialized trades."""
        return self.get_data_dir() / "trades.jsonl"
    
    def get_market_data_file(self) -> Path:
        """Get file for market data."""
        return self.get_data_dir() / "market_data.csv"
    
    # =========================================================================
    # Utilities
    # =========================================================================
    
    def get_scope_summary(self) -> dict:
        """Return summary of resolved paths for validation/logging."""
        return {
            "scope": str(self.scope),
            "base_dir": str(self.base_dir.absolute()),
            "scope_dir": str(self.scope_dir.absolute()),
            "logs_dir": str(self.get_logs_dir().absolute()),
            "models_dir": str(self.get_models_dir().absolute()),
            "state_dir": str(self.get_state_dir().absolute()),
            "features_dir": str(self.get_features_dir().absolute()),
            "labels_dir": str(self.get_labels_dir().absolute()),
            "data_dir": str(self.get_data_dir().absolute()),
        }


def get_scope_paths(scope: Optional[Scope] = None) -> ScopePathResolver:
    """
    Get path resolver for a scope.
    
    Args:
        scope: Optional Scope instance; defaults to global scope
    
    Returns:
        ScopePathResolver
    """
    if scope is None:
        scope = get_scope()
    
    return ScopePathResolver(scope)
