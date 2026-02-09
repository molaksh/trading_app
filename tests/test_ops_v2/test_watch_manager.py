"""Unit tests for WatchManager."""

import json
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch

from ops_agent.watch_manager import WatchManager
from ops_agent.schemas import Watch


class TestWatchManager:
    """Test WatchManager functionality."""

    @pytest.fixture
    def temp_watches_file(self):
        """Create temporary watches file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
            temp_path = f.name
        yield temp_path
        # Cleanup
        Path(temp_path).unlink(missing_ok=True)

    @pytest.fixture
    def mock_response_generator(self):
        """Create mock ResponseGenerator."""
        gen = Mock()
        gen.obs_reader = Mock()
        return gen

    def test_init_no_watches(self, temp_watches_file):
        """Test initialization when no watches exist."""
        Path(temp_watches_file).unlink(missing_ok=True)
        manager = WatchManager(temp_watches_file, "logs")
        assert manager.active_watches == []

    def test_add_watch(self, temp_watches_file):
        """Test adding a new watch."""
        manager = WatchManager(temp_watches_file, "logs")
        watch = manager.add_watch(
            chat_id=12345,
            condition="regime_change",
            scope="live_crypto",
            ttl_hours=24,
        )

        assert watch.chat_id == 12345
        assert watch.condition == "regime_change"
        assert watch.scope == "live_crypto"
        assert watch.watch_id.startswith("w_")
        assert len(manager.active_watches) == 1

    def test_persistence(self, temp_watches_file):
        """Test that watches are persisted to JSONL."""
        manager1 = WatchManager(temp_watches_file, "logs")
        watch1 = manager1.add_watch(chat_id=12345, condition="regime_change")

        # Create new manager, should load watch
        manager2 = WatchManager(temp_watches_file, "logs")
        assert len(manager2.active_watches) == 1
        assert manager2.active_watches[0].chat_id == 12345

    def test_remove_watch(self, temp_watches_file):
        """Test removing a watch."""
        manager = WatchManager(temp_watches_file, "logs")
        watch = manager.add_watch(chat_id=12345, condition="regime_change")

        removed = manager.remove_watch(watch.watch_id)
        assert removed is True
        assert len(manager.active_watches) == 0

    def test_remove_nonexistent_watch(self, temp_watches_file):
        """Test removing non-existent watch."""
        manager = WatchManager(temp_watches_file, "logs")
        removed = manager.remove_watch("w_nonexistent")
        assert removed is False

    def test_list_watches(self, temp_watches_file):
        """Test listing watches for a chat."""
        manager = WatchManager(temp_watches_file, "logs")

        manager.add_watch(chat_id=111, condition="regime_change")
        manager.add_watch(chat_id=111, condition="governance_pending")
        manager.add_watch(chat_id=222, condition="no_trades")

        watches_111 = manager.list_watches(111)
        assert len(watches_111) == 2

        watches_222 = manager.list_watches(222)
        assert len(watches_222) == 1

    def test_evaluate_expired_watch(self, temp_watches_file, mock_response_generator):
        """Test that expired watches are removed and notified."""
        manager = WatchManager(temp_watches_file, "logs")
        watch = manager.add_watch(chat_id=12345, condition="regime_change", ttl_hours=0)

        # Manually set expiration to past
        watch.expires_at = datetime.utcnow() - timedelta(hours=1)

        mock_telegram = Mock()
        manager.evaluate(mock_telegram, mock_response_generator)

        # Should be removed
        assert len(manager.active_watches) == 0
        # Should send expiration message
        mock_telegram.send_message.assert_called()

    def test_evaluate_regime_change(self, temp_watches_file, mock_response_generator):
        """Test regime change detection in evaluation."""
        manager = WatchManager(temp_watches_file, "logs")
        watch = manager.add_watch(
            chat_id=12345, condition="regime_change", scope="live_crypto"
        )

        # Mock observability snapshot
        mock_response_generator.obs_reader.get_snapshot.return_value = {
            "regime": "RISK_ON",
            "trading_active": True,
        }

        mock_telegram = Mock()
        manager.evaluate(mock_telegram, mock_response_generator)

        # First evaluation should initialize last_state
        assert watch.last_state == {"regime": "RISK_ON"}

        # Change regime
        mock_response_generator.obs_reader.get_snapshot.return_value = {
            "regime": "NEUTRAL",
            "trading_active": True,
        }

        manager.evaluate(mock_telegram, mock_response_generator)

        # Should detect change and send message
        assert mock_telegram.send_message.called

    def test_one_shot_watch(self, temp_watches_file, mock_response_generator):
        """Test one-shot watches are removed after triggering."""
        manager = WatchManager(temp_watches_file, "logs")
        watch = manager.add_watch(
            chat_id=12345,
            condition="regime_change",
            scope="live_crypto",
            one_shot=True,
        )

        mock_response_generator.obs_reader.get_snapshot.return_value = {
            "regime": "RISK_ON",
            "trading_active": True,
        }

        mock_telegram = Mock()
        manager.evaluate(mock_telegram, mock_response_generator)

        # Change regime to trigger
        mock_response_generator.obs_reader.get_snapshot.return_value = {
            "regime": "NEUTRAL",
            "trading_active": True,
        }

        manager.evaluate(mock_telegram, mock_response_generator)

        # Should be removed after one shot
        assert len(manager.active_watches) == 0

    def test_no_trades_condition(self, temp_watches_file, mock_response_generator):
        """Test no_trades condition detection."""
        manager = WatchManager(temp_watches_file, "logs")
        watch = manager.add_watch(
            chat_id=12345, condition="no_trades", scope="live_crypto"
        )

        # Mock trading blocked
        mock_response_generator.obs_reader.get_snapshot.return_value = {
            "trading_active": False,
            "blocks": ["PANIC_MODE"],
            "regime": "PANIC",
        }

        mock_telegram = Mock()
        manager.evaluate(mock_telegram, mock_response_generator)

        # Should detect no trades and send notification
        calls = mock_telegram.send_message.call_args_list
        assert any("⛔" in str(call) for call in calls)
