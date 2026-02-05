"""
Crypto scheduler state persistence (crypto-only, no swing contamination).

Maintains lightweight last-run timestamps for crypto tasks.
Uses atomic writes (temp file → rename) for safety.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class CryptoSchedulerState:
    """
    Persist crypto-only scheduler task state.
    
    State file format:
    {
        "task_name": "2026-02-05T10:30:45.123456+00:00",  # ISO format with TZ
        ...
    }
    """
    
    def __init__(self, path: Path):
        """
        Initialize state manager.
        
        Args:
            path: Path to crypto_scheduler_state.json
                 Must be under crypto root, NOT under swing roots
        
        Raises:
            ValueError: If path is under swing scheduler paths
        """
        self.path = Path(path)
        self.state: Dict[str, str] = {}
        
        # CRITICAL: Verify path is crypto-only, not contaminated
        self._validate_crypto_only_path()
        
        # Load existing state
        self._load()
    
    def _validate_crypto_only_path(self) -> None:
        """
        Assert path is crypto-only and not under swing scheduler paths.
        
        Raises:
            ValueError: If path violates crypto-only requirement
        """
        path_str = str(self.path).lower()
        
        # FORBIDDEN: swing roots
        forbidden_patterns = [
            "swing_",
            "/swing/",
            "alpaca",
            "ibkr",
            "zerodha",
            "paper_alpaca",
            "live_alpaca",
        ]
        
        for pattern in forbidden_patterns:
            if pattern in path_str:
                raise ValueError(
                    f"CONTAMINATION ERROR: Crypto scheduler state path "
                    f"cannot contain '{pattern}'. Got: {self.path}\n"
                    f"Use crypto-only paths like: /data/artifacts/crypto/kraken_global/state/"
                )
        
        # REQUIRED: crypto in path
        if "crypto" not in path_str and "kraken" not in path_str:
            raise ValueError(
                f"Crypto scheduler state path must include 'crypto' or 'kraken'. "
                f"Got: {self.path}"
            )
        
        logger.info(f"✓ Crypto-only state path validated: {self.path.parent}")
    
    def _load(self) -> None:
        """Load state from file if it exists."""
        try:
            if self.path.exists():
                content = self.path.read_text()
                self.state = json.loads(content)
                logger.debug(f"Loaded scheduler state: {len(self.state)} tasks")
            else:
                logger.info(f"No existing state file: {self.path}")
                self.state = {}
        except Exception as e:
            logger.warning(f"Could not load scheduler state: {e}")
            self.state = {}
    
    def last_run(self, key: str) -> Optional[datetime]:
        """
        Get last run time for a task.
        
        Args:
            key: Task name (e.g. "trading_tick", "ml_training")
        
        Returns:
            datetime (UTC) or None if never run
        """
        raw = self.state.get(key)
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except Exception as e:
            logger.warning(f"Could not parse last_run for {key}: {e}")
            return None
    
    def last_run_date(self, key: str) -> Optional[datetime.date]:
        """
        Get last run date (date only, no time).
        
        Returns:
            datetime.date or None
        """
        last = self.last_run(key)
        if last is None:
            return None
        # Convert to UTC date
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return last.date()
    
    def last_run_utc_timestamp(self, key: str) -> Optional[str]:
        """
        Get last run timestamp as ISO string (with timezone).
        
        Returns:
            ISO format string or None
        """
        return self.state.get(key)
    
    def update(self, key: str, when: Optional[datetime] = None) -> None:
        """
        Update last run time for a task.
        
        Args:
            key: Task name
            when: Timestamp (defaults to UTC now)
        """
        if when is None:
            when = datetime.now(timezone.utc)
        elif when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        
        # Store as ISO format with timezone
        self.state[key] = when.isoformat()
        self._persist()
    
    def _persist(self) -> None:
        """Atomically write state to disk (tmp → rename)."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            
            # Atomic write: temp file then rename
            temp_path = self.path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(self.state, indent=2, default=str))
            
            # Atomic rename (fails if destination exists on some systems, but OK here)
            temp_path.replace(self.path)
            
            logger.debug(f"Persisted scheduler state: {len(self.state)} tasks")
        except Exception as e:
            logger.error(f"Failed to persist scheduler state: {e}")
    
    def should_run_interval(
        self, 
        key: str, 
        now: datetime,
        interval_minutes: int
    ) -> bool:
        """
        Check if enough time has passed since last run.
        
        Args:
            key: Task name
            now: Current time (UTC)
            interval_minutes: Min minutes between runs
        
        Returns:
            True if should run (never run or interval exceeded)
        """
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        
        last = self.last_run(key)
        if last is None:
            return True  # Never run
        
        elapsed = now - last
        return elapsed.total_seconds() >= (interval_minutes * 60)
    
    def should_run_daily(self, key: str, now: datetime) -> bool:
        """
        Check if task should run once per day.
        
        Args:
            key: Task name
            now: Current time (UTC)
        
        Returns:
            True if today is different from last_run date
        """
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        
        last_date = self.last_run_date(key)
        today = now.date()
        
        return last_date is None or last_date < today
    
    def clear(self) -> None:
        """Clear all state (for testing)."""
        self.state = {}
        if self.path.exists():
            self.path.unlink()
    
    def __repr__(self) -> str:
        return f"CryptoSchedulerState({self.path}, tasks={len(self.state)})"
