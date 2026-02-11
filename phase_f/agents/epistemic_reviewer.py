"""
Epistemic Reviewer agent - compares researcher vs critic and produces verdict.

The Reviewer synthesizes outputs from both Researcher and Critic to produce
conservative, well-reasoned verdicts about regime validity.
"""

import logging
from typing import List, Optional, Tuple
from datetime import datetime

from phase_f.schemas import Hypothesis, Verdict, VerdictType, NarrativeConsistency
from phase_f.agent_identity import REVIEWER_IDENTITY

logger = logging.getLogger(__name__)


class EpistemicReviewer:
    """
    Compare researcher vs critic and produce verdict.

    Synthesizes both analyses into a conservative verdict.
    """

    def __init__(self):
        """Initialize reviewer with identity."""
        self.identity = REVIEWER_IDENTITY

    def produce_verdict(
        self,
        researcher_hypotheses: List[Hypothesis],
        critic_challenges: List[Hypothesis],
        current_regime: str = "UNKNOWN",
        current_regime_confidence: float = 0.5
    ) -> Verdict:
        """
        Produce verdict comparing researcher and critic analyses.

        Args:
            researcher_hypotheses: Hypotheses from researcher
            critic_challenges: Challenges from critic
            current_regime: Current internal regime
            current_regime_confidence: Current regime confidence (0-1)

        Returns:
            Conservative Verdict
        """
        try:
            # Analyze agreement
            agreement_score = self._compute_agreement(
                researcher_hypotheses,
                critic_challenges
            )

            # Determine narrative consistency
            consistency = self._assess_consistency(
                researcher_hypotheses,
                critic_challenges
            )

            # Compute confidence change
            external_confidence = self._estimate_external_confidence(
                researcher_hypotheses
            )
            confidence_change = external_confidence - current_regime_confidence

            # Produce verdict
            verdict_type = self._determine_verdict(
                agreement_score,
                consistency,
                confidence_change,
                len(critic_challenges) > 0
            )

            # Build governance summary
            governance_summary = self._build_governance_summary(
                verdict_type,
                agreement_score,
                consistency,
                confidence_change
            )

            # Build reasoning
            reasoning_summary = self._build_reasoning_summary(
                agreement_score,
                consistency,
                confidence_change,
                len(researcher_hypotheses),
                len(critic_challenges)
            )

            verdict = Verdict(
                verdict=verdict_type,
                regime_confidence=max(0.0, min(1.0, external_confidence)),
                confidence_change_from_internal=confidence_change,
                narrative_consistency=consistency,
                num_sources_analyzed=len(researcher_hypotheses) + len(critic_challenges),
                num_contradictions=len(critic_challenges),
                summary_for_governance=governance_summary,
                reasoning_summary=reasoning_summary,
            )

            logger.info(f"Produced verdict: {verdict_type.value}")
            return verdict

        except Exception as e:
            logger.error(f"Error producing verdict: {e}", exc_info=True)
            # Return conservative default
            return Verdict(
                verdict=VerdictType.HIGH_NOISE_NO_ACTION,
                regime_confidence=0.5,
                confidence_change_from_internal=0.0,
                narrative_consistency=NarrativeConsistency.LOW,
                num_sources_analyzed=0,
                num_contradictions=0,
                summary_for_governance="Analysis error. No action recommended.",
                reasoning_summary="Insufficient data for verdict.",
            )

    def _compute_agreement(
        self,
        researcher_hypotheses: List[Hypothesis],
        critic_challenges: List[Hypothesis]
    ) -> float:
        """
        Compute agreement between researcher and critic.

        Args:
            researcher_hypotheses: Researcher outputs
            critic_challenges: Critic outputs

        Returns:
            Agreement score (0.0-1.0)
        """
        if not researcher_hypotheses or not critic_challenges:
            return 0.5  # Neutral if missing data

        # If critic has many challenges, agreement is lower
        challenge_ratio = len(critic_challenges) / max(len(researcher_hypotheses), 1)

        # If researcher confidence is high and critic confidence low, they disagree
        avg_researcher_confidence = (
            sum(h.confidence for h in researcher_hypotheses) / len(researcher_hypotheses)
            if researcher_hypotheses
            else 0.5
        )
        avg_critic_confidence = (
            sum(h.confidence for h in critic_challenges) / len(critic_challenges)
            if critic_challenges
            else 0.5
        )

        # Agreement = 1 - (confidence gap / 2)
        confidence_gap = abs(avg_researcher_confidence - avg_critic_confidence)
        agreement = max(0.0, 1.0 - (confidence_gap / 2) - (challenge_ratio * 0.3))

        return agreement

    def _assess_consistency(
        self,
        researcher_hypotheses: List[Hypothesis],
        critic_challenges: List[Hypothesis]
    ) -> NarrativeConsistency:
        """
        Assess narrative consistency.

        Args:
            researcher_hypotheses: Researcher outputs
            critic_challenges: Critic outputs

        Returns:
            Narrative consistency assessment
        """
        if not researcher_hypotheses:
            return NarrativeConsistency.LOW

        # Count high-confidence hypotheses
        high_conf = sum(1 for h in researcher_hypotheses if h.confidence > 0.7)
        total = len(researcher_hypotheses)

        # Count serious challenges
        serious_challenges = sum(
            1 for c in critic_challenges if c.confidence > 0.5
        )

        if serious_challenges > total:
            return NarrativeConsistency.LOW
        elif serious_challenges > (total / 2):
            return NarrativeConsistency.MODERATE
        elif high_conf > (total * 0.7):
            return NarrativeConsistency.HIGH
        else:
            return NarrativeConsistency.MODERATE

    def _estimate_external_confidence(
        self,
        researcher_hypotheses: List[Hypothesis]
    ) -> float:
        """
        Estimate external regime confidence.

        Args:
            researcher_hypotheses: Researcher hypotheses

        Returns:
            Confidence score (0.0-1.0)
        """
        if not researcher_hypotheses:
            return 0.5

        # Average confidence, weighted by uncertainty
        total_weight = 0.0
        weighted_sum = 0.0

        for hyp in researcher_hypotheses:
            # Weight by (1 - uncertainty)
            weight = 1.0 - hyp.uncertainty
            weighted_sum += hyp.confidence * weight
            total_weight += weight

        if total_weight == 0:
            return 0.5

        return weighted_sum / total_weight

    def _determine_verdict(
        self,
        agreement_score: float,
        consistency: NarrativeConsistency,
        confidence_change: float,
        has_challenges: bool
    ) -> VerdictType:
        """
        Determine verdict type.

        Args:
            agreement_score: Researcher-critic agreement (0-1)
            consistency: Narrative consistency
            confidence_change: Change from internal regime confidence
            has_challenges: Whether critic found challenges

        Returns:
            Verdict type (conservative)
        """
        # HIGH_NOISE_NO_ACTION: Low agreement or many challenges
        if not has_challenges and agreement_score > 0.75:
            if consistency == NarrativeConsistency.HIGH:
                return VerdictType.REGIME_VALIDATED
            elif consistency == NarrativeConsistency.MODERATE:
                return VerdictType.REGIME_QUESTIONABLE
            else:
                return VerdictType.HIGH_NOISE_NO_ACTION

        # If significant confidence change, might be structural shift
        if abs(confidence_change) > 0.3:
            return VerdictType.POSSIBLE_STRUCTURAL_SHIFT_OBSERVE

        # Default: questionable (conservative default)
        return VerdictType.REGIME_QUESTIONABLE

    def _build_governance_summary(
        self,
        verdict: VerdictType,
        agreement_score: float,
        consistency: NarrativeConsistency,
        confidence_change: float
    ) -> str:
        """
        Build summary for governance (Layer 2 view).

        Args:
            verdict: Verdict type
            agreement_score: Researcher-critic agreement
            consistency: Narrative consistency
            confidence_change: Confidence change

        Returns:
            Governance summary
        """
        if verdict == VerdictType.REGIME_VALIDATED:
            return (
                f"External regime validates internal regime. Consensus: {agreement_score:.0%}. "
                f"Governance can proceed with standard confidence thresholds."
            )
        elif verdict == VerdictType.REGIME_QUESTIONABLE:
            return (
                f"External regime signals mixed. Consensus: {agreement_score:.0%}. "
                f"Recommend +20% confidence penalty on regime-dependent proposals."
            )
        elif verdict == VerdictType.HIGH_NOISE_NO_ACTION:
            return (
                f"High noise in external signals. Recommend deferring "
                f"regime-sensitive governance changes until clarity improves."
            )
        else:  # POSSIBLE_STRUCTURAL_SHIFT
            return (
                f"Possible structural shift detected (Δ confidence: {confidence_change:+.2f}). "
                f"Recommend monitoring regime evolution before major governance adjustments."
            )

    def _build_reasoning_summary(
        self,
        agreement_score: float,
        consistency: NarrativeConsistency,
        confidence_change: float,
        num_hypotheses: int,
        num_challenges: int
    ) -> str:
        """
        Build reasoning summary.

        Args:
            agreement_score: Researcher-critic agreement
            consistency: Narrative consistency
            confidence_change: Confidence change
            num_hypotheses: Number of researcher hypotheses
            num_challenges: Number of critic challenges

        Returns:
            Reasoning summary
        """
        return (
            f"Analyzed {num_hypotheses} external hypotheses with {num_challenges} challenges. "
            f"Researcher-critic agreement: {agreement_score:.0%}. "
            f"Narrative consistency: {consistency.value}. "
            f"Confidence change vs internal: {confidence_change:+.2f}. "
            f"Verdict reflects conservative interpretation of mixed signals."
        )
