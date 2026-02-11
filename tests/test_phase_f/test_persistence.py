"""
Tests for Phase F Persistence (append-only memory).
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from phase_f.persistence import Phase_F_Persistence
from phase_f.schemas import (
    EpistemicMemoryEvent,
    Verdict,
    VerdictType,
    Hypothesis,
)


@pytest.fixture
def temp_persist():
    """Create temporary persistence directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persist = Phase_F_Persistence(root=tmpdir)
        yield persist


class TestAppendOnlyEpisodic:
    """Test append-only episodic memory."""

    def test_append_single_event(self, temp_persist):
        """Append single event to episodic memory."""
        event = EpistemicMemoryEvent(
            timestamp="2026-02-11T10:30:00Z",
            event_type="EXTERNAL_CLAIM",
            source="CoinTelegraph",
            claim="Bitcoin difficulty at ATH",
            market_snapshot={"regime": "RISK_ON"},
        )

        temp_persist.append_episodic_event(event)

        # Verify file exists
        assert temp_persist.episodic_path.exists()

        # Verify content
        with open(temp_persist.episodic_path) as f:
            line = f.readline()
            data = json.loads(line)
            assert data["claim"] == "Bitcoin difficulty at ATH"

    def test_append_multiple_events(self, temp_persist):
        """Append multiple events preserves all."""
        events = [
            EpistemicMemoryEvent(
                timestamp=f"2026-02-11T{i:02d}:00:00Z",
                event_type="EXTERNAL_CLAIM",
                source=f"Source{i}",
                claim=f"Claim {i}",
                market_snapshot={},
            )
            for i in range(5)
        ]

        for event in events:
            temp_persist.append_episodic_event(event)

        # Read back
        read_events = temp_persist.read_episodic_events()
        assert len(read_events) == 5

    def test_never_overwrite(self, temp_persist):
        """Append never overwrites existing file."""
        event1 = EpistemicMemoryEvent(
            timestamp="2026-02-11T10:00:00Z",
            event_type="EXTERNAL_CLAIM",
            source="Source1",
            claim="Claim1",
            market_snapshot={},
        )
        event2 = EpistemicMemoryEvent(
            timestamp="2026-02-11T11:00:00Z",
            event_type="EXTERNAL_CLAIM",
            source="Source2",
            claim="Claim2",
            market_snapshot={},
        )

        temp_persist.append_episodic_event(event1)
        temp_persist.append_episodic_event(event2)

        # Both should exist
        read_events = temp_persist.read_episodic_events()
        assert len(read_events) == 2
        assert read_events[0].claim == "Claim1"
        assert read_events[1].claim == "Claim2"

    def test_read_with_lookback_filter(self, temp_persist):
        """Read respects lookback_days filter."""
        now = datetime.utcnow()

        # Create event from 60 days ago
        old_time = (now - timedelta(days=60)).isoformat() + "Z"
        old_event = EpistemicMemoryEvent(
            timestamp=old_time,
            event_type="EXTERNAL_CLAIM",
            source="Old",
            claim="Old claim",
            market_snapshot={},
        )

        # Create recent event
        recent_time = now.isoformat() + "Z"
        recent_event = EpistemicMemoryEvent(
            timestamp=recent_time,
            event_type="EXTERNAL_CLAIM",
            source="Recent",
            claim="Recent claim",
            market_snapshot={},
        )

        temp_persist.append_episodic_event(old_event)
        temp_persist.append_episodic_event(recent_event)

        # Read with 30 day lookback (should exclude old)
        read_events = temp_persist.read_episodic_events(lookback_days=30)
        assert len(read_events) == 1
        assert read_events[0].claim == "Recent claim"

    def test_find_similar_claims(self, temp_persist):
        """Find similar past claims."""
        events = [
            EpistemicMemoryEvent(
                timestamp="2026-02-11T10:00:00Z",
                event_type="EXTERNAL_CLAIM",
                source="Source1",
                claim="Bitcoin difficulty reaches new high",
                market_snapshot={},
            ),
            EpistemicMemoryEvent(
                timestamp="2026-02-11T11:00:00Z",
                event_type="EXTERNAL_CLAIM",
                source="Source2",
                claim="Ethereum gas fees increase",
                market_snapshot={},
            ),
            EpistemicMemoryEvent(
                timestamp="2026-02-11T12:00:00Z",
                event_type="EXTERNAL_CLAIM",
                source="Source3",
                claim="Bitcoin difficulty reaches ATH again",
                market_snapshot={},
            ),
        ]

        for event in events:
            temp_persist.append_episodic_event(event)

        # Search for "Bitcoin difficulty"
        similar = temp_persist.find_similar_claims("Bitcoin difficulty")
        assert len(similar) == 2


