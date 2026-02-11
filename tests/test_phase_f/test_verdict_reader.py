"""
Tests for Governance Verdict Reader (governance/verdict_reader.py)

Tests reading Phase F verdicts for governance consumption.
"""

import pytest
import json
import tempfile
from pathlib import Path

from governance.verdict_reader import VerdictReader


class TestVerdictReaderInitialization:
    """Test verdict reader initialization."""

    def test_reader_initializes_with_default_root(self):
        """Test reader initialization with default root."""
        reader = VerdictReader()

        assert reader.phase_f_root == Path("persist/phase_f")

    def test_reader_initializes_with_custom_root(self):
        """Test reader initialization with custom root."""
        custom_root = "/custom/path"
        reader = VerdictReader(phase_f_root=custom_root)

        assert reader.phase_f_root == Path(custom_root)


class TestReadingVerdicts:
    """Test reading verdicts."""

    def test_read_latest_verdict_returns_none_when_file_missing(self):
        """Test that reading returns None when verdict file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reader = VerdictReader(phase_f_root=tmpdir)

            verdict = reader.read_latest_verdict("crypto")

            assert verdict is None

    def test_read_latest_verdict_returns_none_when_file_empty(self):
        """Test that reading returns None when verdict file is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create empty file
            verdicts_dir = Path(tmpdir) / "crypto" / "verdicts"
            verdicts_dir.mkdir(parents=True, exist_ok=True)
            verdicts_file = verdicts_dir / "verdicts.jsonl"
            verdicts_file.touch()

            reader = VerdictReader(phase_f_root=tmpdir)
            verdict = reader.read_latest_verdict("crypto")

            assert verdict is None

    def test_read_latest_verdict_returns_most_recent(self):
        """Test that reading returns the most recent verdict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create verdict file with multiple entries
            verdicts_dir = Path(tmpdir) / "crypto" / "verdicts"
            verdicts_dir.mkdir(parents=True, exist_ok=True)
            verdicts_file = verdicts_dir / "verdicts.jsonl"

            verdict1 = {
                "run_id": "run1",
                "timestamp": "2026-02-10T03:00:00",
                "verdict": {"verdict": "REGIME_VALIDATED", "regime_confidence": 0.8}
            }
            verdict2 = {
                "run_id": "run2",
                "timestamp": "2026-02-11T03:00:00",
                "verdict": {"verdict": "REGIME_QUESTIONABLE", "regime_confidence": 0.6}
            }

            with open(verdicts_file, "w") as f:
                f.write(json.dumps(verdict1) + "\n")
                f.write(json.dumps(verdict2) + "\n")

            reader = VerdictReader(phase_f_root=tmpdir)
            latest = reader.read_latest_verdict("crypto")

            assert latest["run_id"] == "run2"
            assert latest["verdict"]["verdict"] == "REGIME_QUESTIONABLE"

    def test_read_latest_verdict_handles_malformed_json(self):
        """Test that reading handles malformed JSON gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            verdicts_dir = Path(tmpdir) / "crypto" / "verdicts"
            verdicts_dir.mkdir(parents=True, exist_ok=True)
            verdicts_file = verdicts_dir / "verdicts.jsonl"

            # Write valid and invalid JSON
            verdict_valid = {
                "run_id": "run1",
                "timestamp": "2026-02-11T03:00:00",
                "verdict": {"verdict": "REGIME_VALIDATED"}
            }

            with open(verdicts_file, "w") as f:
                f.write(json.dumps(verdict_valid) + "\n")
                f.write("invalid json\n")

            reader = VerdictReader(phase_f_root=tmpdir)
            latest = reader.read_latest_verdict("crypto")

            # Should still return None due to malformed last line
            # or should return the valid one if not last line
            # Current implementation reads last line, so malformed will return None
            assert latest is None


