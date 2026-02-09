"""Integration tests for Phase E v2 components."""

import json
import pytest
import tempfile
import time
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from ops_agent.watch_manager import WatchManager
from ops_agent.duration_tracker import DurationTracker
from ops_agent.historical_analyzer import HistoricalAnalyzer
from ops_agent.digest_generator import DigestGenerator
from ops_agent.response_generator import ResponseGenerator
from ops_agent.ops_loop import OpsLoop
from ops_agent.telegram_handler import TelegramHandler
from ops_agent.persistence import OpsEventLogger
from ops_agent.schemas import DailySummaryEntry


class TestPhaseEV2Integration:
    """Integration tests for Phase E v2."""

    @pytest.fixture
    def temp_persistence_dir(self):
        """Create temporary persistence directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def temp_logs_dir(self):
        """Create temporary logs directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_duration_tracking_lifecycle(self, temp_persistence_dir):
        """Test complete duration tracking lifecycle."""
        tracker = DurationTracker(f"{temp_persistence_dir}/regime_history.jsonl")

        # Start tracking
        event1 = tracker.update("live_crypto", "RISK_ON")
        assert event1 is not None
        assert event1.regime == "RISK_ON"

        # Verify duration accumulates
        time.sleep(0.2)
        duration1 = tracker.get_duration("live_crypto")
        time.sleep(0.2)
        duration2 = tracker.get_duration("live_crypto")

        assert duration2 >= duration1  # Allow equal in case of timing precision

        # Change regime
        event2 = tracker.update("live_crypto", "NEUTRAL")
        assert event2 is not None
        assert event2.previous_regime == "RISK_ON"
        assert event2.duration_seconds is not None

    def test_watch_evaluation_lifecycle(self, temp_persistence_dir, temp_logs_dir):
        """Test watch creation and evaluation lifecycle."""
        manager = WatchManager(
            f"{temp_persistence_dir}/active_watches.jsonl", temp_logs_dir
        )

        # Create watch
        watch = manager.add_watch(
            chat_id=12345,
            condition="regime_change",
            scope="live_crypto",
            ttl_hours=24,
        )

        assert len(manager.active_watches) == 1

        # Mock response generator with regime snapshot
        gen = Mock()
        gen.obs_reader = Mock()
        gen.obs_reader.get_snapshot.return_value = {"regime": "RISK_ON"}

        mock_telegram = Mock()

        # First evaluation - should initialize
        manager.evaluate(mock_telegram, gen)
        assert watch.last_state == {"regime": "RISK_ON"}

        # Change regime
        gen.obs_reader.get_snapshot.return_value = {"regime": "NEUTRAL"}

        # Second evaluation - should detect change
        manager.evaluate(mock_telegram, gen)
        assert mock_telegram.send_message.called
        assert "Regime change" in str(mock_telegram.send_message.call_args)

    def test_historical_context_addition(self, temp_logs_dir):
        """Test that historical context is added to responses."""
        with patch("ops_agent.historical_analyzer.SummaryReader") as mock_reader_class:
            mock_reader = Mock()

            # Create mock summaries (all RISK_ON)
            summaries = [
                DailySummaryEntry(
                    timestamp=datetime.utcnow(),
                    scope="live_crypto",
                    regime="RISK_ON",
                    trades_executed=5,
                    realized_pnl=100.0,
                    max_drawdown=-0.02,
                )
                for _ in range(5)
            ]
            mock_reader.get_summaries.return_value = summaries
            mock_reader_class.return_value = mock_reader

            analyzer = HistoricalAnalyzer(temp_logs_dir)

            # Test framing
            framing = analyzer.frame_expectation("live_crypto", "RISK_ON", 24.0)
            assert framing is not None

    def test_digest_generation(self, temp_logs_dir):
        """Test digest generation with multiple scopes."""
        gen = Mock()
        gen.obs_reader = Mock()

        snapshots = {
            "live_crypto": {
                "regime": "RISK_ON",
                "recent_trades": 3,
                "daily_pnl": 150.0,
                "trading_active": True,
            },
            "paper_crypto": {
                "regime": "NEUTRAL",
                "recent_trades": 1,
                "daily_pnl": 25.0,
                "trading_active": True,
            },
            "live_us": None,
            "paper_us": None,
        }

        def get_snapshot_side_effect(scope):
            return snapshots.get(scope)

        gen.obs_reader.get_snapshot.side_effect = get_snapshot_side_effect

        digest_gen = DigestGenerator(gen, enabled=True, only_if_activity=True)
        digest = digest_gen.generate_digest()

        assert "Daily Digest" in digest
        assert "live_crypto" in digest
        assert "RISK_ON" in digest

    def test_v1_backward_compatibility(self, temp_persistence_dir, temp_logs_dir):
        """Test that v1 functionality works without v2 components."""
        # Create components without v2 features
        telegram = Mock(spec=TelegramHandler)
        telegram.allowed_chat_ids = [12345]
        telegram.get_updates.return_value = []

        generator = ResponseGenerator(logs_root=temp_logs_dir)

        # Verify v2 components are None
        assert generator.duration_tracker is None
        assert generator.historical_analyzer is None

        event_logger = Mock(spec=OpsEventLogger)

        # Create loop without v2 components
        loop = OpsLoop(
            telegram_handler=telegram,
            response_generator=generator,
            event_logger=event_logger,
            watch_manager=None,
            digest_generator=None,
        )

        # Should run without error
        assert loop.watch_manager is None
        assert loop.digest_generator is None

    def test_v2_all_features_enabled(self, temp_persistence_dir, temp_logs_dir):
        """Test ops loop with all v2 features enabled."""
        telegram = Mock(spec=TelegramHandler)
        telegram.allowed_chat_ids = [12345]
        telegram.get_updates.return_value = []
        telegram.send_message.return_value = True

        generator = ResponseGenerator(logs_root=temp_logs_dir)

        duration_tracker = DurationTracker(
            f"{temp_persistence_dir}/regime_history.jsonl"
        )
        duration_tracker.update("live_crypto", "RISK_ON")
        generator.duration_tracker = duration_tracker

        with patch("ops_agent.historical_analyzer.SummaryReader"):
            historical_analyzer = HistoricalAnalyzer(temp_logs_dir)
            generator.historical_analyzer = historical_analyzer

        watch_manager = WatchManager(
            f"{temp_persistence_dir}/active_watches.jsonl", temp_logs_dir
        )

        digest_generator = DigestGenerator(generator, enabled=True)

        event_logger = Mock(spec=OpsEventLogger)

        # Create loop with all v2 features
        loop = OpsLoop(
            telegram_handler=telegram,
            response_generator=generator,
            event_logger=event_logger,
            watch_manager=watch_manager,
            digest_generator=digest_generator,
        )

        # Verify all components initialized
        assert loop.watch_manager is not None
        assert loop.digest_generator is not None
        assert generator.duration_tracker is not None
        assert generator.historical_analyzer is not None

        # Single tick should work without error
        loop._tick()

    def test_watch_expire_and_notify(self, temp_persistence_dir, temp_logs_dir):
        """Test watch expiration and notification."""
        manager = WatchManager(
            f"{temp_persistence_dir}/active_watches.jsonl", temp_logs_dir
        )

        # Create watch that expires immediately
        watch = manager.add_watch(
            chat_id=12345, condition="regime_change", ttl_hours=0
        )

        # Manually set past expiration
        watch.expires_at = datetime.utcnow() - timedelta(seconds=1)

        gen = Mock()
        gen.obs_reader = Mock()
        gen.obs_reader.get_snapshot.return_value = {"regime": "RISK_ON"}

        mock_telegram = Mock()
        manager.evaluate(mock_telegram, gen)

        # Watch should be removed
        assert len(manager.active_watches) == 0
        # Expiration notification should be sent
        mock_telegram.send_message.assert_called()

    def test_persist_and_recover(self, temp_persistence_dir):
        """Test persistence and recovery of state."""
        watches_file = f"{temp_persistence_dir}/active_watches.jsonl"

        # Create watch in first manager
        manager1 = WatchManager(watches_file, "logs")
        watch1 = manager1.add_watch(chat_id=111, condition="regime_change")

        # Create second manager, should recover watch
        manager2 = WatchManager(watches_file, "logs")
        assert len(manager2.active_watches) == 1
        assert manager2.active_watches[0].chat_id == 111
        assert manager2.active_watches[0].watch_id == watch1.watch_id
