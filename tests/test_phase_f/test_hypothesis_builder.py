"""
Tests for hypothesis formation from claims.
"""

import pytest
from phase_f.schemas import Claim, SentimentEnum
from phase_f.hypothesis_builder import HypothesisBuilder


@pytest.fixture
def builder():
    """Create builder instance."""
    return HypothesisBuilder()


@pytest.fixture
def sample_claims():
    """Create sample claims for testing."""
    return [
        Claim(
            claim_text="Bitcoin volatility has increased significantly",
            source="CoinTelegraph",
            source_url="https://cointelegraph.com",
            publication_timestamp="2026-02-11T10:00:00Z",
            confidence_in_claim=0.8,
            is_factual=True,
            sentiment=SentimentEnum.POSITIVE,
        ),
        Claim(
            claim_text="Market sentiment is bullish with strong gains",
            source="CoinDesk",
            source_url="https://coindesk.com",
            publication_timestamp="2026-02-11T10:15:00Z",
            confidence_in_claim=0.75,
            is_factual=True,
            sentiment=SentimentEnum.POSITIVE,
        ),
        Claim(
            claim_text="Some traders express concern about rapid uptrend",
            source="Reuters",
            source_url="https://reuters.com",
            publication_timestamp="2026-02-11T10:30:00Z",
            confidence_in_claim=0.6,
            is_factual=True,
            sentiment=SentimentEnum.NEGATIVE,
        ),
    ]


class TestHypothesisBuilder:
    """Test hypothesis building."""

    def test_build_hypotheses(self, builder, sample_claims):
        """Build hypotheses from claims."""
        hypotheses = builder.build_hypotheses(sample_claims)
        assert len(hypotheses) > 0

        # Each hypothesis should be valid
        for hyp in hypotheses:
            assert hyp.hypothesis_text
            assert 0.0 <= hyp.confidence <= 1.0
            assert 0.0 <= hyp.uncertainty <= 1.0
            assert len(hyp.reasoning_steps) > 0

    def test_hypothesis_has_supporting_claims(self, builder, sample_claims):
        """Hypotheses should reference supporting claims."""
        hypotheses = builder.build_hypotheses(sample_claims)

        for hyp in hypotheses:
            # Should have either supporting or contradicting claims
            assert len(hyp.supporting_claims) + len(hyp.contradicting_claims) > 0

    def test_confidence_calculation(self, builder, sample_claims):
        """Confidence should be based on claim agreement."""
        hypotheses = builder.build_hypotheses(sample_claims)

        # With more positive than negative claims, confidence > 0.5
        if hypotheses:
            for hyp in hypotheses:
                if len(hyp.supporting_claims) > len(hyp.contradicting_claims):
                    assert hyp.confidence >= 0.5

    def test_empty_claims(self, builder):
        """Handle empty claims list."""
        hypotheses = builder.build_hypotheses([])
        assert hypotheses == []

    def test_single_claim(self, builder):
        """Handle single claim."""
        claim = Claim(
            claim_text="Bitcoin is trending upward",
            source="Test",
            source_url="https://test.com",
            publication_timestamp="2026-02-11T10:00:00Z",
            confidence_in_claim=0.8,
            is_factual=True,
            sentiment=SentimentEnum.POSITIVE,
        )
        hypotheses = builder.build_hypotheses([claim])
        assert len(hypotheses) > 0
        assert hypotheses[0].confidence > 0.5

    def test_hypothesis_text_quality(self, builder, sample_claims):
        """Hypothesis text should be descriptive and non-prescriptive."""
        hypotheses = builder.build_hypotheses(sample_claims)

        for hyp in hypotheses:
            # Should not contain action words
            forbidden = [
                "execute", "trade", "buy", "sell", "should", "must",
                "change", "reduce", "increase"
            ]
            hyp_lower = hyp.hypothesis_text.lower()
            for word in forbidden:
                assert word not in hyp_lower, f"Hypothesis contains '{word}'"

    def test_all_hypotheses_have_reasoning(self, builder, sample_claims):
        """All hypotheses must document reasoning."""
        hypotheses = builder.build_hypotheses(sample_claims)

        for hyp in hypotheses:
            assert len(hyp.reasoning_steps) > 0
            # Each step should be informative
            for step in hyp.reasoning_steps:
                assert len(step) > 10  # Non-trivial

    def test_uncertainty_bounds(self, builder):
        """Uncertainty should reflect disagreement."""
        # All positive claims
        positive_claims = [
            Claim(
                claim_text=f"Positive claim {i}",
                source="Test",
                source_url="https://test.com",
                publication_timestamp="2026-02-11T10:00:00Z",
                confidence_in_claim=0.8,
                is_factual=True,
                sentiment=SentimentEnum.POSITIVE,
            )
            for i in range(3)
        ]

        hypotheses = builder.build_hypotheses(positive_claims)
        if hypotheses:
            # Low uncertainty when all claims agree
            assert any(h.uncertainty < 0.3 for h in hypotheses)

        # Mixed claims
        mixed_claims = [
            Claim(
                claim_text="Positive",
                source="Test",
                source_url="https://test.com",
                publication_timestamp="2026-02-11T10:00:00Z",
                confidence_in_claim=0.8,
                is_factual=True,
                sentiment=SentimentEnum.POSITIVE,
            ),
            Claim(
                claim_text="Negative",
                source="Test",
                source_url="https://test.com",
                publication_timestamp="2026-02-11T10:00:00Z",
                confidence_in_claim=0.8,
                is_factual=True,
                sentiment=SentimentEnum.NEGATIVE,
            ),
        ]

        hypotheses = builder.build_hypotheses(mixed_claims)
        if hypotheses:
            # High uncertainty when claims conflict
            assert any(h.uncertainty > 0.3 for h in hypotheses)
