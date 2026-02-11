"""
Tests for Phase F Logging (phase_f/logging.py)

Tests the three-layer transparency logging system.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime

from phase_f.logging import PhaseFLogger
from phase_f.schemas import Verdict, VerdictType, NarrativeConsistency


def setup_test_logger(tmpdir):
    """Helper to set up logger with temp directory."""
    logger = PhaseFLogger(scope="crypto")
    logger.logs_dir = Path(tmpdir)
    logger.pipeline_log_file = logger.logs_dir / "pipeline.jsonl"
    logger.audit_trail_file = logger.logs_dir / "audit_trail.jsonl"
    logger.logs_dir.mkdir(parents=True, exist_ok=True)
    return logger


class TestLoggerInitialization:
    """Test logger initialization."""

    def test_logger_creates_logs_directory(self):
        """Test that logger creates logs directory."""
        logger = PhaseFLogger(scope="crypto")
        logs_dir = Path("persist/phase_f/crypto/logs")
        assert logger.logs_dir == logs_dir

    def test_logger_initializes_with_scope(self):
        """Test logger initialization with scope."""
        logger = PhaseFLogger(scope="test_scope")
        assert logger.scope == "test_scope"
        assert "test_scope" in str(logger.logs_dir)


class TestPipelineLogging:
    """Test Layer 1: Pipeline structured logging."""

    def test_log_run_start_creates_jsonl_entry(self):
        """Test that log_run_start creates a JSON entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = setup_test_logger(tmpdir)
            run_id = "phase_f_run_20260211_030000"
            logger.log_run_start(run_id)

            pipeline_log = logger.logs_dir / "pipeline.jsonl"
            assert pipeline_log.exists()

            with open(pipeline_log) as f:
                line = f.readline()
                entry = json.loads(line)

            assert entry["event"] == "RUN_START"
            assert entry["run_id"] == run_id
            assert "timestamp_utc" in entry
            assert entry["scope"] == "crypto"

    def test_log_stage_complete(self):
        """Test that log_stage_complete logs stage completion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = setup_test_logger(tmpdir)
            metrics = {"articles_fetched": 10, "claims_extracted": 25}
            logger.log_stage_complete("researcher", metrics)

            pipeline_log = logger.logs_dir / "pipeline.jsonl"
            with open(pipeline_log) as f:
                line = f.readline()
                entry = json.loads(line)

            assert entry["event"] == "STAGE_COMPLETE"
            assert entry["stage"] == "researcher"
            assert entry["metrics"] == metrics

    def test_log_run_complete_success(self):
        """Test that log_run_complete logs successful completion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = setup_test_logger(tmpdir)
            run_id = "phase_f_run_20260211_030000"
            logger.log_run_complete(run_id, success=True)

            pipeline_log = logger.logs_dir / "pipeline.jsonl"
            with open(pipeline_log) as f:
                line = f.readline()
                entry = json.loads(line)

            assert entry["event"] == "RUN_COMPLETE"
            assert entry["success"] is True
            assert entry["error"] is None

    def test_log_run_complete_failure(self):
        """Test that log_run_complete logs failures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = setup_test_logger(tmpdir)
            run_id = "phase_f_run_20260211_030000"
            error_msg = "Test error"
            logger.log_run_complete(run_id, success=False, error=error_msg)

            pipeline_log = logger.logs_dir / "pipeline.jsonl"
            with open(pipeline_log) as f:
                line = f.readline()
                entry = json.loads(line)

            assert entry["event"] == "RUN_COMPLETE"
            assert entry["success"] is False
            assert entry["error"] == error_msg

    def test_multiple_pipeline_logs_append(self):
        """Test that multiple logs append to same file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = setup_test_logger(tmpdir)
            logger.log_run_start("run1")
            logger.log_stage_complete("stage1", {})
            logger.log_run_complete("run1", success=True)

            pipeline_log = logger.logs_dir / "pipeline.jsonl"
            with open(pipeline_log) as f:
                lines = f.readlines()

            assert len(lines) == 3
            assert json.loads(lines[0])["event"] == "RUN_START"
            assert json.loads(lines[1])["event"] == "STAGE_COMPLETE"
            assert json.loads(lines[2])["event"] == "RUN_COMPLETE"