class TestAppendOnlyVerdicts:
    """Test append-only verdict history."""

    def test_append_verdict(self, temp_persist):
        """Append verdict to verdict history."""
        verdict = Verdict(
            verdict=VerdictType.REGIME_VALIDATED,
            regime_confidence=0.80,
            confidence_change_from_internal=0.0,
            narrative_consistency="HIGH",
            num_sources_analyzed=10,
            num_contradictions=0,
            summary_for_governance="Regime validated",
            reasoning_summary="All sources agree",
        )

        temp_persist.append_verdict(verdict, run_id="run_001")

        # Verify file exists
        assert temp_persist.verdicts_path.exists()

    def test_read_verdicts(self, temp_persist):
        """Read verdict history."""
        verdicts = [
            Verdict(
                verdict=VerdictType.REGIME_VALIDATED,
                regime_confidence=0.80 + i * 0.05,
                confidence_change_from_internal=0.0,
                narrative_consistency="MODERATE",
                num_sources_analyzed=10,
                num_contradictions=0,
                summary_for_governance="Test",
                reasoning_summary="Test",
            )
            for i in range(3)
        ]

        for i, verdict in enumerate(verdicts):
            temp_persist.append_verdict(verdict, run_id=f"run_{i:03d}")

        # Read back
        read_verdicts = temp_persist.read_verdicts()
        assert len(read_verdicts) == 3

    def test_get_latest_verdict(self, temp_persist):
        """Get most recent verdict."""
        verdict1 = Verdict(
            verdict=VerdictType.REGIME_VALIDATED,
            regime_confidence=0.70,
            confidence_change_from_internal=0.0,
            narrative_consistency="MODERATE",
            num_sources_analyzed=5,
            num_contradictions=0,
            summary_for_governance="Test1",
            reasoning_summary="Test",
        )
        verdict2 = Verdict(
            verdict=VerdictType.REGIME_QUESTIONABLE,
            regime_confidence=0.55,
            confidence_change_from_internal=-0.15,
            narrative_consistency="LOW",
            num_sources_analyzed=8,
            num_contradictions=2,
            summary_for_governance="Test2",
            reasoning_summary="Test",
        )

        temp_persist.append_verdict(verdict1, run_id="run_001")
        temp_persist.append_verdict(verdict2, run_id="run_002")

        latest = temp_persist.get_latest_verdict()
        assert latest is not None
        assert latest["verdict"]["verdict"] == VerdictType.REGIME_QUESTIONABLE.value


class TestSemanticMemory:
    """Test versioned semantic memory."""

    def test_write_semantic_summary(self, temp_persist):
        """Write semantic summary (versioned)."""
        from phase_f.schemas import SemanticMemorySummary

        summary = SemanticMemorySummary(
            period_start="2026-02-01",
            period_end="2026-02-28",
            version=1,
            patterns=[
                {"pattern": "BTC ATH occurs", "frequency": 0.3, "confidence": 0.7}
            ],
        )

        temp_persist.write_semantic_summary(summary)

        # Verify file exists
        files = list(temp_persist.semantic_dir.glob("semantic_*.json"))
        assert len(files) == 1

    def test_read_semantic_summary(self, temp_persist):
        """Read semantic summary by period and version."""
        from phase_f.schemas import SemanticMemorySummary

        summary = SemanticMemorySummary(
            period_start="2026-02-01",
            period_end="2026-02-28",
            version=1,
            patterns=[
                {"pattern": "Test pattern", "frequency": 0.5, "confidence": 0.8}
            ],
        )

        temp_persist.write_semantic_summary(summary)

        # Read back
        read = temp_persist.read_semantic_summary("2026-02-01", "2026-02-28", version=1)
        assert read is not None
        assert len(read.patterns) == 1
        assert read.version == 1

    def test_versioning_no_overwrite(self, temp_persist):
        """Versioning prevents overwrites."""
        from phase_f.schemas import SemanticMemorySummary

        summary_v1 = SemanticMemorySummary(
            period_start="2026-02-01",
            period_end="2026-02-28",
            version=1,
            patterns=[{"pattern": "Pattern1", "frequency": 0.3}],
        )
        summary_v2 = SemanticMemorySummary(
            period_start="2026-02-01",
            period_end="2026-02-28",
            version=2,
            patterns=[{"pattern": "Pattern2", "frequency": 0.5}],
        )

        temp_persist.write_semantic_summary(summary_v1)
        temp_persist.write_semantic_summary(summary_v2)

        # Both should exist
        files = list(temp_persist.semantic_dir.glob("semantic_*.json"))
        assert len(files) == 2

    def test_list_semantic_summaries(self, temp_persist):
        """List all semantic summaries."""
        from phase_f.schemas import SemanticMemorySummary

        summaries = [
            SemanticMemorySummary(
                period_start=f"2026-{i:02d}-01",
                period_end=f"2026-{i:02d}-28",
                version=1,
                patterns=[],
            )
            for i in range(1, 4)
        ]

        for summary in summaries:
            temp_persist.write_semantic_summary(summary)

        filenames = temp_persist.list_semantic_summaries()
        assert len(filenames) == 3
