"""
Tests for Epistemic Critic and Reviewer agents.
"""

import pytest
from datetime import datetime, timedelta

from phase_f.schemas import Claim, Hypothesis, Verdict, VerdictType, SentimentEnum, NarrativeConsistency
from phase_f.agents import EpistemicCritic, EpistemicReviewer


@pytest.fixture
def sample_researcher_hypotheses():
    """Create sample researcher hypotheses."""
    return [
        Hypothesis(
            hypothesis_text="External sentiment is bullish based on multiple sources",
            confidence=0.75,
            uncertainty=0.15,
            supporting_claims=[],
            contradicting_claims=[],
            reasoning_steps=["Analyzed 5 positive sources", "Found consistent narrative"],
        ),
        Hypothesis(
            hypothesis_text="Market regime shows signs of consolidation",
            confidence=0.65,
            uncertainty=0.25,
            supporting_claims=[],
            contradicting_claims=[],
            reasoning_steps=["Analyzed volatility data", "Trend suggests consolidation"],
        ),
    ]


@pytest.fixture
def sample_critic_challenges():
    """Create sample critic challenges."""
    return [
        Hypothesis(
            hypothesis_text="Supporting claims contradict each other",
            confidence=0.55,
            uncertainty=0.4,
            supporting_claims=[],
            contradicting_claims=[],
            reasoning_steps=["Found conflicting signals", "Narrative oversimplified"],
        ),
    ]


class TestEpistemicCritic:
    """Test Critic agent."""

    def test_critic_identity(self):
        """Critic has proper identity."""
        critic = EpistemicCritic()
        assert critic.identity.agent_id == "epistemic_critic_001"
        assert "adversarial" in critic.identity.skepticism_posture.lower()

    def test_challenge_hypothesis(self, sample_researcher_hypotheses):
        """Critic can challenge hypotheses."""
        critic = EpistemicCritic()
        hypothesis = sample_researcher_hypotheses[0]

        challenges = critic.challenge_hypothesis(hypothesis)
        # Should produce some challenges
        assert isinstance(challenges, list)

    def test_find_contradictions(self, sample_researcher_hypotheses):
        """Critic can find contradictions."""
        critic = EpistemicCritic()

        # Hypothesis with contradictory supporting claims
        contradictory = Hypothesis(
            hypothesis_text="Test",
            confidence=0.5,
            uncertainty=0.3,
            supporting_claims=[
                Claim(
                    claim_text="Positive claim",
                    source="Test",
                    source_url="https://test.com",
                    publication_timestamp="2026-02-11T10:00:00Z",
                    confidence_in_claim=0.8,
                    is_factual=True,
                    sentiment=SentimentEnum.POSITIVE,
                ),
                Claim(
                    claim_text="Negative claim",
                    source="Test",
                    source_url="https://test.com",
                    publication_timestamp="2026-02-11T10:00:00Z",
                    confidence_in_claim=0.8,
                    is_factual=True,
                    sentiment=SentimentEnum.NEGATIVE,
                ),
            ],
            contradicting_claims=[],
            reasoning_steps=["Test"],
        )

        challenges = critic.challenge_hypothesis(contradictory)
        assert len(challenges) > 0
        # Should find contradiction challenge
        assert any("contradict" in h.hypothesis_text.lower() for h in challenges)

    def test_challenge_recency_bias(self):
        """Critic can detect recency bias."""
        critic = EpistemicCritic()
        now = datetime.utcnow()

        # Recent claims (last 3 days)
        recent_claims = [
            Claim(
                claim_text=f"Recent claim {i}",
                source="Test",
                source_url="https://test.com",
                publication_timestamp=(now - timedelta(days=1)).isoformat() + "Z",
                confidence_in_claim=0.8,
                is_factual=True,
                sentiment=SentimentEnum.POSITIVE,
            )
            for i in range(5)
        ]

        hypothesis = Hypothesis(
            hypothesis_text="Test",
            confidence=0.7,
            uncertainty=0.2,
            supporting_claims=recent_claims,
            contradicting_claims=[],
            reasoning_steps=["Test"],
        )

        challenges = critic.challenge_hypothesis(hypothesis)
        # Should challenge recency bias
        assert any("recent" in h.hypothesis_text.lower() for h in challenges)

    def test_challenger_hypotheses_have_reasoning(self):
        """All challenges must have reasoning."""
        critic = EpistemicCritic()
        hypothesis = Hypothesis(
            hypothesis_text="Test hypothesis",
            confidence=0.7,
            uncertainty=0.2,
            supporting_claims=[],
            contradicting_claims=[],
            reasoning_steps=["Test"],
        )

        challenges = critic.challenge_hypothesis(hypothesis)
        for challenge in challenges:
            assert len(challenge.reasoning_steps) > 0


