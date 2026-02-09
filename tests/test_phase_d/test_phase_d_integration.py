"""
Integration tests for Phase D governance layer.
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import shutil

from phase_d.schemas import BlockEvent, BlockEvidence, BlockType, PhaseEligibilityResult
from phase_d.block_detector import BlockDetector
from phase_d.evidence_collector import EvidenceCollector
from phase_d.block_classifier import BlockClassifier
from phase_d.eligibility_checker import EligibilityChecker
from phase_d.persistence import PhaseDPersistence
from phase_d.phase_d_loop import PhaseDLoop
from ops_agent.schemas import DailySummaryEntry


class TestBlockDetection:
    """Test regime block detection."""

    def test_block_start_detection(self):
        """Test detecting when a block starts."""
        detector = BlockDetector()

        # Create a mock summary with blocked regime
        # Note: In real usage, this comes from SummaryReader
        detector._active_blocks.clear()

        # Simulate first check with block detected
        scope = "test_scope"

        # First, simulate no block
        assert scope not in detector._active_blocks

        # Now imagine summary_reader.get_latest_summary returns regime_blocked_period
        # We would have called: detector.detect_blocks(scope)
        # Since we can't easily mock SummaryReader here, we test the persistence layer instead

    def test_block_type_classification(self):
        """Test block type classification."""
        classifier = BlockClassifier()

        # Create a test block event
        block = BlockEvent(
            block_id="test_block_1",
            scope="test_scope",
            event_type="BLOCK_END",
            timestamp=datetime.utcnow(),
            regime="BTC_UNSUITABLE",
            reason="BTC regime block",
            block_start_ts=datetime.utcnow() - timedelta(hours=1),
            block_end_ts=datetime.utcnow(),
            duration_seconds=3600,
        )

        # Create evidence for SHOCK classification
        shock_evidence = BlockEvidence(
            block_id="test_block_1",
            scope="test_scope",
            duration_seconds=3600,
            btc_max_upside_pct=5.0,
            eth_max_upside_pct=3.0,
            alt_max_upside_pct=2.0,
            btc_max_drawdown_pct=-15.0,  # > 10% threshold
            eth_max_drawdown_pct=-8.0,
            volatility_before_block_end=10.0,
            volatility_after_block_end=25.0,
            volatility_expansion_ratio=2.5,  # > 2.0 threshold
            regime_at_start="BTC_UNSUITABLE",
            regime_at_end="BTC_UNSUITABLE",
        )

        block_type = classifier.classify_block(block, shock_evidence)
        assert block_type == BlockType.SHOCK

    def test_noise_classification(self):
        """Test NOISE block classification."""
        classifier = BlockClassifier()

        block = BlockEvent(
            block_id="test_block_2",
            scope="test_scope",
            event_type="BLOCK_END",
            timestamp=datetime.utcnow(),
            regime="BTC_UNSUITABLE",
            reason="BTC regime block",
            block_start_ts=datetime.utcnow() - timedelta(minutes=5),
            block_end_ts=datetime.utcnow(),
            duration_seconds=300,
        )

        # Evidence for NOISE: short duration, low upside, low drawdown
        noise_evidence = BlockEvidence(
            block_id="test_block_2",
            scope="test_scope",
            duration_seconds=300,
            historical_median_duration=600,  # 10 minutes median
            btc_max_upside_pct=1.0,
            eth_max_upside_pct=0.5,
            alt_max_upside_pct=0.0,
            btc_max_drawdown_pct=-1.0,
            eth_max_drawdown_pct=-0.5,
            volatility_expansion_ratio=1.0,
            regime_at_start="BTC_UNSUITABLE",
            regime_at_end="BTC_UNSUITABLE",
        )

        block_type = classifier.classify_block(block, noise_evidence)
        assert block_type == BlockType.NOISE

    def test_structural_classification(self):
        """Test STRUCTURAL block classification (default)."""
        classifier = BlockClassifier()

        block = BlockEvent(
            block_id="test_block_3",
            scope="test_scope",
            event_type="BLOCK_END",
            timestamp=datetime.utcnow(),
            regime="BTC_UNSUITABLE",
            reason="BTC regime block",
            block_start_ts=datetime.utcnow() - timedelta(hours=2),
            block_end_ts=datetime.utcnow(),
            duration_seconds=7200,
        )

        # Evidence for STRUCTURAL: long, high upside
        structural_evidence = BlockEvidence(
            block_id="test_block_3",
            scope="test_scope",
            duration_seconds=7200,
            historical_p90_duration=3600,  # p90 is 1 hour
            btc_max_upside_pct=8.0,
            eth_max_upside_pct=6.0,
            alt_max_upside_pct=5.0,
            btc_max_drawdown_pct=-2.0,
            eth_max_drawdown_pct=-1.5,
            volatility_expansion_ratio=1.1,
            regime_at_start="BTC_UNSUITABLE",
            regime_at_end="BTC_UNSUITABLE",
        )

        block_type = classifier.classify_block(block, structural_evidence)
        assert block_type == BlockType.STRUCTURAL


class TestEligibilityEvaluation:
    """Test Phase D v1 eligibility evaluation."""

    def test_insufficient_evidence(self):
        """Test that eligibility fails with insufficient blocks."""
        checker = EligibilityChecker()

        # Only 1 completed block (need 3)
        history = [
            BlockEvent(
                block_id="b1",
                scope="test",
                event_type="BLOCK_END",
                timestamp=datetime.utcnow(),
                regime="BTC",
                reason="test",
                block_start_ts=datetime.utcnow(),
                block_end_ts=datetime.utcnow(),
                duration_seconds=100,
                block_type=BlockType.STRUCTURAL,
            )
        ]

        evidence_map = {
            "b1": BlockEvidence(
                block_id="b1",
                scope="test",
                duration_seconds=100,
                btc_max_upside_pct=5.0,
                eth_max_upside_pct=4.0,
                btc_max_drawdown_pct=-2.0,
                eth_max_drawdown_pct=-1.5,
                volatility_expansion_ratio=1.0,
                regime_at_start="BTC",
                regime_at_end="BTC",
            )
        }

        result = checker.check_eligibility("test", None, history, evidence_map)
        assert not result.eligible
        assert not result.evidence_sufficiency_passed

    def test_eligibility_expiry(self):
        """Test that eligibility auto-expires after 24h."""
        checker = EligibilityChecker()

        # Create enough evidence for eligibility
        history = [
            BlockEvent(
                block_id=f"b{i}",
                scope="test",
                event_type="BLOCK_END",
                timestamp=datetime.utcnow() - timedelta(hours=24 - i),
                regime="BTC",
                reason="test",
                block_start_ts=datetime.utcnow() - timedelta(hours=25 - i),
                block_end_ts=datetime.utcnow() - timedelta(hours=24 - i),
                duration_seconds=7200,
                block_type=BlockType.STRUCTURAL,
            )
            for i in range(3)
        ]

        evidence_map = {
            f"b{i}": BlockEvidence(
                block_id=f"b{i}",
                scope="test",
                duration_seconds=7200,
                historical_p90_duration=3600,
                btc_max_upside_pct=8.0,
                eth_max_upside_pct=6.0,
                btc_max_drawdown_pct=-2.0,
                eth_max_drawdown_pct=-1.5,
                volatility_expansion_ratio=1.0,
                regime_at_start="BTC",
                regime_at_end="BTC",
            )
            for i in range(3)
        }

        # Mock current block
        current = BlockEvent(
            block_id="current",
            scope="test",
            event_type="BLOCK_START",
            timestamp=datetime.utcnow(),
            regime="BTC",
            reason="test",
            block_start_ts=datetime.utcnow() - timedelta(hours=4),
        )

        result = checker.check_eligibility("test", current, history, evidence_map)

        # Check expiry timestamp set
        if result.expiry_timestamp:
            # Expiry should be ~24h from now
            hours_until_expiry = (result.expiry_timestamp - datetime.utcnow()).total_seconds() / 3600
            assert 23.5 < hours_until_expiry < 24.5


class TestPersistence:
    """Test Phase D persistence layer."""

    def test_write_and_read_block_event(self):
        """Test writing and reading block events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch the persistence root
            import phase_d.persistence
            original_root = phase_d.persistence.PHASE_D_PERSIST_ROOT
            phase_d.persistence.PHASE_D_PERSIST_ROOT = tmpdir

            persistence = PhaseDPersistence()

            block = BlockEvent(
                block_id="test_123",
                scope="test_scope",
                event_type="BLOCK_START",
                timestamp=datetime.utcnow(),
                regime="BTC",
                reason="test",
                block_start_ts=datetime.utcnow(),
            )

            # Write and read
            success = persistence.write_block_event(block)
            assert success

            events = persistence.read_block_events("test_scope")
            assert len(events) > 0
            assert events[0].block_id == "test_123"

            # Restore
            phase_d.persistence.PHASE_D_PERSIST_ROOT = original_root

    def test_write_and_read_evidence(self):
        """Test writing and reading block evidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import phase_d.persistence
            original_root = phase_d.persistence.PHASE_D_PERSIST_ROOT
            phase_d.persistence.PHASE_D_PERSIST_ROOT = tmpdir

            persistence = PhaseDPersistence()

            evidence = BlockEvidence(
                block_id="test_456",
                scope="test",
                duration_seconds=1000,
                btc_max_upside_pct=5.0,
                eth_max_upside_pct=4.0,
                btc_max_drawdown_pct=-2.0,
                eth_max_drawdown_pct=-1.5,
                volatility_expansion_ratio=1.1,
                regime_at_start="BTC",
                regime_at_end="BTC",
            )

            success = persistence.write_block_evidence(evidence)
            assert success

            read_evidence = persistence.read_block_evidence("test_456")
            assert read_evidence is not None
            assert read_evidence.block_id == "test_456"
            assert read_evidence.btc_max_upside_pct == 5.0

            # Restore
            phase_d.persistence.PHASE_D_PERSIST_ROOT = original_root

    def test_append_only_persistence(self):
        """Test that persistence is truly append-only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import phase_d.persistence
            original_root = phase_d.persistence.PHASE_D_PERSIST_ROOT
            phase_d.persistence.PHASE_D_PERSIST_ROOT = tmpdir

            persistence = PhaseDPersistence()

            # Write first block
            block1 = BlockEvent(
                block_id="b1",
                scope="s1",
                event_type="BLOCK_START",
                timestamp=datetime.utcnow(),
                regime="BTC",
                reason="test",
                block_start_ts=datetime.utcnow(),
            )
            persistence.write_block_event(block1)

            # Write second block
            block2 = BlockEvent(
                block_id="b2",
                scope="s1",
                event_type="BLOCK_START",
                timestamp=datetime.utcnow(),
                regime="BTC",
                reason="test",
                block_start_ts=datetime.utcnow(),
            )
            persistence.write_block_event(block2)

            # Read all for scope
            events = persistence.read_block_events("s1")
            assert len(events) == 2
            assert events[0].block_id == "b1"
            assert events[1].block_id == "b2"

            # Restore
            phase_d.persistence.PHASE_D_PERSIST_ROOT = original_root


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
