"""
Tests for Phase F Job Orchestrator (phase_f/phase_f_job.py)

Tests the full pipeline execution: Researcher → Critic → Reviewer → Verdict
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from phase_f.phase_f_job import PhaseFJob, run_phase_f_job
from phase_f.schemas import Verdict, VerdictType, NarrativeConsistency


class TestPhaseFJobInitialization:
    """Test Phase F job initialization."""

    def test_job_initializes_with_defaults(self):
        """Test job initialization with default scope."""
        job = PhaseFJob(scope="crypto")

        assert job.scope == "crypto"
        assert job.persistence is not None
        assert job.safety_validator is not None
        assert job.logger is not None

    def test_job_initializes_fetcher(self):
        """Test job initialization with fetcher."""
        job = PhaseFJob(scope="crypto")

        assert job.fetcher is not None

    def test_job_initializes_components(self):
        """Test that all components are initialized."""
        job = PhaseFJob()

        assert job.fetcher is not None
        assert job.claim_extractor is not None
        assert job.hypothesis_builder is not None
        assert job.critic is not None
        assert job.reviewer is not None


class TestPipelineExecution:
    """Test full pipeline execution."""

    @patch('phase_f.phase_f_job.PHASE_F_ENABLED', True)
    @patch('phase_f.phase_f_job.PHASE_F_KILL_SWITCH', False)
    def test_run_executes_full_pipeline(self):
        """Test that run() executes all pipeline stages."""
        job = PhaseFJob(scope="crypto")

        # Mock components
        job.fetcher.fetch_crypto_news = Mock(return_value=[
            {"title": "Test article", "content": "Test content", "url": "http://test.com"}
        ])
        job.claim_extractor.extract_from_article = Mock(return_value=[
            Mock(claim_text="Test claim", source="test")
        ])
        job.hypothesis_builder.build_hypotheses = Mock(return_value=[
            Mock(hypothesis="Test hypothesis")
        ])
        job.critic.challenge_hypothesis = Mock(return_value=[
            Mock(challenge="Test challenge")
        ])
        job.reviewer.produce_verdict = Mock(return_value=Mock(
            verdict=VerdictType.REGIME_VALIDATED,
            regime_confidence=0.85,
            confidence_change_from_internal=0.05,
            narrative_consistency=NarrativeConsistency.HIGH,
            reasoning_summary="Test reasoning",
            num_sources_analyzed=1,
            num_contradictions=0,
            summary_for_governance="Test summary"
        ))
        job.persistence.append_verdict = Mock()
        job.safety_validator.validate_verdict = Mock()

        success = job.run()

        assert success is True
        job.fetcher.fetch_crypto_news.assert_called_once()
        job.critic.challenge_hypothesis.assert_called_once()
        job.reviewer.produce_verdict.assert_called_once()
        job.persistence.append_verdict.assert_called_once()

    @patch('phase_f.phase_f_job.PHASE_F_ENABLED', True)
    @patch('phase_f.phase_f_job.PHASE_F_KILL_SWITCH', False)
    def test_run_returns_false_on_no_articles(self):
        """Test that run returns False when no articles are fetched."""
        job = PhaseFJob(scope="crypto")
        job.fetcher.fetch_crypto_news = Mock(return_value=[])

        success = job.run()

        assert success is False

    @patch('phase_f.phase_f_job.PHASE_F_ENABLED', True)
    @patch('phase_f.phase_f_job.PHASE_F_KILL_SWITCH', False)
    def test_run_returns_false_on_no_hypotheses(self):
        """Test that run returns False when no hypotheses are generated."""
        job = PhaseFJob(scope="crypto")
        job.fetcher.fetch_crypto_news = Mock(return_value=[
            {"title": "Test", "content": "Test", "url": "http://test.com"}
        ])
        job.claim_extractor.extract_from_article = Mock(return_value=[])
        job.hypothesis_builder.build_hypotheses = Mock(return_value=[])

        success = job.run()

        assert success is False

    @patch('phase_f.phase_f_job.PHASE_F_ENABLED', True)
    @patch('phase_f.phase_f_job.PHASE_F_KILL_SWITCH', False)
    def test_run_handles_exception_gracefully(self):
        """Test that run handles exceptions gracefully."""
        job = PhaseFJob(scope="crypto")
        job.fetcher.fetch_crypto_news = Mock(side_effect=Exception("Test error"))

        success = job.run()

        assert success is False

    @patch('phase_f.phase_f_job.PHASE_F_ENABLED', False)
    def test_run_respects_enabled_flag(self):
        """Test that run respects PHASE_F_ENABLED flag."""
        job = PhaseFJob(scope="crypto")
        job.fetcher.fetch_crypto_news = Mock()

        success = job.run()

        assert success is False
        job.fetcher.fetch_crypto_news.assert_not_called()

    @patch('phase_f.phase_f_job.PHASE_F_KILL_SWITCH', True)
    def test_run_respects_kill_switch(self):
        """Test that run respects PHASE_F_KILL_SWITCH."""
        job = PhaseFJob(scope="crypto")
        job.fetcher.fetch_crypto_news = Mock()

        success = job.run()

        assert success is False
        job.fetcher.fetch_crypto_news.assert_not_called()


class TestRegimeIntegration:
    """Test regime integration."""

    @patch('phase_f.phase_f_job.PHASE_F_ENABLED', True)
    @patch('phase_f.phase_f_job.PHASE_F_KILL_SWITCH', False)
    def test_run_gets_current_regime(self):
        """Test that run calls produce_verdict with regime parameters."""
        job = PhaseFJob(scope="crypto")

        job.fetcher.fetch_crypto_news = Mock(return_value=[
            {"title": "Test", "content": "Test", "url": "http://test.com"}
        ])
        job.claim_extractor.extract_from_article = Mock(return_value=[Mock(claim_text="Test")])
        job.hypothesis_builder.build_hypotheses = Mock(return_value=[Mock(hypothesis="Test")])
        job.critic.challenge_hypothesis = Mock(return_value=[Mock(challenge="Test")])
        job.reviewer.produce_verdict = Mock(return_value=Mock(
            verdict=VerdictType.REGIME_VALIDATED,
            regime_confidence=0.85,
            confidence_change_from_internal=0.0,
            narrative_consistency=NarrativeConsistency.HIGH,
            reasoning_summary="Test",
            num_sources_analyzed=1,
            num_contradictions=0,
            summary_for_governance="Test"
        ))
        job.persistence.append_verdict = Mock()
        job.safety_validator.validate_verdict = Mock()

        job.run()

        # Verify reviewer was called with regime parameters
        job.reviewer.produce_verdict.assert_called()
        call_kwargs = job.reviewer.produce_verdict.call_args[1]
        assert "current_regime" in call_kwargs


class TestRunPhaseFFunctionIntegration:
    """Test run_phase_f_job convenience function."""

    @patch('phase_f.phase_f_job.PhaseFJob')
    def test_run_phase_f_job_creates_job_and_runs(self, mock_job_class):
        """Test that run_phase_f_job creates and runs a job."""
        mock_job = MagicMock()
        mock_job.run.return_value = True
        mock_job_class.return_value = mock_job

        result = run_phase_f_job(scope="crypto")

        assert result is True
        mock_job_class.assert_called_once_with(scope="crypto")
        mock_job.run.assert_called_once()

    @patch('phase_f.phase_f_job.PhaseFJob')
    def test_run_phase_f_job_returns_false_on_failure(self, mock_job_class):
        """Test that run_phase_f_job returns False if job fails."""
        mock_job = MagicMock()
        mock_job.run.return_value = False
        mock_job_class.return_value = mock_job

        result = run_phase_f_job()

        assert result is False


class TestPersistenceIntegration:
    """Test interaction with persistence layer."""

    @patch('phase_f.phase_f_job.PHASE_F_ENABLED', True)
    @patch('phase_f.phase_f_job.PHASE_F_KILL_SWITCH', False)
    def test_run_persists_verdict(self):
        """Test that verdict is persisted."""
        job = PhaseFJob(scope="crypto")

        job.fetcher.fetch_crypto_news = Mock(return_value=[
            {"title": "Test", "content": "Test", "url": "http://test.com"}
        ])
        job.claim_extractor.extract_from_article = Mock(return_value=[Mock(claim_text="Test")])
        job.hypothesis_builder.build_hypotheses = Mock(return_value=[Mock(hypothesis="Test")])
        job.critic.challenge_hypothesis = Mock(return_value=[Mock(challenge="Test")])

        test_verdict = Mock(
            verdict=VerdictType.REGIME_VALIDATED,
            regime_confidence=0.85,
            confidence_change_from_internal=0.0,
            narrative_consistency=NarrativeConsistency.HIGH,
            reasoning_summary="Test",
            num_sources_analyzed=1,
            num_contradictions=0,
            summary_for_governance="Test"
        )
        job.reviewer.produce_verdict = Mock(return_value=test_verdict)
        job.persistence.append_verdict = Mock()
        job.safety_validator.validate_verdict = Mock()

        job.run()

        job.persistence.append_verdict.assert_called_once()
        call_args = job.persistence.append_verdict.call_args[0]
        assert call_args[0] == test_verdict  # Verdict
        assert isinstance(call_args[1], str)  # run_id