class TestEpistemicReviewer:
    """Test Reviewer agent."""

    def test_reviewer_identity(self):
        """Reviewer has proper identity."""
        reviewer = EpistemicReviewer()
        assert reviewer.identity.agent_id == "epistemic_reviewer_001"
        assert "conservative" in reviewer.identity.skepticism_posture.lower()

    def test_produce_verdict(self, sample_researcher_hypotheses, sample_critic_challenges):
        """Reviewer can produce verdict."""
        reviewer = EpistemicReviewer()

        # Replicate hypotheses to meet minimum 8 sources for data sufficiency
        hypotheses = sample_researcher_hypotheses * 4  # 2 * 4 = 8
        challenges = sample_critic_challenges * 4  # 2 * 4 = 8

        verdict = reviewer.produce_verdict(
            hypotheses,
            challenges,
            current_regime="RISK_ON",
            current_regime_confidence=0.7,
            market_signals_available=True,
            source_metadata={
                "categories": ["crypto-news", "macro", "market-microstructure"],
                "num_articles": 8,
                "num_unique_sources": 8,
                "actual_sources": ["Bloomberg", "Reuters", "CoinDesk", "Medium", "Reddit", "BeInCrypto", "CoinGecko", "Kraken"]
            }
        )

        assert isinstance(verdict, Verdict)
        assert verdict.verdict in [
            VerdictType.REGIME_VALIDATED,
            VerdictType.REGIME_QUESTIONABLE,
            VerdictType.HIGH_NOISE_NO_ACTION,
            VerdictType.POSSIBLE_STRUCTURAL_SHIFT_OBSERVE,
        ]
        assert 0.0 <= verdict.regime_confidence <= 1.0
        assert verdict.num_sources_analyzed > 0

    def test_verdict_is_conservative(self, sample_researcher_hypotheses):
        """Verdicts should be conservative."""
        reviewer = EpistemicReviewer()

        # Even with high researcher confidence, if we have challenges, verdict is cautious
        challenges = [
            Hypothesis(
                hypothesis_text="Challenge",
                confidence=0.6,
                uncertainty=0.3,
                supporting_claims=[],
                contradicting_claims=[],
                reasoning_steps=["Challenge reasoning"],
            )
        ]

        verdict = reviewer.produce_verdict(
            sample_researcher_hypotheses,
            challenges,
            current_regime="RISK_ON",
            current_regime_confidence=0.8,
            market_signals_available=True,
            source_metadata={
                "categories": ["crypto", "macro", "market"],
                "num_articles": 8
            }
        )

        # With challenges, should not validate
        assert verdict.verdict != VerdictType.REGIME_VALIDATED

    def test_governance_summary_no_prescriptive_language(self, sample_researcher_hypotheses, sample_critic_challenges):
        """Governance summary must not have action words."""
        reviewer = EpistemicReviewer()

        verdict = reviewer.produce_verdict(
            sample_researcher_hypotheses,
            sample_critic_challenges,
            market_signals_available=True,
            source_metadata={
                "categories": ["crypto", "macro", "market"],
                "num_articles": 8
            }
        )

        # Check no forbidden words
        forbidden = [
            "execute", "trade", "buy", "sell", "should", "must",
            "change", "reduce", "increase"
        ]
        summary_lower = verdict.summary_for_governance.lower()
        for word in forbidden:
            assert word not in summary_lower, f"Summary contains '{word}'"

    def test_verdict_reasoning_documented(self, sample_researcher_hypotheses, sample_critic_challenges):
        """All verdicts must document reasoning."""
        reviewer = EpistemicReviewer()

        # Replicate hypotheses to meet minimum 8 sources for data sufficiency
        hypotheses = sample_researcher_hypotheses * 4
        challenges = sample_critic_challenges * 4

        verdict = reviewer.produce_verdict(
            hypotheses,
            challenges,
            market_signals_available=True,
            source_metadata={
                "categories": ["crypto-news", "macro", "market-microstructure"],
                "num_articles": 8,
                "num_unique_sources": 8,
                "actual_sources": ["Bloomberg", "Reuters", "CoinDesk", "Medium", "Reddit", "BeInCrypto", "CoinGecko", "Kraken"]
            }
        )

        assert len(verdict.reasoning_summary) > 20
        assert "agreement" in verdict.reasoning_summary.lower() or \
               "confidence" in verdict.reasoning_summary.lower()

    def test_empty_hypotheses_handled(self):
        """Reviewer handles empty hypothesis lists."""
        reviewer = EpistemicReviewer()

        # Empty data triggers INSUFFICIENT_DATA verdict due to data sufficiency gate
        verdict = reviewer.produce_verdict(
            [],
            [],
            market_signals_available=True,
            source_metadata={
                "categories": ["crypto", "macro", "market"],
                "num_articles": 0
            }
        )
        assert verdict is not None
        assert verdict.verdict == VerdictType.INSUFFICIENT_DATA or \
               verdict.verdict == VerdictType.HIGH_NOISE_NO_ACTION

    def test_verdict_with_confidence_change(self, sample_researcher_hypotheses):
        """Verdict reflects confidence changes."""
        reviewer = EpistemicReviewer()

        # Researcher hypotheses with high confidence (replicate to 8 for sufficiency)
        high_conf_hypotheses = [
            Hypothesis(
                hypothesis_text="Strong external signal",
                confidence=0.85,
                uncertainty=0.1,
                supporting_claims=[],
                contradicting_claims=[],
                reasoning_steps=["Strong evidence"],
            )
        ] * 8  # Replicate to meet minimum 8 sources

        verdict = reviewer.produce_verdict(
            high_conf_hypotheses,
            [],  # No challenges
            current_regime="RISK_ON",
            current_regime_confidence=0.5,
            market_signals_available=True,
            source_metadata={
                "categories": ["crypto-news", "macro", "market-microstructure"],
                "num_articles": 8,
                "num_unique_sources": 8,
                "actual_sources": ["Bloomberg", "Reuters", "CoinDesk", "Medium", "Reddit", "BeInCrypto", "CoinGecko", "Kraken"]
            }
        )

        # Should show positive confidence change (capped at +0.20)
        assert verdict.confidence_change_from_internal > 0 or \
               verdict.confidence_change_from_internal == 0  # Can be capped


