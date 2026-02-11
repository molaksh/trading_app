"""
Hypothesis formation from extracted claims.

Groups claims by theme and forms probabilistic hypotheses.
"""

import logging
from typing import List, Dict
from phase_f.schemas import Claim, Hypothesis, SentimentEnum

logger = logging.getLogger(__name__)


class HypothesisBuilder:
    """Form probabilistic hypotheses from claims."""

    def __init__(self):
        """Initialize builder with theme mappings."""
        self.theme_keywords = {
            "volatility": ["volatility", "vol", "std dev", "variance", "swing"],
            "trend": ["trend", "uptrend", "downtrend", "rally", "crash", "momentum"],
            "liquidity": ["liquidity", "volume", "bid-ask", "depth", "slippage"],
            "regulation": ["regulation", "sec", "regulatory", "legal", "compliance"],
            "sentiment": ["sentiment", "fear", "greed", "bullish", "bearish", "confidence"],
            "technology": ["technology", "upgrade", "protocol", "blockchain", "network"],
        }

    def build_hypotheses(self, claims: List[Claim]) -> List[Hypothesis]:
        """
        Build hypotheses from claims.

        Args:
            claims: List of extracted claims

        Returns:
            List of Hypothesis objects
        """
        if not claims:
            return []

        hypotheses = []

        try:
            # Group claims by theme
            themed_claims = self._group_by_theme(claims)

            # Build hypothesis for each theme
            for theme, group_claims in themed_claims.items():
                if group_claims:
                    hypothesis = self._build_hypothesis_for_theme(theme, group_claims)
                    if hypothesis:
                        hypotheses.append(hypothesis)

            logger.info(f"Built {len(hypotheses)} hypotheses from {len(claims)} claims")
            return hypotheses

        except Exception as e:
            logger.error(f"Error building hypotheses: {e}", exc_info=True)
            return []

    def _group_by_theme(self, claims: List[Claim]) -> Dict[str, List[Claim]]:
        """
        Group claims by theme.

        Args:
            claims: List of claims

        Returns:
            Dict mapping theme to claims
        """
        themed = {theme: [] for theme in self.theme_keywords.keys()}

        for claim in claims:
            text_lower = claim.claim_text.lower()

            # Find matching theme
            for theme, keywords in self.theme_keywords.items():
                if any(kw in text_lower for kw in keywords):
                    themed[theme].append(claim)
                    break

            # Add to "general" if no theme matched
            if not any(claim in v for v in themed.values()):
                themed["sentiment"].append(claim)  # Default theme

        # Remove empty themes
        return {k: v for k, v in themed.items() if v}

    def _build_hypothesis_for_theme(self, theme: str, claims: List[Claim]) -> Hypothesis:
        """
        Build hypothesis for a specific theme.

        Args:
            theme: Theme name
            claims: Claims for this theme

        Returns:
            Hypothesis object
        """
        # Separate by sentiment
        supporting = [c for c in claims if c.sentiment == SentimentEnum.POSITIVE]
        contradicting = [c for c in claims if c.sentiment == SentimentEnum.NEGATIVE]
        neutral = [c for c in claims if c.sentiment == SentimentEnum.NEUTRAL]

        # Calculate confidence
        total = len(claims)
        if total == 0:
            return None

        # Confidence: (supporting - contradicting) / total
        confidence = max(0.0, min(1.0, (len(supporting) - len(contradicting)) / total + 0.5))

        # Uncertainty: how much disagreement
        uncertainty = len(contradicting) / total if total > 0 else 0.0

        # Build hypothesis text
        hypothesis_text = self._build_hypothesis_text(theme, supporting, contradicting)

        # Reasoning steps
        reasoning_steps = [
            f"Analyzed {len(claims)} claims about {theme}",
            f"Found {len(supporting)} supporting, {len(contradicting)} contradicting",
            f"Confidence: {confidence:.2f} (supports {theme})",
        ]

        try:
            return Hypothesis(
                hypothesis_text=hypothesis_text,
                confidence=confidence,
                uncertainty=uncertainty,
                supporting_claims=supporting,
                contradicting_claims=contradicting,
                reasoning_steps=reasoning_steps,
            )
        except Exception as e:
            logger.error(f"Error creating hypothesis: {e}")
            return None

    def _build_hypothesis_text(
        self,
        theme: str,
        supporting: List[Claim],
        contradicting: List[Claim]
    ) -> str:
        """
        Build descriptive hypothesis text.

        Args:
            theme: Theme name
            supporting: Supporting claims
            contradicting: Contradicting claims

        Returns:
            Hypothesis text
        """
        if len(supporting) > len(contradicting):
            return f"External sources suggest {theme} is elevated and noteworthy. Multiple sources confirm this narrative."
        elif len(contradicting) > len(supporting):
            return f"External sources show mixed signals on {theme}. Some contradict the dominant narrative."
        else:
            return f"External sources present conflicting views on {theme}. Narrative is uncertain."
