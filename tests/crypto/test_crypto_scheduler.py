"""
Test crypto scheduler: persistent state, daily tasks, downtime enforcement.

Tests the daemon-mode crypto scheduler:
- State persistence across restarts
- Task scheduling (interval + daily)
- Downtime state enforcement (no trading during, no ML outside)
- Crypto-only path validation (zero swing contamination)
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

from crypto.scheduling import DowntimeScheduler, TradingState, CryptoSchedulerState
from crypto.scheduling.state import CryptoSchedulerState as StateManager


class TestCryptoSchedulerStatePersistence:
    """Test A: Scheduler state persists across restarts."""
    
    def test_crypto_scheduler_persists_state(self):
        """
        MANDATORY TEST A: State file persists and reloads correctly.
        
        Scenario:
        1. Create scheduler state manager
        2. Mark a task as "ran"
        3. Reload from disk (simulating container restart)
        4. Verify last_run persisted
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "crypto" / "kraken_global" / "state" / "crypto_scheduler_state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Initial state manager
            state1 = CryptoSchedulerState(state_path)
            
            # Simulate marking a task as run
            now = datetime.now(timezone.utc)
            state1.update("trading_tick", now)
            
            # Verify it's in memory
            assert state1.last_run("trading_tick") is not None
            
            # Reload from disk (simulating container restart)
            state2 = CryptoSchedulerState(state_path)
            
            # Verify persisted
            last_run = state2.last_run("trading_tick")
            assert last_run is not None
            assert last_run.date() == now.date()
            assert abs((now - last_run).total_seconds()) < 5  # Within 5 seconds
    
    def test_state_survives_multiple_restarts(self):
        """Test state persists across multiple restart cycles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "crypto" / "kraken_global" / "state" / "crypto_scheduler_state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            
            now = datetime.now(timezone.utc)
            
            # Restart 1: Mark trading_tick
            state1 = CryptoSchedulerState(state_path)
            state1.update("trading_tick", now)
            
            # Restart 2: Add another task
            state2 = CryptoSchedulerState(state_path)
            state2.update("monitor", now + timedelta(minutes=5))
            
            # Verify both persisted
            assert state2.last_run("trading_tick") is not None
            assert state2.last_run("monitor") is not None
            
            # Restart 3: Reload and verify both still there
            state3 = CryptoSchedulerState(state_path)
            assert state3.last_run("trading_tick") is not None
            assert state3.last_run("monitor") is not None


class TestCryptoDowntimeEnforcement:
    """Test B & C: Downtime blocks trading, allows ML."""
    
    @pytest.fixture
    def scheduler(self):
        """Create scheduler with default downtime 03:00-05:00 UTC."""
        return DowntimeScheduler("03:00", "05:00")
    
    def test_crypto_downtime_blocks_trading_allows_ml(self, scheduler):
        """
        MANDATORY TEST B: During downtime, trading paused, ML allowed.
        
        Scenario:
        - Time is 04:00 UTC (in downtime window)
        - trading_tick task: should NOT run (blocked by state)
        - ml_training task: should run (allowed in downtime)
        """
        now = datetime(2026, 2, 5, 4, 0, 0, tzinfo=timezone.utc)
        
        # Verify we're in downtime
        assert scheduler.get_current_state(now) == TradingState.DOWNTIME
        assert not scheduler.is_trading_allowed(now)
        assert scheduler.is_training_allowed(now)
    
    def test_crypto_outside_downtime_allows_trading_blocks_ml(self, scheduler):
        """
        MANDATORY TEST C: Outside downtime, trading allowed, ML blocked.
        
        Scenario:
        - Time is 10:00 UTC (outside downtime)
        - trading_tick task: should run (allowed)
        - ml_training task: should NOT run (only in downtime)
        """
        now = datetime(2026, 2, 5, 10, 0, 0, tzinfo=timezone.utc)
        
        # Verify we're in trading window
        assert scheduler.get_current_state(now) == TradingState.TRADING
        assert scheduler.is_trading_allowed(now)
        assert not scheduler.is_training_allowed(now)


class TestCryptoDailyTaskRunOnce:
    """Test D: Daily tasks run once per day, skip after restart."""
    
    def test_crypto_daily_task_runs_once_per_day_even_after_restart(self):
        """
        MANDATORY TEST D: Daily task skips if already ran today (even after restart).
        
        Scenario:
        1. Run ml_training task at 04:00 UTC on 2026-02-05
        2. Persist state to disk
        3. "Restart" container: reload state from disk
        4. Check same day: task should NOT run again
        5. Check next day: task should run again
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "crypto" / "kraken_global" / "state" / "crypto_scheduler_state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Day 1: mark ml_training as ran at 04:00 UTC
            day1 = datetime(2026, 2, 5, 4, 0, 0, tzinfo=timezone.utc)
            state1 = CryptoSchedulerState(state_path)
            state1.update("ml_training", day1)
            
            # Simulate restart: reload state
            state2 = CryptoSchedulerState(state_path)
            
            # Same day (2026-02-05), should NOT run again
            later_same_day = datetime(2026, 2, 5, 10, 0, 0, tzinfo=timezone.utc)
            assert not state2.should_run_daily("ml_training", later_same_day)
            
            # Next day (2026-02-06), should run
            next_day = datetime(2026, 2, 6, 4, 0, 0, tzinfo=timezone.utc)
            assert state2.should_run_daily("ml_training", next_day)


