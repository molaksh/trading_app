"""
Tests for Phase F Safety Validators (constitutional constraints).
"""

import pytest
from pydantic import ValidationError

from phase_f.safety_checks import SafetyValidator, validate_phase_f_design
from phase_f.schemas import (
    Verdict,
    VerdictType,
    Hypothesis,
    EpistemicMemoryEvent,
    Claim,
    SentimentEnum,
)


class TestVerdictSafety:
    """Test verdict safety validation."""

    def test_valid_verdict_passes(self):
        """Valid verdict passes safety checks."""
        verdict = Verdict(
            verdict=VerdictType.REGIME_VALIDATED,
            regime_confidence=0.80,
            confidence_change_from_internal=0.0,
            narrative_consistency="HIGH",
            num_sources_analyzed=10,
            num_contradictions=0,
            summary_for_governance="External regime confirms internal regime.",
            reasoning_summary="Sources agree on regime direction.",
        )

        assert SafetyValidator.validate_verdict(verdict) is True

    def test_verdict_whitelisted_verdict_type(self):
        """Verdict type must be whitelisted."""
        # This is enforced by Pydantic enum at schema level
        verdict = Verdict(
            verdict=VerdictType.REGIME_VALIDATED,
            regime_confidence=0.5,
            confidence_change_from_internal=0.0,
            narrative_consistency="MODERATE",
            num_sources_analyzed=5,
            num_contradictions=0,
            summary_for_governance="Test",
            reasoning_summary="Test",
        )
        assert SafetyValidator.validate_verdict(verdict) is True

    def test_verdict_no_action_words_in_summary(self):
        """Verdict summary cannot contain action words."""
        invalid_summaries = [
            "We should reduce positions",
            "Execute trades now",
            "Buy BTC immediately",
            "Change the position size",
        ]

        for summary in invalid_summaries:
            with pytest.raises(ValidationError):  # Pydantic raises ValidationError
                verdict = Verdict(
                    verdict=VerdictType.REGIME_VALIDATED,
                    regime_confidence=0.5,
                    confidence_change_from_internal=0.0,
                    narrative_consistency="MODERATE",
                    num_sources_analyzed=5,
                    num_contradictions=0,
                    summary_for_governance=summary,
                    reasoning_summary="Test",
                )

    def test_verdict_confidence_bounds(self):
        """Verdict confidence must be 0.0-1.0."""
        with pytest.raises(ValidationError):  # Pydantic raises ValidationError
            verdict = Verdict(
                verdict=VerdictType.REGIME_VALIDATED,
                regime_confidence=1.5,  # Invalid
                confidence_change_from_internal=0.0,
                narrative_consistency="MODERATE",
                num_sources_analyzed=5,
                num_contradictions=0,
                summary_for_governance="Test",
                reasoning_summary="Test",
            )

    def test_verdict_no_urgency_language(self):
        """Verdict cannot contain urgency words."""
        verdict = Verdict(
            verdict=VerdictType.REGIME_VALIDATED,
            regime_confidence=0.5,
            confidence_change_from_internal=0.0,
            narrative_consistency="MODERATE",
            num_sources_analyzed=5,
            num_contradictions=0,
            summary_for_governance="Test immediately",  # Urgency word
            reasoning_summary="Test",
        )

        # Should pass schema validation but fail safety check
        warnings = SafetyValidator.check_verdict_content_safety(verdict)
        assert len(warnings) > 0
        assert any("immediately" in w.lower() for w in warnings)

    def test_verdict_no_conditional_execution(self):
        """Verdict cannot encode conditional execution."""
        # This will raise ValidationError because "->" is in summary
        with pytest.raises(ValidationError):
            verdict = Verdict(
                verdict=VerdictType.REGIME_VALIDATED,
                regime_confidence=0.5,
                confidence_change_from_internal=0.0,
                narrative_consistency="MODERATE",
                num_sources_analyzed=5,
                num_contradictions=0,
                summary_for_governance="If regime changes -> reduce positions",
                reasoning_summary="Test",
            )


class TestMemoryEventSafety:
    """Test memory event safety validation."""

    def test_valid_event_passes(self):
        """Valid memory event passes checks."""
        event = EpistemicMemoryEvent(
            timestamp="2026-02-11T10:30:00Z",
            event_type="EXTERNAL_CLAIM",
            source="CoinTelegraph",
            claim="Bitcoin network difficulty reached ATH",
            market_snapshot={"regime": "RISK_ON"},
        )

        assert SafetyValidator.validate_memory_event(event) is True

    def test_no_causation_words(self):
        """Memory cannot contain causation words."""
        invalid_claims = [
            "Bitcoin ATH causes bullish regime",
            "This leads to price increase",
            "Event -> Trade execution",
        ]

        for claim in invalid_claims:
            with pytest.raises(ValidationError):  # Pydantic raises ValidationError
                event = EpistemicMemoryEvent(
                    timestamp="2026-02-11T10:30:00Z",
                    event_type="EXTERNAL_CLAIM",
                    source="Test",
                    claim=claim,
                    market_snapshot={},
                )

    def test_no_action_words_in_claim(self):
        """Memory cannot contain action words."""
        invalid_claims = [
            "We should buy BTC",
            "Execute trades on signal",
            "Change position size to 100%",
        ]

        for claim in invalid_claims:
            with pytest.raises(AssertionError):
                event = EpistemicMemoryEvent(
                    timestamp="2026-02-11T10:30:00Z",
                    event_type="EXTERNAL_CLAIM",
                    source="Test",
                    claim=claim,
                    market_snapshot={},
                )
                SafetyValidator.validate_memory_event(event)

    def test_invalid_timestamp(self):
        """Invalid timestamp raises error."""
        # Note: "2026-02-11" is valid ISO date format (date without time)
        # So we need a truly invalid format
        with pytest.raises(ValidationError):
            event = EpistemicMemoryEvent(
                timestamp="not-a-timestamp",  # Truly invalid
                event_type="EXTERNAL_CLAIM",
                source="Test",
                claim="Test claim",
                market_snapshot={},
            )


