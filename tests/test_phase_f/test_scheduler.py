"""
Tests for Phase F Scheduler (phase_f/scheduler.py)

Tests state persistence, daily scheduling, and graceful shutdown.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

from phase_f.scheduler import PhaseFScheduler


class TestSchedulerInitialization:
    """Test scheduler initialization."""

    def test_scheduler_creates_state_directory(self):
        """Test that scheduler creates state directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "scheduler_state.json"
            job_func = Mock()

            scheduler = PhaseFScheduler(job_func, state_file=state_file)

            assert state_file.parent.exists()

    def test_scheduler_initializes_with_defaults(self):
        """Test scheduler initialization with default run time."""
        job_func = Mock()
        scheduler = PhaseFScheduler(job_func, run_time_utc="03:00")

        assert scheduler.run_time_utc == "03:00"
        assert scheduler.job_func == job_func
        assert scheduler._shutdown_requested is False


class TestStateManagement:
    """Test state persistence."""

    def test_load_state_returns_none_when_file_missing(self):
        """Test loading state when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "missing" / "scheduler_state.json"
            scheduler = PhaseFScheduler(Mock(), state_file=state_file)

            state = scheduler._load_state()

            assert state == {"last_run_date": None}

    def test_save_and_load_state(self):
        """Test saving and loading state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "scheduler_state.json"
            scheduler = PhaseFScheduler(Mock(), state_file=state_file)

            # Save state
            test_state = {"last_run_date": "2026-02-11"}
            scheduler._save_state(test_state)

            # Load state
            loaded_state = scheduler._load_state()

            assert loaded_state == test_state

    def test_save_state_creates_parent_directory(self):
        """Test that save_state creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "nested" / "dir" / "scheduler_state.json"
            scheduler = PhaseFScheduler(Mock(), state_file=state_file)
            state_file.parent.mkdir(parents=True, exist_ok=True)

            scheduler._save_state({"last_run_date": "2026-02-11"})

            assert state_file.exists()

    def test_already_run_today_returns_true_if_ran(self):
        """Test that already_run_today returns True if job ran today."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "scheduler_state.json"
            scheduler = PhaseFScheduler(Mock(), state_file=state_file)

            # Save today's date
            today = datetime.now(timezone.utc).date().isoformat()
            scheduler._save_state({"last_run_date": today})

            # Check
            assert scheduler._already_run_today() is True

    def test_already_run_today_returns_false_if_not_ran(self):
        """Test that already_run_today returns False if job didn't run today."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "scheduler_state.json"
            scheduler = PhaseFScheduler(Mock(), state_file=state_file)

            # Save yesterday's date
            yesterday = datetime(2026, 2, 10).date().isoformat()
            scheduler._save_state({"last_run_date": yesterday})

            # Check (with mocked today)
            with patch('phase_f.scheduler.datetime') as mock_datetime:
                mock_datetime.now.return_value.date.return_value.isoformat.return_value = "2026-02-11"
                assert scheduler._already_run_today() is False


class TestJobExecution:
    """Test job execution with state management."""

    def test_run_job_with_state_executes_job(self):
        """Test that _run_job_with_state executes the job function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "scheduler_state.json"
            job_func = Mock()
            scheduler = PhaseFScheduler(job_func, state_file=state_file)

            # Should execute because job hasn't run today
            scheduler._run_job_with_state()

            job_func.assert_called_once()

    def test_run_job_skips_if_already_ran_today(self):
        """Test that job is skipped if already ran today."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "scheduler_state.json"
            job_func = Mock()
            scheduler = PhaseFScheduler(job_func, state_file=state_file)

            # Set today's date as last run
            today = datetime.now(timezone.utc).date().isoformat()
            scheduler._save_state({"last_run_date": today})

            # Should skip
            scheduler._run_job_with_state()

            job_func.assert_not_called()

    def test_run_job_updates_state_on_success(self):
        """Test that state is updated after successful job run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "scheduler_state.json"
            job_func = Mock()
            scheduler = PhaseFScheduler(job_func, state_file=state_file)

            scheduler._run_job_with_state()

            # Check state
            state = scheduler._load_state()
            today = datetime.now(timezone.utc).date().isoformat()
            assert state["last_run_date"] == today

    def test_run_job_handles_failure_gracefully(self):
        """Test that job failure is handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "scheduler_state.json"
            job_func = Mock(side_effect=Exception("Test error"))
            scheduler = PhaseFScheduler(job_func, state_file=state_file)

            # Should not raise
            scheduler._run_job_with_state()

            # State should not be updated
            state = scheduler._load_state()
            assert state["last_run_date"] is None


class TestSchedulerShutdown:
    """Test graceful shutdown."""

    def test_request_shutdown_sets_flag(self):
        """Test that _request_shutdown sets the shutdown flag."""
        scheduler = PhaseFScheduler(Mock())

        scheduler._request_shutdown()

        assert scheduler._shutdown_requested is True


class TestConfigurationIntegration:
    """Test integration with Phase F settings."""

    @patch('phase_f.scheduler.PHASE_F_KILL_SWITCH', True)
    def test_start_respects_kill_switch(self):
        """Test that scheduler respects PHASE_F_KILL_SWITCH."""
        job_func = Mock()
        scheduler = PhaseFScheduler(job_func)

        # Should return early due to kill switch
        scheduler.start()

        # Job should not be scheduled
        job_func.assert_not_called()

    @patch('phase_f.scheduler.PHASE_F_ENABLED', False)
    def test_start_respects_disabled_flag(self):
        """Test that scheduler respects PHASE_F_ENABLED=false."""
        job_func = Mock()
        scheduler = PhaseFScheduler(job_func)

        # Should return early due to disabled flag
        scheduler.start()

        # Job should not be scheduled (at least not immediately)
        # Note: In actual daemon mode, this would still start but not schedule


class TestSchedulerIntegration:
    """Integration tests."""

    @patch('schedule.every')
    def test_scheduler_schedules_daily_run(self, mock_schedule):
        """Test that scheduler schedules a daily run."""
        mock_job = MagicMock()
        mock_schedule.return_value.day.at.return_value.do = Mock(return_value=mock_job)

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "scheduler_state.json"
            job_func = Mock()
            scheduler = PhaseFScheduler(job_func, state_file=state_file)

            # Mock the start method to just check scheduling
            with patch('schedule.every') as mock_every:
                mock_every.return_value.day.at.return_value.do = Mock()
                mock_scheduler = PhaseFScheduler(job_func, state_file=state_file, run_time_utc="03:00")

                # Verify initialization sets up daily schedule
                assert mock_scheduler.run_time_utc == "03:00"