class TestSchedulerStateIsCryptoOnly:
    """Test E: State path must be crypto-only, never under swing roots."""
    
    def test_scheduler_state_is_crypto_only(self):
        """
        MANDATORY TEST E: Scheduler state path is strictly crypto-only.
        
        Crypto-only paths: Must contain "crypto" or "kraken"
        Forbidden paths: Cannot contain "swing", "alpaca", "ibkr", etc.
        
        Scenario:
        1. Valid crypto path: Should succeed
        2. Swing path: Should raise ValueError (contamination check)
        3. Generic path: Should raise ValueError (not crypto)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # PASS: Crypto-only path
            crypto_path = tmpdir_path / "crypto" / "kraken_global" / "state" / "crypto_scheduler_state.json"
            crypto_path.parent.mkdir(parents=True, exist_ok=True)
            state = CryptoSchedulerState(crypto_path)
            assert state.path == crypto_path
            
            # FAIL: Swing path (contamination)
            swing_path = tmpdir_path / "swing" / "alpaca" / "state" / "crypto_scheduler_state.json"
            swing_path.parent.mkdir(parents=True, exist_ok=True)
            with pytest.raises(ValueError, match="CONTAMINATION"):
                CryptoSchedulerState(swing_path)
            
            # FAIL: Generic path (not crypto)
            generic_path = tmpdir_path / "generic" / "scheduler_state.json"
            generic_path.parent.mkdir(parents=True, exist_ok=True)
            with pytest.raises(ValueError, match="crypto"):
                CryptoSchedulerState(generic_path)


class TestTaskIntervals:
    """Test interval-based task scheduling."""
    
    def test_should_run_interval_never_run(self):
        """Task that never ran should execute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "crypto" / "test" / "state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state = CryptoSchedulerState(state_path)
            
            now = datetime.now(timezone.utc)
            assert state.should_run_interval("trading_tick", now, 1) is True
    
    def test_should_run_interval_not_yet_due(self):
        """Task run recently should not execute if interval not met."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "crypto" / "test" / "state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state = CryptoSchedulerState(state_path)
            
            now = datetime.now(timezone.utc)
            state.update("trading_tick", now)
            
            # Just now, interval not met
            assert state.should_run_interval("trading_tick", now, 1) is False
    
    def test_should_run_interval_due(self):
        """Task should execute after interval expires."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "crypto" / "test" / "state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state = CryptoSchedulerState(state_path)
            
            now = datetime.now(timezone.utc)
            past = now - timedelta(minutes=61)  # 61 min ago
            
            state.state["trading_tick"] = past.isoformat()
            
            # 61 minutes later, interval (60 min) is met
            assert state.should_run_interval("trading_tick", now, 60) is True


class TestAtomicWrites:
    """Test atomic state file writes."""
    
    def test_state_atomic_write(self):
        """State file writes are atomic (tmp → rename)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "crypto" / "test" / "state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            
            state = CryptoSchedulerState(state_path)
            
            now = datetime.now(timezone.utc)
            state.update("task1", now)
            state.update("task2", now + timedelta(seconds=1))
            
            # Verify file exists and is valid JSON
            assert state_path.exists()
            data = json.loads(state_path.read_text())
            assert len(data) == 2
            assert "task1" in data
            assert "task2" in data


class TestStateImportExport:
    """Test state querying and persistence."""
    
    def test_last_run_date(self):
        """last_run_date extracts date component."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "crypto" / "test" / "state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state = CryptoSchedulerState(state_path)
            
            now = datetime(2026, 2, 5, 14, 30, 0, tzinfo=timezone.utc)
            state.update("task1", now)
            
            last_date = state.last_run_date("task1")
            assert last_date == now.date()
            assert last_date.year == 2026
            assert last_date.month == 2
            assert last_date.day == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