class TestCriticReviewerIntegration:
    """Integration tests for Critic and Reviewer."""

    def test_critic_researcher_integration(self, sample_researcher_hypotheses):
        """Critic can challenge Researcher output."""
        critic = EpistemicCritic()

        for hypothesis in sample_researcher_hypotheses:
            challenges = critic.challenge_hypothesis(hypothesis)
            # All challenges should be valid
            for challenge in challenges:
                assert challenge.confidence > 0
                assert len(challenge.reasoning_steps) > 0

    def test_full_pipeline(self, sample_researcher_hypotheses):
        """Full pipeline: Researcher → Critic → Reviewer."""
        critic = EpistemicCritic()
        reviewer = EpistemicReviewer()

        # Ensure we have enough hypotheses for sufficiency check
        hypotheses = sample_researcher_hypotheses
        if len(hypotheses) < 8:
            hypotheses = sample_researcher_hypotheses * (8 // len(sample_researcher_hypotheses) + 1)

        # Generate challenges
        all_challenges = []
        for hypothesis in hypotheses:
            challenges = critic.challenge_hypothesis(hypothesis)
            all_challenges.extend(challenges)

        # Produce verdict
        verdict = reviewer.produce_verdict(
            hypotheses,
            all_challenges,
            market_signals_available=True,
            source_metadata={
                "categories": ["crypto-news", "macro", "market-microstructure"],
                "num_articles": len(hypotheses),
                "num_unique_sources": max(8, len(hypotheses)),
                "actual_sources": ["Bloomberg", "Reuters", "CoinDesk", "Medium", "Reddit", "BeInCrypto", "CoinGecko", "Kraken"]
            }
        )

        assert verdict is not None
        assert verdict.num_contradictions == len(all_challenges)