class TestHypothesisSafety:
    """Test hypothesis safety validation."""

    def test_valid_hypothesis_passes(self):
        """Valid hypothesis passes checks."""
        hypothesis = Hypothesis(
            hypothesis_text="External narrative supports bullish regime",
            confidence=0.75,
            uncertainty=0.15,
            supporting_claims=[],
            contradicting_claims=[],
            reasoning_steps=["Step 1", "Step 2"],
        )

        assert SafetyValidator.validate_hypothesis(hypothesis) is True

    def test_no_action_words_in_hypothesis(self):
        """Hypothesis cannot contain action words."""
        # Test that validation catches action words
        try:
            Hypothesis(
                hypothesis_text="We should buy BTC",
                confidence=0.5,
                uncertainty=0.2,
                supporting_claims=[],
                contradicting_claims=[],
                reasoning_steps=["Test"],
            )
            assert False, "Should have raised ValidationError"
        except ValidationError:
            pass  # Expected

    def test_confidence_bounds(self):
        """Hypothesis confidence must be 0.0-1.0."""
        with pytest.raises(ValidationError):  # Pydantic raises ValidationError
            hypothesis = Hypothesis(
                hypothesis_text="Test hypothesis",
                confidence=1.5,  # Invalid
                uncertainty=0.2,
                supporting_claims=[],
                contradicting_claims=[],
                reasoning_steps=["Test"],
            )

    def test_requires_reasoning_steps(self):
        """Hypothesis must have reasoning steps."""
        with pytest.raises(ValidationError):  # Pydantic raises ValidationError
            hypothesis = Hypothesis(
                hypothesis_text="Test hypothesis",
                confidence=0.5,
                uncertainty=0.2,
                supporting_claims=[],
                contradicting_claims=[],
                reasoning_steps=[],  # Empty
            )


class TestResourceLimits:
    """Test resource limit validation."""

    def test_valid_resources_pass(self):
        """Valid resource usage passes."""
        assert SafetyValidator.validate_resource_limits(
            tokens_used=50000,
            runtime_seconds=300,
            articles_fetched=20,
            sources_analyzed=10,
            max_tokens=100000,
            max_runtime=600,
            max_articles=25,
            max_sources=15,
        ) is True

    def test_token_limit_exceeded(self):
        """Token limit exceeded raises error."""
        with pytest.raises(AssertionError):
            SafetyValidator.validate_resource_limits(
                tokens_used=150000,  # Exceeds limit
                runtime_seconds=300,
                articles_fetched=20,
                sources_analyzed=10,
                max_tokens=100000,
                max_runtime=600,
                max_articles=25,
                max_sources=15,
            )

    def test_runtime_limit_exceeded(self):
        """Runtime limit exceeded raises error."""
        with pytest.raises(AssertionError):
            SafetyValidator.validate_resource_limits(
                tokens_used=50000,
                runtime_seconds=700,  # Exceeds limit
                articles_fetched=20,
                sources_analyzed=10,
                max_tokens=100000,
                max_runtime=600,
                max_articles=25,
                max_sources=15,
            )

    def test_article_limit_exceeded(self):
        """Article limit exceeded raises error."""
        with pytest.raises(AssertionError):
            SafetyValidator.validate_resource_limits(
                tokens_used=50000,
                runtime_seconds=300,
                articles_fetched=30,  # Exceeds limit
                sources_analyzed=10,
                max_tokens=100000,
                max_runtime=600,
                max_articles=25,
                max_sources=15,
            )

    def test_source_limit_exceeded(self):
        """Source limit exceeded raises error."""
        with pytest.raises(AssertionError):
            SafetyValidator.validate_resource_limits(
                tokens_used=50000,
                runtime_seconds=300,
                articles_fetched=20,
                sources_analyzed=20,  # Exceeds limit
                max_tokens=100000,
                max_runtime=600,
                max_articles=25,
                max_sources=15,
            )


class TestDesignValidation:
    """Test overall Phase F design validation."""

    def test_phase_f_design_valid(self):
        """Phase F design validation passes."""
        assert validate_phase_f_design() is True

    def test_verdict_content_safety_checks(self):
        """Test verdict content safety check utility."""
        # Valid verdict
        verdict = Verdict(
            verdict=VerdictType.REGIME_VALIDATED,
            regime_confidence=0.8,
            confidence_change_from_internal=0.0,
            narrative_consistency="HIGH",
            num_sources_analyzed=10,
            num_contradictions=0,
            summary_for_governance="Regime validated",
            reasoning_summary="Sources agree",
        )

        warnings = SafetyValidator.check_verdict_content_safety(verdict)
        assert len(warnings) == 0

    def test_verdict_urgency_warning(self):
        """Urgent verdict triggers warning."""
        verdict = Verdict(
            verdict=VerdictType.REGIME_VALIDATED,
            regime_confidence=0.8,
            confidence_change_from_internal=0.0,
            narrative_consistency="HIGH",
            num_sources_analyzed=10,
            num_contradictions=0,
            summary_for_governance="Regime urgent issue today",
            reasoning_summary="Critical analysis",
        )

        warnings = SafetyValidator.check_verdict_content_safety(verdict)
        assert len(warnings) > 0
        assert any(
            "urgent" in w.lower() or "critical" in w.lower()
            for w in warnings
        )