class TestGovernanceSummary:
    """Test governance summary extraction."""

    def test_get_governance_summary_returns_summary(self):
        """Test getting governance summary from verdict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            verdicts_dir = Path(tmpdir) / "crypto" / "verdicts"
            verdicts_dir.mkdir(parents=True, exist_ok=True)
            verdicts_file = verdicts_dir / "verdicts.jsonl"

            verdict = {
                "run_id": "run1",
                "timestamp": "2026-02-11T03:00:00",
                "verdict": {
                    "verdict": "REGIME_VALIDATED",
                    "summary_for_governance": "Regime is stable and validated"
                }
            }

            with open(verdicts_file, "w") as f:
                f.write(json.dumps(verdict) + "\n")

            reader = VerdictReader(phase_f_root=tmpdir)
            summary = reader.get_governance_summary("crypto")

            assert summary == "Regime is stable and validated"

    def test_get_governance_summary_returns_none_if_missing(self):
        """Test that getting summary returns None if not available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            verdicts_dir = Path(tmpdir) / "crypto" / "verdicts"
            verdicts_dir.mkdir(parents=True, exist_ok=True)
            verdicts_file = verdicts_dir / "verdicts.jsonl"

            verdict = {
                "run_id": "run1",
                "timestamp": "2026-02-11T03:00:00",
                "verdict": {"verdict": "REGIME_VALIDATED"}
            }

            with open(verdicts_file, "w") as f:
                f.write(json.dumps(verdict) + "\n")

            reader = VerdictReader(phase_f_root=tmpdir)
            summary = reader.get_governance_summary("crypto")

            assert summary is None


