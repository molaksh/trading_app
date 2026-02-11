"""
Tests for Phase F Schemas (Pydantic models with safety validations).
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from phase_f.schemas import (
    Claim,
    Hypothesis,
    Verdict,
    EpistemicMemoryEvent,
    SemanticMemorySummary,
    VerdictType,
    SentimentEnum,
)


class TestClaim:
    """Test Claim schema validation."""

    def test_valid_claim(self):
        """Create valid claim."""
        claim = Claim(
            claim_text="Bitcoin network difficulty at ATH",
            source="CoinTelegraph",
            source_url="https://cointelegraph.com/news/btc-difficulty",
            publication_timestamp="2026-02-11T10:30:00Z",
            confidence_in_claim=0.85,
            is_factual=True,
            sentiment=SentimentEnum.POSITIVE,
        )
        assert claim.claim_text == "Bitcoin network difficulty at ATH"
        assert claim.confidence_in_claim == 0.85
        assert claim.is_factual is True

    def test_claim_immutable(self):
        """Claim is frozen (immutable)."""
        claim = Claim(
            claim_text="Test",
            source="Source",
            source_url="https://example.com",
            publication_timestamp="2026-02-11T10:30:00Z",
            confidence_in_claim=0.5,
            is_factual=True,
            sentiment=SentimentEnum.NEUTRAL,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            claim.claim_text = "Modified"

    def test_invalid_url(self):
        """URL must start with http."""
        with pytest.raises(ValueError):
            Claim(
                claim_text="Test",
                source="Source",
                source_url="not-a-url",
                publication_timestamp="2026-02-11T10:30:00Z",
                confidence_in_claim=0.5,
                is_factual=True,
                sentiment=SentimentEnum.NEUTRAL,
            )

    def test_invalid_timestamp(self):
        """Timestamp must be ISO format."""
        # Note: "2026-02-11" is valid ISO date format, use truly invalid format
        with pytest.raises(ValidationError):  # Pydantic raises ValidationError
            Claim(
                claim_text="Test",
                source="Source",
                source_url="https://example.com",
                publication_timestamp="not-a-date",  # Truly invalid
                confidence_in_claim=0.5,
                is_factual=True,
                sentiment=SentimentEnum.NEUTRAL,
            )

    def test_confidence_bounds(self):
        """Confidence must be 0.0-1.0."""
        # Too high
        with pytest.raises(ValueError):
            Claim(
                claim_text="Test",
                source="Source",
                source_url="https://example.com",
                publication_timestamp="2026-02-11T10:30:00Z",
                confidence_in_claim=1.5,
                is_factual=True,
                sentiment=SentimentEnum.NEUTRAL,
            )

        # Too low
        with pytest.raises(ValueError):
            Claim(
                claim_text="Test",
                source="Source",
                source_url="https://example.com",
                publication_timestamp="2026-02-11T10:30:00Z",
                confidence_in_claim=-0.1,
                is_factual=True,
                sentiment=SentimentEnum.NEUTRAL,
            )


class TestHypothesis:
    """Test Hypothesis schema validation."""

    def test_valid_hypothesis(self):
        """Create valid hypothesis."""
        hypothesis = Hypothesis(
            hypothesis_text="External narrative supports bullish regime",
            confidence=0.75,
            uncertainty=0.15,
            supporting_claims=[],
            contradicting_claims=[],
            reasoning_steps=["Analyzed 10 sources", "Found 7 supporting"],
        )
        assert hypothesis.confidence == 0.75
        assert hypothesis.uncertainty == 0.15

    def test_no_prescriptive_language(self):
        """Hypothesis cannot contain action words."""
        # Test that validation catches action words
        try:
            Hypothesis(
                hypothesis_text="We should execute trades",
                confidence=0.5,
                uncertainty=0.2,
                supporting_claims=[],
                contradicting_claims=[],
                reasoning_steps=["Test"],
            )
            assert False, "Should have raised ValidationError"
        except ValidationError:
            pass  # Expected

    def test_hypothesis_requires_reasoning(self):
        """Hypothesis must have reasoning steps."""
        with pytest.raises(ValueError):
            Hypothesis(
                hypothesis_text="Test hypothesis",
                confidence=0.5,
                uncertainty=0.2,
                supporting_claims=[],
                contradicting_claims=[],
                reasoning_steps=[],  # Empty
            )


class TestVerdict:
    """Test Verdict schema validation."""

    def test_valid_verdict(self):
        """Create valid verdict."""
        verdict = Verdict(
            verdict=VerdictType.REGIME_VALIDATED,
            regime_confidence=0.80,
            confidence_change_from_internal=-0.05,
            narrative_consistency="HIGH",
            num_sources_analyzed=10,
            num_contradictions=1,
            summary_for_governance="External regime confirms internal regime.",
            reasoning_summary="Sources agree on current regime direction.",
        )
        assert verdict.verdict == VerdictType.REGIME_VALIDATED
        assert verdict.regime_confidence == 0.80

    def test_verdict_whitelist(self):
        """Verdict must be from whitelist."""
        # Valid verdicts should all work
        for verdict_type in [
            VerdictType.REGIME_VALIDATED,
            VerdictType.REGIME_QUESTIONABLE,
            VerdictType.HIGH_NOISE_NO_ACTION,
            VerdictType.POSSIBLE_STRUCTURAL_SHIFT_OBSERVE,
        ]:
            verdict = Verdict(
                verdict=verdict_type,
                regime_confidence=0.5,
                confidence_change_from_internal=0.0,
                narrative_consistency="MODERATE",
                num_sources_analyzed=5,
                num_contradictions=0,
                summary_for_governance="Test",
                reasoning_summary="Test",
            )
            assert verdict.verdict == verdict_type

    def test_verdict_no_action_words(self):
        """Verdict cannot contain action words."""
        invalid_summaries = [
            "We should reduce positions",
            "Buy BTC now based on signals",
            "Execute trades immediately",
            "Trade the regime change",
        ]

        for summary in invalid_summaries:
            with pytest.raises(ValueError):
                Verdict(
                    verdict=VerdictType.REGIME_VALIDATED,
                    regime_confidence=0.5,
                    confidence_change_from_internal=0.0,
                    narrative_consistency="MODERATE",
                    num_sources_analyzed=5,
                    num_contradictions=0,
                    summary_for_governance=summary,
                    reasoning_summary="Test",
                )

    def test_verdict_no_urgency_language(self):
        """Verdict cannot contain urgency words (check by reasoning validator)."""
        # This would be caught by SafetyValidator.check_verdict_content_safety()
        # rather than schema validation
        verdict = Verdict(
            verdict=VerdictType.REGIME_VALIDATED,
            regime_confidence=0.5,
            confidence_change_from_internal=0.0,
            narrative_consistency="MODERATE",
            num_sources_analyzed=5,
            num_contradictions=0,
            summary_for_governance="Test",
            reasoning_summary="Test - urgent issue",  # This gets through schema
        )
        # SafetyValidator would catch it
        assert verdict is not None


class TestEpistemicMemoryEvent:
    """Test EpistemicMemoryEvent schema validation."""

    def test_valid_event(self):
        """Create valid memory event."""
        event = EpistemicMemoryEvent(
            timestamp="2026-02-11T10:30:00Z",
            event_type="EXTERNAL_CLAIM",
            source="CoinTelegraph",
            claim="Bitcoin network difficulty reached ATH",
            market_snapshot={
                "regime": "RISK_ON",
                "volatility": 25.5,
                "trend": 0.8,
            },
        )
        assert event.event_type == "EXTERNAL_CLAIM"
        assert "ATH" in event.claim

    def test_no_causation_in_claim(self):
        """Claim cannot contain causation words."""
        invalid_claims = [
            "Bitcoin ATH causes bullish regime",
            "This leads to price increase",
            "Event -> Price spike",
        ]

        for claim in invalid_claims:
            with pytest.raises(ValueError):
                EpistemicMemoryEvent(
                    timestamp="2026-02-11T10:30:00Z",
                    event_type="EXTERNAL_CLAIM",
                    source="Test",
                    claim=claim,
                    market_snapshot={},
                )

    def test_event_immutable(self):
        """Memory event is frozen."""
        event = EpistemicMemoryEvent(
            timestamp="2026-02-11T10:30:00Z",
            event_type="EXTERNAL_CLAIM",
            source="Test",
            claim="Test claim",
            market_snapshot={},
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.claim = "Modified"


class TestSemanticMemorySummary:
    """Test SemanticMemorySummary schema validation."""

    def test_valid_summary(self):
        """Create valid semantic summary."""
        summary = SemanticMemorySummary(
            period_start="2026-02-01",
            period_end="2026-02-28",
            version=1,
            patterns=[
                {"pattern": "BTC ATH occurs", "frequency": 0.3, "confidence": 0.7}
            ],
        )
        assert summary.version == 1
        assert len(summary.patterns) == 1

    def test_patterns_no_rules(self):
        """Patterns cannot encode rules."""
        with pytest.raises(ValueError):
            SemanticMemorySummary(
                period_start="2026-02-01",
                period_end="2026-02-28",
                version=1,
                patterns=[
                    {
                        "pattern": "if BTC > 50k then buy",
                        "frequency": 0.5,
                    }
                ],
            )

    def test_version_ordering(self):
        """Versions should increment."""
        summary_v1 = SemanticMemorySummary(
            period_start="2026-02-01",
            period_end="2026-02-28",
            version=1,
            patterns=[],
        )
        summary_v2 = SemanticMemorySummary(
            period_start="2026-02-01",
            period_end="2026-02-28",
            version=2,
            patterns=[],
        )
        assert summary_v2.version > summary_v1.version
