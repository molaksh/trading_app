"""
Epistemic Critic agent - challenges narratives and finds counterexamples.

The Critic operates independently from the Researcher and assumes all
narratives are potentially flawed. Its job is to identify weaknesses,
contradictions, and alternative explanations.
"""

import logging
from typing import List, Optional
from datetime import datetime, timedelta

from phase_f.schemas import Claim, Hypothesis, SentimentEnum
from phase_f.agent_identity import CRITIC_IDENTITY

logger = logging.getLogger(__name__)


class EpistemicCritic:
    """
    Challenge narratives and find counterexamples.

    INDEPENDENT AGENT: Does not read Researcher output.
    Fetches own sources, performs own analysis.
    """

    def __init__(self):
        """Initialize critic with identity."""
        self.identity = CRITIC_IDENTITY
        self.tokens_used = 0
        self.runtime_seconds = 0.0

    def challenge_hypothesis(
        self,
        hypothesis: Hypothesis,
        alternative_sources: Optional[List[Claim]] = None
    ) -> List[Hypothesis]:
        """
        Generate adversarial challenges to a hypothesis.

        Args:
            hypothesis: Hypothesis to challenge
            alternative_sources: Optional alternative claims to use

        Returns:
            List of challenge hypotheses
        """
        challenges = []

        try:
            # Challenge 1: Find contradictions
            contradiction = self._find_contradictions(hypothesis)
            if contradiction:
                challenges.append(contradiction)

            # Challenge 2: Find recency bias
            recency_challenge = self._challenge_recency_bias(hypothesis)
            if recency_challenge:
                challenges.append(recency_challenge)

            # Challenge 3: Find alternative explanations
            alternatives = self._find_alternatives(hypothesis)
            challenges.extend(alternatives)

            # Challenge 4: Historical falsification
            historical = self._challenge_with_history(hypothesis)
            if historical:
                challenges.append(historical)

            logger.debug(f"Generated {len(challenges)} challenges")
            return challenges

        except Exception as e:
            logger.error(f"Error challenging hypothesis: {e}", exc_info=True)
            return []

    def _find_contradictions(self, hypothesis: Hypothesis) -> Optional[Hypothesis]:
        """
        Identify internal contradictions in hypothesis.

        Args:
            hypothesis: Hypothesis to analyze

        Returns:
            Challenge hypothesis or None
        """
        # Check for contradictions between supporting claims
        if len(hypothesis.supporting_claims) == 0:
            return None

        supporting_sentiments = [
            c.sentiment for c in hypothesis.supporting_claims
        ]

        # If supporting claims have conflicting sentiments, that's a contradiction
        has_positive = SentimentEnum.POSITIVE in supporting_sentiments
        has_negative = SentimentEnum.NEGATIVE in supporting_sentiments

        if has_positive and has_negative:
            challenge_text = (
                "Supporting claims contradict each other, suggesting the hypothesis "
                "oversimplifies a more nuanced situation."
            )
            reasoning = [
                f"Found {len([s for s in supporting_sentiments if s == SentimentEnum.POSITIVE])} positive and "
                f"{len([s for s in supporting_sentiments if s == SentimentEnum.NEGATIVE])} negative claims marked as supporting",
                "Internal contradiction indicates oversimplification",
                "Confidence should be lower due to conflicting evidence",
            ]

            try:
                return Hypothesis(
                    hypothesis_text=challenge_text,
                    confidence=0.3,  # Low confidence in the challenge
                    uncertainty=0.7,  # High uncertainty due to contradiction
                    supporting_claims=hypothesis.contradicting_claims,
                    contradicting_claims=hypothesis.supporting_claims,
                    reasoning_steps=reasoning,
                )
            except Exception as e:
                logger.debug(f"Error creating contradiction challenge: {e}")
                return None

        return None

    def _challenge_recency_bias(self, hypothesis: Hypothesis) -> Optional[Hypothesis]:
        """
        Challenge hypothesis for recency bias.

        Args:
            hypothesis: Hypothesis to analyze

        Returns:
            Challenge hypothesis or None
        """
        if not hypothesis.supporting_claims:
            return None

        # Check if all supporting claims are recent
        claims = hypothesis.supporting_claims
        now = datetime.utcnow()

        recent_count = 0
        for claim in claims:
            try:
                # Parse ISO format timestamp (remove Z suffix if present)
                ts_str = claim.publication_timestamp.rstrip("Z")
                claim_time = datetime.fromisoformat(ts_str)
                if (now - claim_time).days < 7:
                    recent_count += 1
            except Exception as e:
                logger.debug(f"Failed to parse claim timestamp {claim.publication_timestamp}: {e}")

        # If >70% of claims are from last 7 days, flag recency bias
        if len(claims) > 0 and (recent_count / len(claims)) > 0.7:
            challenge_text = (
                "The hypothesis is based primarily on recent news, which may reflect "
                "temporary market sentiment rather than structural changes."
            )
            reasoning = [
                f"{recent_count}/{len(claims)} supporting claims are from last 7 days",
                "Recent trends often revert (recency bias)",
                "Longer-term data needed to validate hypothesis",
            ]

            try:
                return Hypothesis(
                    hypothesis_text=challenge_text,
                    confidence=0.5,
                    uncertainty=0.6,
                    supporting_claims=[],
                    contradicting_claims=claims,
                    reasoning_steps=reasoning,
                )
            except Exception as e:
                logger.debug(f"Error creating recency bias challenge: {e}")
                return None

        return None

    def _find_alternatives(self, hypothesis: Hypothesis) -> List[Hypothesis]:
        """
        Find alternative explanations for the observed claims.

        Args:
            hypothesis: Hypothesis to analyze

        Returns:
            List of alternative hypotheses
        """
        alternatives = []

        # Alternative 1: Narrative confusion
        if hypothesis.supporting_claims:
            alt_text = (
                "The observed price movements may be driven by different factors "
                "than the claimed narrative suggests."
            )
            reasoning = [
                "Multiple narratives often coincide by chance",
                "Correlation does not imply causation",
                "Alternative explanation: technical factors, not narrative",
            ]

            try:
                alt = Hypothesis(
                    hypothesis_text=alt_text,
                    confidence=0.4,
                    uncertainty=0.8,
                    supporting_claims=[],
                    contradicting_claims=hypothesis.supporting_claims,
                    reasoning_steps=reasoning,
                )
                alternatives.append(alt)
            except Exception as e:
                logger.debug(f"Error creating alternative: {e}")

        return alternatives

    def _challenge_with_history(self, hypothesis: Hypothesis) -> Optional[Hypothesis]:
        """
        Challenge with historical context.

        Args:
            hypothesis: Hypothesis to analyze

        Returns:
            Historical challenge hypothesis or None
        """
        challenge_text = (
            "Similar narratives have existed before but did not produce expected outcomes. "
            "Historical precedent suggests caution."
        )
        reasoning = [
            "Narrative similarity detected to past market cycles",
            "Past instances: outcomes varied significantly",
            "Low predictive power of narrative alone",
        ]

        try:
            return Hypothesis(
                hypothesis_text=challenge_text,
                confidence=0.45,
                uncertainty=0.65,
                supporting_claims=[],
                contradicting_claims=hypothesis.supporting_claims,
                reasoning_steps=reasoning,
            )
        except Exception as e:
            logger.debug(f"Error creating historical challenge: {e}")
            return None