class TestConfidencyPenalty:
    """Test confidence penalty calculation."""

    def test_should_apply_penalty_for_regime_questionable(self):
        """Test that penalty is applied for REGIME_QUESTIONABLE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            verdicts_dir = Path(tmpdir) / "crypto" / "verdicts"
            verdicts_dir.mkdir(parents=True, exist_ok=True)
            verdicts_file = verdicts_dir / "verdicts.jsonl"

            verdict = {
                "run_id": "run1",
                "timestamp": "2026-02-11T03:00:00",
                "verdict": {"verdict": "REGIME_QUESTIONABLE"}
            }

            with open(verdicts_file, "w") as f:
                f.write(json.dumps(verdict) + "\n")

            reader = VerdictReader(phase_f_root=tmpdir)
            should_apply = reader.should_apply_confidence_penalty("crypto")

            assert should_apply is True

    def test_should_apply_penalty_for_high_noise(self):
        """Test that penalty is applied for HIGH_NOISE_NO_ACTION."""
        with tempfile.TemporaryDirectory() as tmpdir:
            verdicts_dir = Path(tmpdir) / "crypto" / "verdicts"
            verdicts_dir.mkdir(parents=True, exist_ok=True)
            verdicts_file = verdicts_dir / "verdicts.jsonl"

            verdict = {
                "run_id": "run1",
                "timestamp": "2026-02-11T03:00:00",
                "verdict": {"verdict": "HIGH_NOISE_NO_ACTION"}
            }

            with open(verdicts_file, "w") as f:
                f.write(json.dumps(verdict) + "\n")

            reader = VerdictReader(phase_f_root=tmpdir)
            should_apply = reader.should_apply_confidence_penalty("crypto")

            assert should_apply is True

    def test_should_not_apply_penalty_for_regime_validated(self):
        """Test that no penalty is applied for REGIME_VALIDATED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            verdicts_dir = Path(tmpdir) / "crypto" / "verdicts"
            verdicts_dir.mkdir(parents=True, exist_ok=True)
            verdicts_file = verdicts_dir / "verdicts.jsonl"

            verdict = {
                "run_id": "run1",
                "timestamp": "2026-02-11T03:00:00",
                "verdict": {"verdict": "REGIME_VALIDATED"}
            }

            with open(verdicts_file, "w") as f:
                f.write(json.dumps(verdict) + "\n")

            reader = VerdictReader(phase_f_root=tmpdir)
            should_apply = reader.should_apply_confidence_penalty("crypto")

            assert should_apply is False

    def test_get_penalty_factor_returns_correct_multipliers(self):
        """Test that penalty factors are correct."""
        with tempfile.TemporaryDirectory() as tmpdir:
            verdicts_dir = Path(tmpdir) / "crypto" / "verdicts"
            verdicts_dir.mkdir(parents=True, exist_ok=True)
            verdicts_file = verdicts_dir / "verdicts.jsonl"

            reader = VerdictReader(phase_f_root=tmpdir)

            # Test REGIME_QUESTIONABLE (20% penalty)
            verdict = {
                "run_id": "run1",
                "timestamp": "2026-02-11T03:00:00",
                "verdict": {"verdict": "REGIME_QUESTIONABLE"}
            }
            with open(verdicts_file, "w") as f:
                f.write(json.dumps(verdict) + "\n")

            assert reader.get_penalty_factor("crypto") == 0.8

            # Test HIGH_NOISE (30% penalty)
            verdict["verdict"]["verdict"] = "HIGH_NOISE_NO_ACTION"
            with open(verdicts_file, "w") as f:
                f.write(json.dumps(verdict) + "\n")

            assert reader.get_penalty_factor("crypto") == 0.7

            # Test POSSIBLE_STRUCTURAL_SHIFT (10% penalty)
            verdict["verdict"]["verdict"] = "POSSIBLE_STRUCTURAL_SHIFT_OBSERVE"
            with open(verdicts_file, "w") as f:
                f.write(json.dumps(verdict) + "\n")

            assert reader.get_penalty_factor("crypto") == 0.9

            # Test REGIME_VALIDATED (no penalty)
            verdict["verdict"]["verdict"] = "REGIME_VALIDATED"
            with open(verdicts_file, "w") as f:
                f.write(json.dumps(verdict) + "\n")

            assert reader.get_penalty_factor("crypto") == 1.0

    def test_get_penalty_factor_returns_1_0_when_no_verdict(self):
        """Test that penalty factor is 1.0 when no verdict exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reader = VerdictReader(phase_f_root=tmpdir)

            factor = reader.get_penalty_factor("crypto")

            assert factor == 1.0


class TestVerdictMetadata:
    """Test verdict metadata extraction."""

    def test_get_verdict_metadata_returns_all_fields(self):
        """Test that metadata includes all verdict fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            verdicts_dir = Path(tmpdir) / "crypto" / "verdicts"
            verdicts_dir.mkdir(parents=True, exist_ok=True)
            verdicts_file = verdicts_dir / "verdicts.jsonl"

            verdict = {
                "run_id": "phase_f_run_20260211_030000",
                "timestamp": "2026-02-11T03:00:00",
                "verdict": {
                    "verdict": "REGIME_VALIDATED",
                    "regime_confidence": 0.85,
                    "narrative_consistency": "HIGH",
                    "num_sources_analyzed": 42,
                    "num_contradictions": 3
                }
            }

            with open(verdicts_file, "w") as f:
                f.write(json.dumps(verdict) + "\n")

            reader = VerdictReader(phase_f_root=tmpdir)
            metadata = reader.get_verdict_metadata("crypto")

            assert metadata is not None
            assert metadata["phase_f_run_id"] == "phase_f_run_20260211_030000"
            assert metadata["phase_f_verdict_timestamp"] == "2026-02-11T03:00:00"
            assert metadata["phase_f_verdict_type"] == "REGIME_VALIDATED"
            assert metadata["phase_f_regime_confidence"] == 0.85
            assert metadata["phase_f_narrative_consistency"] == "HIGH"
            assert metadata["phase_f_num_sources"] == 42
            assert metadata["phase_f_num_contradictions"] == 3

    def test_get_verdict_metadata_returns_none_when_missing(self):
        """Test that metadata returns None when verdict missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reader = VerdictReader(phase_f_root=tmpdir)

            metadata = reader.get_verdict_metadata("crypto")

            assert metadata is None
