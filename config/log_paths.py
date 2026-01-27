"""
Centralized log path resolver for Docker and multi-market support.

Provides deterministic, environment-driven log paths for:
- Multi-market: india, us
- Multi-mode: observation, paper, live
- Multi-container: swing-trader, risk-monitor

CRITICAL SAFETY:
- All logs must be written to host-mounted volumes (never inside image)
- Paths are constructed dynamically from env vars
- Defaults are safe (india/paper)
- Live logs are segregated and excluded from Git

ENVIRONMENT VARIABLES:
- MARKET: Market identifier (india/us, default: india)
- APP_ENV: Trading mode (observation/paper/live, default: paper)
- LOG_ROOT: Base log directory (default: ./logs)

LOG STRUCTURE:
logs/
├── india/
│   ├── observation/
│   │   └── observations.jsonl
│   ├── paper/
│   │   ├── execution_log.jsonl
│   │   └── trade_ledger.json
│   └── live/
│       └── (empty for now)
└── us/
    ├── paper/
    │   ├── execution_log.jsonl
    │   └── trade_ledger.json
    └── live/
        └── (empty for now)
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class LogPathResolver:
    """
    Centralized resolver for all log paths.
    
    Enforces:
    - Consistent directory structure
    - Environment-driven configuration
    - Safe defaults
    - Automatic directory creation
    """
    
    def __init__(
        self,
        market: Optional[str] = None,
        app_env: Optional[str] = None,
        log_root: Optional[str] = None,
    ):
        """
        Initialize log path resolver.
        
        Args:
            market: Market identifier (india/us), reads from MARKET env var
            app_env: Trading mode (observation/paper/live), reads from APP_ENV env var
            log_root: Base log directory, reads from LOG_ROOT env var
        """
        # Read from environment with safe defaults
        self.market = (market or os.getenv("MARKET", "india")).lower()
        self.app_env = (app_env or os.getenv("APP_ENV", "paper")).lower()
        self.log_root = Path(log_root or os.getenv("LOG_ROOT", "./logs"))
        
        # Validate market
        if self.market not in ["india", "us"]:
            logger.warning(f"Invalid MARKET={self.market}, defaulting to 'india'")
            self.market = "india"
        
        # Validate app_env
        if self.app_env not in ["observation", "paper", "live"]:
            logger.warning(f"Invalid APP_ENV={self.app_env}, defaulting to 'paper'")
            self.app_env = "paper"
        
        # Construct base directory
        self.base_dir = self.log_root / self.market / self.app_env
        
        # Create directories on initialization
        self._ensure_directories()
        
        logger.info("=" * 80)
        logger.info("LOG PATH RESOLVER INITIALIZED")
        logger.info("=" * 80)
        logger.info(f"  Market: {self.market.upper()}")
        logger.info(f"  Mode: {self.app_env.upper()}")
        logger.info(f"  Base Directory: {self.base_dir.absolute()}")
        logger.info("=" * 80)
    
    def _ensure_directories(self) -> None:
        """Create log directories if they don't exist."""
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured log directory exists: {self.base_dir}")
        except Exception as e:
            logger.error(f"Failed to create log directory {self.base_dir}: {e}")
            raise
    
    def get_execution_log_path(self) -> Path:
        """
        Get path for execution log (order submissions, fills, etc).
        
        Returns:
            Path to execution_log.jsonl
        """
        return self.base_dir / "execution_log.jsonl"
    
    def get_trade_ledger_path(self) -> Path:
        """
        Get path for trade ledger (completed trades only).
        
        Returns:
            Path to trade_ledger.json
        """
        return self.base_dir / "trade_ledger.json"
    
    def get_observation_log_path(self) -> Path:
        """
        Get path for observation log (monitoring without trading).
        
        Returns:
            Path to observations.jsonl
        """
        return self.base_dir / "observations.jsonl"
    
    def get_dated_execution_log_path(self, date_str: str) -> Path:
        """
        Get path for dated execution log (backward compatibility).
        
        Args:
            date_str: Date string (e.g., "2026-01-27")
        
        Returns:
            Path to trades_{date}.jsonl
        """
        return self.base_dir / f"trades_{date_str}.jsonl"
    
    def get_custom_log_path(self, filename: str) -> Path:
        """
        Get path for custom log file.
        
        Args:
            filename: Name of log file
        
        Returns:
            Path to custom log file in base directory
        """
        return self.base_dir / filename
    
    def get_base_directory(self) -> Path:
        """
        Get base log directory for this market/mode.
        
        Returns:
            Base directory path
        """
        return self.base_dir
    
    def is_live_mode(self) -> bool:
        """
        Check if running in live trading mode.
        
        Returns:
            True if APP_ENV=live
        """
        return self.app_env == "live"
    
    def is_paper_mode(self) -> bool:
        """
        Check if running in paper trading mode.
        
        Returns:
            True if APP_ENV=paper
        """
        return self.app_env == "paper"
    
    def is_observation_mode(self) -> bool:
        """
        Check if running in observation mode.
        
        Returns:
            True if APP_ENV=observation
        """
        return self.app_env == "observation"
    
    def get_config_summary(self) -> dict:
        """
        Get configuration summary for logging/debugging.
        
        Returns:
            Dict with market, mode, and paths
        """
        return {
            "market": self.market,
            "app_env": self.app_env,
            "log_root": str(self.log_root.absolute()),
            "base_dir": str(self.base_dir.absolute()),
            "execution_log": str(self.get_execution_log_path()),
            "trade_ledger": str(self.get_trade_ledger_path()),
            "observation_log": str(self.get_observation_log_path()),
        }


# Global singleton instance
_resolver_instance: Optional[LogPathResolver] = None


def get_log_path_resolver() -> LogPathResolver:
    """
    Get global log path resolver instance (singleton).
    
    Returns:
        LogPathResolver instance
    """
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = LogPathResolver()
    return _resolver_instance


def reset_log_path_resolver() -> None:
    """
    Reset global resolver instance (for testing).
    """
    global _resolver_instance
    _resolver_instance = None