class TestAuditTrailLogging:
    """Test Layer 3: Human audit trail logging."""

    def test_log_verdict_reasoning_creates_entry(self):
        """Test that log_verdict_reasoning creates an audit trail entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = setup_test_logger(tmpdir)

            verdict = Verdict(
                verdict=VerdictType.REGIME_VALIDATED,
                regime_confidence=0.85,
                confidence_change_from_internal=0.05,
                narrative_consistency=NarrativeConsistency.HIGH,
                reasoning_summary="Test reasoning",
                num_sources_analyzed=42,
                num_contradictions=3,
                summary_for_governance="Test governance summary"
            )

            run_id = "phase_f_run_20260211_030000"
            logger.log_verdict_reasoning(run_id, verdict)

            audit_file = logger.logs_dir / "audit_trail.jsonl"
            assert audit_file.exists()

            with open(audit_file) as f:
                line = f.readline()
                entry = json.loads(line)

            assert entry["run_id"] == run_id
            assert entry["verdict_type"] == "REGIME_VALIDATED"
            assert entry["regime_confidence"] == 0.85
            assert entry["confidence_change_from_internal"] == 0.05
            assert entry["narrative_consistency"] == "HIGH"
            assert "Test reasoning" in entry["reasoning_summary"]
            assert entry["num_sources_analyzed"] == 42
            assert entry["num_contradictions"] == 3

    def test_multiple_verdicts_append_to_audit_trail(self):
        """Test that multiple verdicts append to audit trail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = setup_test_logger(tmpdir)

            verdict1 = Verdict(
                verdict=VerdictType.REGIME_VALIDATED,
                regime_confidence=0.85,
                confidence_change_from_internal=0.0,
                narrative_consistency=NarrativeConsistency.HIGH,
                reasoning_summary="Verdict 1",
                num_sources_analyzed=10,
                num_contradictions=0,
                summary_for_governance="Summary 1"
            )

            verdict2 = Verdict(
                verdict=VerdictType.REGIME_QUESTIONABLE,
                regime_confidence=0.6,
                confidence_change_from_internal=-0.1,
                narrative_consistency=NarrativeConsistency.MODERATE,
                reasoning_summary="Verdict 2",
                num_sources_analyzed=15,
                num_contradictions=2,
                summary_for_governance="Summary 2"
            )

            logger.log_verdict_reasoning("run1", verdict1)
            logger.log_verdict_reasoning("run2", verdict2)

            audit_file = logger.logs_dir / "audit_trail.jsonl"
            with open(audit_file) as f:
                lines = f.readlines()

            assert len(lines) == 2
            entry1 = json.loads(lines[0])
            entry2 = json.loads(lines[1])

            assert entry1["verdict_type"] == "REGIME_VALIDATED"
            assert entry2["verdict_type"] == "REGIME_QUESTIONABLE"


class TestLoggingErrorHandling:
    """Test error handling in logging."""

    def test_pipeline_log_handles_write_error_gracefully(self):
        """Test that pipeline logging handles write errors gracefully."""
        logger = PhaseFLogger(scope="crypto")
        logger.logs_dir = Path("/root/nonexistent/path")
        logger.pipeline_log_file = logger.logs_dir / "pipeline.jsonl"

        # Should not raise
        logger.log_run_start("test_run")

    def test_audit_trail_log_handles_write_error_gracefully(self):
        """Test that audit logging handles write errors gracefully."""
        logger = PhaseFLogger(scope="crypto")
        logger.logs_dir = Path("/root/nonexistent/path")
        logger.audit_trail_file = logger.logs_dir / "audit_trail.jsonl"

        verdict = Verdict(
            verdict=VerdictType.REGIME_VALIDATED,
            regime_confidence=0.85,
            confidence_change_from_internal=0.0,
            narrative_consistency=NarrativeConsistency.HIGH,
            reasoning_summary="Test",
            num_sources_analyzed=10,
            num_contradictions=0,
            summary_for_governance="Test summary"
        )

        # Should not raise
        logger.log_verdict_reasoning("run1", verdict)


class TestLayerIntegration:
    """Test all layers working together."""

    def test_full_logging_pipeline(self):
        """Test full logging pipeline from start to verdict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = setup_test_logger(tmpdir)
            run_id = "phase_f_run_test"

            # Layer 1: Run start
            logger.log_run_start(run_id)

            # Layer 1: Stage completions
            logger.log_stage_complete("researcher", {"articles": 10})
            logger.log_stage_complete("critic", {"challenges": 5})
            logger.log_stage_complete("reviewer", {"verdict": "VALIDATED"})

            # Layer 3: Verdict reasoning
            verdict = Verdict(
                verdict=VerdictType.REGIME_VALIDATED,
                regime_confidence=0.85,
                confidence_change_from_internal=0.0,
                narrative_consistency=NarrativeConsistency.HIGH,
                reasoning_summary="All checks passed",
                num_sources_analyzed=10,
                num_contradictions=0,
                summary_for_governance="Regime is validated"
            )
            logger.log_verdict_reasoning(run_id, verdict)

            # Layer 1: Run complete
            logger.log_run_complete(run_id, success=True)

            # Verify all files exist and have correct number of entries
            pipeline_log = logger.logs_dir / "pipeline.jsonl"
            audit_file = logger.logs_dir / "audit_trail.jsonl"

            assert pipeline_log.exists()
            assert audit_file.exists()

            with open(pipeline_log) as f:
                pipeline_lines = f.readlines()
            with open(audit_file) as f:
                audit_lines = f.readlines()

            assert len(pipeline_lines) == 5  # start + 3 stages + complete
            assert len(audit_lines) == 1  # 1 verdict
