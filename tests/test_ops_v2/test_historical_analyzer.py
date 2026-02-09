"""Unit tests for HistoricalAnalyzer."""

import pytest
from unittest.mock import Mock, patch

from ops_agent.historical_analyzer import HistoricalAnalyzer
from ops_agent.schemas import DailySummaryEntry
from datetime import datetime


class TestHistoricalAnalyzer:
    """Test HistoricalAnalyzer functionality."""

    @pytest.fixture
    def mock_summary_reader(self):
        """Create mock SummaryReader."""
        reader = Mock()
        return reader

    @pytest.fixture
    def analyzer(self, mock_summary_reader):
        """Create analyzer with mocked reader."""
        with patch("ops_agent.historical_analyzer.SummaryReader", return_value=mock_summary_reader):
            return HistoricalAnalyzer("logs")

    def test_get_regime_statistics(self, analyzer, mock_summary_reader):
        """Test regime statistics calculation."""
        # Mock summaries
        summaries = [
            DailySummaryEntry(
                timestamp=datetime.utcnow(),
                scope="live_crypto",
                regime="RISK_ON",
                trades_executed=5,
                realized_pnl=100.0,
                max_drawdown=-0.02,
            ),
            DailySummaryEntry(
                timestamp=datetime.utcnow(),
                scope="live_crypto",
                regime="RISK_ON",
                trades_executed=3,
                realized_pnl=50.0,
                max_drawdown=-0.01,
            ),
            DailySummaryEntry(
                timestamp=datetime.utcnow(),
                scope="live_crypto",
                regime="NEUTRAL",
                trades_executed=1,
                realized_pnl=10.0,
                max_drawdown=-0.005,
            ),
        ]
        mock_summary_reader.get_summaries.return_value = summaries

        stats = analyzer.get_regime_statistics("live_crypto")

        assert "RISK_ON" in stats
        assert "NEUTRAL" in stats
        assert stats["RISK_ON"]["occurrences"] == 2
        assert stats["NEUTRAL"]["occurrences"] == 1

    def test_frame_expectation_unusual(self, analyzer, mock_summary_reader):
        """Test expectation framing for unusual durations."""
        summaries = [
            DailySummaryEntry(
                timestamp=datetime.utcnow(),
                scope="live_crypto",
                regime="PANIC",
                trades_executed=0,
                realized_pnl=0.0,
                max_drawdown=-0.1,
            )
            for _ in range(5)
        ]
        mock_summary_reader.get_summaries.return_value = summaries

        # Duration is 2x median (24h * 2)
        framing = analyzer.frame_expectation("live_crypto", "PANIC", duration_hours=50)

        assert framing is not None
        assert "unusual" in framing.lower()

    def test_frame_expectation_typical(self, analyzer, mock_summary_reader):
        """Test expectation framing for typical durations."""
        summaries = [
            DailySummaryEntry(
                timestamp=datetime.utcnow(),
                scope="live_crypto",
                regime="NEUTRAL",
                trades_executed=2,
                realized_pnl=0.0,
                max_drawdown=-0.01,
            )
            for _ in range(5)
        ]
        mock_summary_reader.get_summaries.return_value = summaries

        # Duration matches median
        framing = analyzer.frame_expectation("live_crypto", "NEUTRAL", duration_hours=24)

        assert framing is not None
        assert "typical" in framing.lower()

    def test_has_happened_before_no_trades(self, analyzer, mock_summary_reader):
        """Test detection of no_trades condition historically."""
        summaries = [
            DailySummaryEntry(
                timestamp=datetime.utcnow(),
                scope="live_crypto",
                regime="NEUTRAL",
                trades_executed=0,  # No trades
                realized_pnl=0.0,
                max_drawdown=0.0,
            ),
            DailySummaryEntry(
                timestamp=datetime.utcnow(),
                scope="live_crypto",
                regime="RISK_ON",
                trades_executed=5,
                realized_pnl=100.0,
                max_drawdown=-0.02,
            ),
        ]
        mock_summary_reader.get_summaries.return_value = summaries

        has_occurred = analyzer.has_happened_before("live_crypto", "no_trades")
        assert has_occurred is True

    def test_has_happened_before_panic(self, analyzer, mock_summary_reader):
        """Test detection of panic regime historically."""
        summaries = [
            DailySummaryEntry(
                timestamp=datetime.utcnow(),
                scope="live_crypto",
                regime="PANIC",
                trades_executed=0,
                realized_pnl=-500.0,
                max_drawdown=-0.15,
            ),
        ]
        mock_summary_reader.get_summaries.return_value = summaries

        has_occurred = analyzer.has_happened_before("live_crypto", "panic_regime")
        assert has_occurred is True

    def test_has_happened_before_false(self, analyzer, mock_summary_reader):
        """Test when condition hasn't happened before."""
        summaries = [
            DailySummaryEntry(
                timestamp=datetime.utcnow(),
                scope="live_crypto",
                regime="RISK_ON",
                trades_executed=5,
                realized_pnl=100.0,
                max_drawdown=-0.02,
            ),
        ]
        mock_summary_reader.get_summaries.return_value = summaries

        has_occurred = analyzer.has_happened_before("live_crypto", "panic_regime")
        assert has_occurred is False

    def test_get_typical_pattern(self, analyzer, mock_summary_reader):
        """Test getting typical pattern for regime."""
        summaries = [
            DailySummaryEntry(
                timestamp=datetime.utcnow(),
                scope="live_crypto",
                regime="RISK_ON",
                trades_executed=5,
                realized_pnl=100.0,
                max_drawdown=-0.02,
            )
            for _ in range(10)
        ]
        mock_summary_reader.get_summaries.return_value = summaries

        pattern = analyzer.get_typical_pattern("live_crypto", "RISK_ON")

        assert pattern is not None
        assert "common" in pattern.lower()
