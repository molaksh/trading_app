"""
Scope-aware persistent storage path resolver for Phase 0.

All data, logs, models, state must be stored OUTSIDE the container
in mounted persistent volumes, organized by SCOPE.

Expected filesystem layout:
    <PERSISTENCE_ROOT>/
        <SCOPE>/
            ledger/
                trades.jsonl
            models/
                active_model.json
                <strategy_name>/
                    v00001/
                        model.pkl
                        metadata.json
                    v00002/
                        ...
            features/
                features_YYYY-MM-DD.csv
            labels/
                labels_YYYY-MM-DD.csv
            state/
                ml_state.json
                broker_state.json
                scheduler_state.json
            logs/
                execution_log.jsonl
                errors.jsonl
                observations.jsonl
            cache/
                ohlcv/
                    <symbol>_daily.csv
"""

import os
import logging
from pathlib import Path
from typing import Optional, Union

from config.scope import Scope, get_scope

logger = logging.getLogger(__name__)


def _is_docker_environment() -> bool:
    """Return True if running inside a Docker container."""
    return Path("/.dockerenv").exists()


def _is_mounted_path(path: Path) -> bool:
    """Best-effort check for mount points inside containers."""
    try:
        if path.is_mount():
            return True
    except Exception:
        pass

    try:
        mountinfo = Path("/proc/self/mountinfo")
        if mountinfo.exists():
            with mountinfo.open() as f:
                for line in f:
                    # mount point is the 5th field in mountinfo
                    parts = line.split()
                    if len(parts) > 4 and parts[4] == str(path):
                        return True
    except Exception:
        pass

    return False


def _validate_persistence_root(root: Path) -> None:
    """Fail fast if persistence root is missing, not mounted, or not writable."""
    if not root.is_absolute():
        raise ValueError(f"PERSISTENCE_ROOT must be absolute: {root}")

    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise ValueError(f"Cannot create PERSISTENCE_ROOT {root}: {e}")

    if _is_docker_environment() and not _is_mounted_path(root):
        raise ValueError(
            f"PERSISTENCE_ROOT {root} is not a mounted volume. "
            f"Refusing to start to avoid container-local state."
        )

    # Write permission check
    test_file = root / ".persist_test"
    try:
        test_file.write_text("test")
        test_file.unlink()
    except Exception as e:
        raise ValueError(f"PERSISTENCE_ROOT not writable: {e}")


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
        
        # Get persistence root (required)
        persistence_root = os.getenv("PERSISTENCE_ROOT")
        if not persistence_root:
            raise ValueError(
                "PERSISTENCE_ROOT env var not set. "
                "Must point to a mounted persistent storage directory (e.g., /app/persist)"
            )

        self.base_dir = Path(persistence_root)
        _validate_persistence_root(self.base_dir)
        self.scope_dir = self.base_dir / str(scope)
        
        # Create scope-specific subdirectories
        self._ensure_subdirectories()
        
        logger.info(f"ScopePathResolver initialized for {scope}")
        logger.info(f"  Persistence root: {self.base_dir.absolute()}")
        logger.info(f"  Scope directory: {self.scope_dir.absolute()}")
    
    def _ensure_subdirectories(self) -> None:
        """Create all required subdirectories."""
        subdirs = [
            self.get_logs_dir(),
            self.get_ledger_dir(),
            self.get_models_dir(),
            self.get_state_dir(),
            self.get_features_dir(),
            self.get_labels_dir(),
            self.get_cache_dir(),
            self.get_ohlcv_cache_dir(),
        ]
        
        for path in subdirs:
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning(f"Could not create {path}: {e}")
    
    # =========================================================================
    # Logs (execution_log.jsonl, errors.jsonl, observations.jsonl)
    # =========================================================================
    
    def get_logs_dir(self) -> Path:
        """Get logs directory."""
        return self.scope_dir / "logs"
    
    def get_execution_log_path(self) -> Path:
        """Path to execution log (all orders and fills)."""
        return self.get_logs_dir() / "execution_log.jsonl"
    
    def get_trade_ledger_path(self) -> Path:
        """Path to trade ledger (completed trades only)."""
        return self.get_ledger_dir() / "trades.jsonl"

    # =========================================================================
    # Ledger (trade history)
    # =========================================================================

    def get_ledger_dir(self) -> Path:
        """Get ledger directory."""
        return self.scope_dir / "ledger"

    def get_ledger_file(self) -> Path:
        """Get trades ledger file (JSONL)."""
        return self.get_ledger_dir() / "trades.jsonl"

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
    
    def get_active_model_file(self) -> Path:
        """Get active_model.json file that pins current model version."""
        return self.get_models_dir() / "active_model.json"
    
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
    # Cache (market data)
    # =========================================================================

    def get_cache_dir(self) -> Path:
        """Get cache directory for raw market data."""
        return self.scope_dir / "cache"

    def get_ohlcv_cache_dir(self) -> Path:
        """Get OHLCV cache directory."""
        return self.get_cache_dir() / "ohlcv"

    def get_market_data_file(self) -> Path:
        """Get file for market data (optional, legacy)."""
        return self.get_cache_dir() / "market_data.csv"
    
    # =========================================================================
    # Utilities
    # =========================================================================
    
    def get_scope_summary(self) -> dict:
        """Return summary of resolved paths for validation/logging."""
        return {
            "scope": str(self.scope),
            "persistence_root": str(self.base_dir.absolute()),
            "scope_dir": str(self.scope_dir.absolute()),
            "logs_dir": str(self.get_logs_dir().absolute()),
            "ledger_dir": str(self.get_ledger_dir().absolute()),
            "models_dir": str(self.get_models_dir().absolute()),
            "state_dir": str(self.get_state_dir().absolute()),
            "features_dir": str(self.get_features_dir().absolute()),
            "labels_dir": str(self.get_labels_dir().absolute()),
            "cache_dir": str(self.get_cache_dir().absolute()),
        }


def get_scope_path(scope: Union[Scope, str, None], component: str) -> Path:
    """
    Resolve a component path for a given scope.

    Allowed components:
    - ledger
    - models
    - features
    - labels
    - state
    - logs
    - cache
    """
    if scope is None:
        scope = get_scope()
    elif isinstance(scope, str):
        scope = Scope.from_string(scope)

    resolver = ScopePathResolver(scope)

    allowed = {
        "ledger": resolver.get_ledger_dir,
        "models": resolver.get_models_dir,
        "features": resolver.get_features_dir,
        "labels": resolver.get_labels_dir,
        "state": resolver.get_state_dir,
        "logs": resolver.get_logs_dir,
        "cache": resolver.get_cache_dir,
    }

    if component not in allowed:
        raise ValueError(f"Invalid component: {component}. Allowed: {sorted(allowed.keys())}")

    return allowed[component]()


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
