"""Unit tests for DurationTracker."""

import json
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from ops_agent.duration_tracker import DurationTracker
from ops_agent.schemas import RegimeEvent


class TestDurationTracker:
    """Test DurationTracker functionality."""

    @pytest.fixture
    def temp_history_file(self):
        """Create temporary history file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
            temp_path = f.name
        yield temp_path
        # Cleanup
        Path(temp_path).unlink(missing_ok=True)

    def test_init_no_file(self, temp_history_file):
        """Test initialization when history file doesn't exist."""
        Path(temp_history_file).unlink(missing_ok=True)
        tracker = DurationTracker(temp_history_file)
        assert tracker.current_regimes == {}

    def test_update_first_regime(self, temp_history_file):
        """Test first regime update (no previous regime)."""
        tracker = DurationTracker(temp_history_file)
        event = tracker.update("live_crypto", "RISK_ON")

        assert event is not None
        assert event.regime == "RISK_ON"
        assert event.previous_regime is None
        assert event.duration_seconds is None

    def test_update_regime_change(self, temp_history_file):
        """Test regime change detection."""
        tracker = DurationTracker(temp_history_file)

        # First update
        event1 = tracker.update("live_crypto", "RISK_ON")
        assert event1 is not None

        # Wait a bit, then change regime
        import time

        time.sleep(0.1)
        event2 = tracker.update("live_crypto", "NEUTRAL")

        assert event2 is not None
        assert event2.previous_regime == "RISK_ON"
        assert event2.regime == "NEUTRAL"
        assert event2.duration_seconds is not None
        assert event2.duration_seconds >= 0

    def test_no_change_returns_none(self, temp_history_file):
        """Test that unchanged regime returns None."""
        tracker = DurationTracker(temp_history_file)

        tracker.update("live_crypto", "RISK_ON")
        event2 = tracker.update("live_crypto", "RISK_ON")

        assert event2 is None

    def test_persistence(self, temp_history_file):
        """Test that events are persisted to JSONL."""
        tracker1 = DurationTracker(temp_history_file)
        tracker1.update("live_crypto", "RISK_ON")

        # Create new tracker, should load previous event
        tracker2 = DurationTracker(temp_history_file)
        assert "live_crypto" in tracker2.current_regimes
        assert tracker2.current_regimes["live_crypto"][0] == "RISK_ON"

    def test_get_duration_unknown_scope(self, temp_history_file):
        """Test getting duration for unknown scope."""
        tracker = DurationTracker(temp_history_file)
        assert tracker.get_duration("unknown_scope") is None

    def test_get_duration_known_scope(self, temp_history_file):
        """Test getting duration for known scope."""
        tracker = DurationTracker(temp_history_file)
        tracker.update("live_crypto", "RISK_ON")

        import time

        time.sleep(0.1)
        duration = tracker.get_duration("live_crypto")

        assert duration is not None
        assert duration >= 0

    def test_get_duration_formatted(self, temp_history_file):
        """Test human-readable duration formatting."""
        tracker = DurationTracker(temp_history_file)
        tracker.update("live_crypto", "RISK_ON")

        # Mock duration for testing
        tracker.current_regimes["live_crypto"] = (
            "RISK_ON",
            datetime.utcnow() - timedelta(hours=4, minutes=12),
        )

        formatted = tracker.get_duration_formatted("live_crypto")
        assert "h" in formatted  # Should have hours
        assert "m" in formatted  # Should have minutes

    def test_multiple_scopes(self, temp_history_file):
        """Test tracking multiple scopes independently."""
        tracker = DurationTracker(temp_history_file)

        tracker.update("live_crypto", "RISK_ON")
        tracker.update("paper_crypto", "NEUTRAL")

        assert len(tracker.current_regimes) == 2
        assert tracker.get_current_regime("live_crypto") == "RISK_ON"
        assert tracker.get_current_regime("paper_crypto") == "NEUTRAL"
