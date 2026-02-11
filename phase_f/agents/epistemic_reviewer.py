"""
Epistemic Reviewer agent - compares researcher vs critic and produces verdict.

The Reviewer synthesizes outputs from both Researcher and Critic to produce
conservative, well-reasoned verdicts about regime validity.

CRITICAL EPISTEMIC FIXES:
- Data sufficiency gates prevent verdicts on insufficient evidence
- Confidence floors protect against noise amplification
- API failures treated as missing data, not negative evidence
- Structural shift classification heavily gated
- Confidence deltas bounded to prevent overreaction
- Source independence tracked to detect overlap bias
"""

import logging
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime

from phase_f.schemas import Hypothesis, Verdict, VerdictType, NarrativeConsistency
from phase_f.agent_identity import REVIEWER_IDENTITY

logger = logging.getLogger(__name__)

# Configuration constants
MINIMUM_SOURCES_FOR_VERDICT = 8
MINIMUM_SOURCE_CATEGORIES = 3
CONFIDENCE_FLOOR = 0.4  # Never drop below 40% on disagreement alone
CONFIDENCE_FLOOR_STRICT = 0.3  # Only with strong contradictory evidence
MAX_NEGATIVE_DELTA = -0.30  # Cap negative confidence change
MAX_POSITIVE_DELTA = 0.20  # Cap positive confidence change
MIN_AGREEMENT_FOR_SHIFT = 0.60  # Need 60% agreement for structural shift
MAX_SOURCE_OVERLAP_RATIO = 0.70  # Flag if > 70% overlap between R & C


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
        current_regime_confidence: float = 0.5,
        market_signals_available: bool = True,
        source_metadata: Optional[Dict[str, Any]] = None
    ) -> Verdict:
        """
        Produce verdict comparing researcher and critic analyses.

        CRITICAL: Data sufficiency is checked BEFORE confidence estimation.
        Verdicts degrade gracefully when data is insufficient.

        Args:
            researcher_hypotheses: Hypotheses from researcher
            critic_challenges: Challenges from critic
            current_regime: Current internal regime
            current_regime_confidence: Current regime confidence (0-1)
            market_signals_available: Whether Kraken API succeeded
            source_metadata: Dict with "categories" list, "num_articles", etc.

        Returns:
            Conservative Verdict (INSUFFICIENT_DATA if data too weak)
        """
        try:
            # STEP 1: Check data sufficiency (MANDATORY GATE)
            sufficiency = self._check_data_sufficiency(
                researcher_hypotheses,
                market_signals_available,
                source_metadata
            )

            if not sufficiency["passed"]:
                logger.warning(
                    f"Data sufficiency failed: {sufficiency['reason']}. "
                    f"Emitting INSUFFICIENT_DATA verdict."
                )
                return self._build_insufficient_data_verdict(
                    sufficiency,
                    current_regime_confidence
                )

            # STEP 2: Check source independence
            independence = self._check_source_independence(
                researcher_hypotheses,
                critic_challenges
            )

            if independence["overlap_ratio"] > MAX_SOURCE_OVERLAP_RATIO:
                logger.warning(
                    f"High source overlap detected ({independence['overlap_ratio']:.0%}). "
                    f"Preventing structural shift classification."
                )

            # STEP 3: Compute agreement score
            agreement_score = self._compute_agreement(
                researcher_hypotheses,
                critic_challenges
            )

            # STEP 4: Assess narrative consistency
            consistency = self._assess_consistency(
                researcher_hypotheses,
                critic_challenges
            )

            # STEP 5: Estimate external confidence (with floor protection)
            external_confidence = self._estimate_external_confidence(
                researcher_hypotheses,
                agreement_score,
                critic_challenges
            )

            # STEP 6: Compute and cap confidence delta
            confidence_change = self._cap_confidence_delta(
                external_confidence - current_regime_confidence,
                market_signals_available
            )

            # STEP 7: Determine verdict type (with structural shift gating)
            verdict_type = self._determine_verdict(
                agreement_score,
                consistency,
                confidence_change,
                len(critic_challenges) > 0,
                market_signals_available,
                independence["overlap_ratio"]
            )

            # STEP 8: Build governance summary
            governance_summary = self._build_governance_summary(
                verdict_type,
                agreement_score,
                consistency,
                confidence_change,
                sufficiency,
                independence
            )

            # STEP 9: Build reasoning
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

            logger.info(f"Produced verdict: {verdict_type.value} (confidence: {external_confidence:.2f})")
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
                summary_for_governance="Analysis error. Unable to assess regime validity.",
                reasoning_summary="Insufficient data for verdict.",
            )

    def _check_data_sufficiency(
        self,
        researcher_hypotheses: List[Hypothesis],
        market_signals_available: bool,
        source_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Check if data is sufficient for a meaningful verdict.

        Requirements:
        - At least 8 total sources analyzed
        - At least 3 distinct source categories
        - Market price signals successfully fetched
        - At least some volatility/price metrics available

        Returns:
            Dict with "passed" (bool), "reason" (str), and details
        """
        issues = []
        total_sources = len(researcher_hypotheses) if researcher_hypotheses else 0

        # Check: Minimum number of sources
        if total_sources < MINIMUM_SOURCES_FOR_VERDICT:
            issues.append(
                f"Only {total_sources} sources analyzed "
                f"(need {MINIMUM_SOURCES_FOR_VERDICT})"
            )

        # Check: Source category diversity
        if source_metadata:
            categories = source_metadata.get("categories", [])
            unique_categories = len(set(categories)) if categories else 0
            if unique_categories < MINIMUM_SOURCE_CATEGORIES:
                issues.append(
                    f"Only {unique_categories} distinct source categories "
                    f"(need {MINIMUM_SOURCE_CATEGORIES})"
                )

        # Check: Market signals availability
        if not market_signals_available:
            issues.append("Market signals (Kraken API) unavailable")

        passed = len(issues) == 0

        return {
            "passed": passed,
            "reason": " | ".join(issues) if issues else "All sufficiency checks passed",
            "num_sources": total_sources,
            "market_signals_available": market_signals_available,
            "source_categories": source_metadata.get("categories", []) if source_metadata else []
        }

    def _check_source_independence(
        self,
        researcher_hypotheses: List[Hypothesis],
        critic_challenges: List[Hypothesis]
    ) -> Dict[str, Any]:
        """
        Check if Researcher and Critic analyzed independent sources.

        High overlap (>70%) indicates they're analyzing the same narratives,
        reducing independence of critical analysis.

        Returns:
            Dict with "overlap_ratio", "researcher_sources", "critic_sources"
        """
        researcher_urls = set()
        critic_urls = set()

        for hyp in researcher_hypotheses:
            for claim in hyp.supporting_claims + hyp.contradicting_claims:
                researcher_urls.add(claim.source_url)

        for hyp in critic_challenges:
            for claim in hyp.supporting_claims + hyp.contradicting_claims:
                critic_urls.add(claim.source_url)

        overlap = researcher_urls & critic_urls
        total = researcher_urls | critic_urls

        overlap_ratio = len(overlap) / len(total) if total else 0.0

        return {
            "overlap_ratio": overlap_ratio,
            "researcher_sources": len(researcher_urls),
            "critic_sources": len(critic_urls),
            "total_unique": len(total),
            "overlap_count": len(overlap)
        }

    def _build_insufficient_data_verdict(
        self,
        sufficiency: Dict[str, Any],
        current_regime_confidence: float
    ) -> Verdict:
        """
        Build INSUFFICIENT_DATA verdict when data gates fail.

        Confidence is capped at -10% delta from internal (no panic).
        """
        return Verdict(
            verdict=VerdictType.INSUFFICIENT_DATA,
            regime_confidence=max(CONFIDENCE_FLOOR, current_regime_confidence - 0.10),
            confidence_change_from_internal=-0.10,  # Capped
            narrative_consistency=NarrativeConsistency.LOW,
            num_sources_analyzed=sufficiency.get("num_sources", 0),
            num_contradictions=0,
            summary_for_governance=(
                f"Insufficient external data for regime assessment. "
                f"Reason: {sufficiency['reason']}. "
                f"Assessment: Defer regime-dependent governance adjustments until clarity improves."
            ),
            reasoning_summary=(
                f"Data insufficiency: {sufficiency['reason']}. "
                f"Verdict remains conservative pending more evidence."
            ),
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
        researcher_hypotheses: List[Hypothesis],
        agreement_score: float,
        critic_challenges: List[Hypothesis]
    ) -> float:
        """
        Estimate external regime confidence WITH FLOOR PROTECTION.

        CRITICAL FIX: Disagreement does not collapse confidence.
        - Disagreement increases uncertainty, not negative evidence
        - Confidence floor (0.4) prevents noise amplification
        - Only strong contradictory evidence can drop below 0.4

        Args:
            researcher_hypotheses: Researcher hypotheses
            agreement_score: Researcher-critic agreement (0-1)
            critic_challenges: Critic challenges

        Returns:
            Confidence score (0.0-1.0) with floor protection
        """
        if not researcher_hypotheses:
            return CONFIDENCE_FLOOR

        # Step 1: Compute base confidence from researcher hypotheses
        total_weight = 0.0
        weighted_sum = 0.0

        for hyp in researcher_hypotheses:
            weight = 1.0 - hyp.uncertainty
            weighted_sum += hyp.confidence * weight
            total_weight += weight

        if total_weight == 0:
            base_confidence = 0.5
        else:
            base_confidence = weighted_sum / total_weight

        # Step 2: Assess if critic has strong contradictory evidence
        has_strong_contradictions = any(
            c.confidence > 0.7 for c in critic_challenges
        )

        # Step 3: Apply confidence floor
        # - If disagreement but no strong contradictions: use floor
        # - If strong contradictions exist: can go below floor
        if agreement_score < 0.5 and not has_strong_contradictions:
            # Disagreement without evidence → protect floor
            external_confidence = max(CONFIDENCE_FLOOR, base_confidence)
        elif has_strong_contradictions and agreement_score < 0.4:
            # Strong contradictions + high disagreement → stricter floor
            external_confidence = max(CONFIDENCE_FLOOR_STRICT, base_confidence)
        else:
            # Normal case: use weighted confidence
            external_confidence = base_confidence

        return max(0.0, min(1.0, external_confidence))

    def _cap_confidence_delta(
        self,
        delta: float,
        market_signals_available: bool
    ) -> float:
        """
        Cap confidence delta to prevent overreaction.

        If market signals unavailable, cap at -15% (no structural shift possible).
        Otherwise cap at ±30% / ±20%.

        Args:
            delta: Raw confidence delta
            market_signals_available: Whether Kraken API succeeded

        Returns:
            Capped delta
        """
        if not market_signals_available:
            # No market data: cap at small negative (treat as missing, not bad)
            return max(-0.15, delta)

        # Normal case: apply standard caps
        return max(MAX_NEGATIVE_DELTA, min(MAX_POSITIVE_DELTA, delta))

    def _determine_verdict(
        self,
        agreement_score: float,
        consistency: NarrativeConsistency,
        confidence_change: float,
        has_challenges: bool,
        market_signals_available: bool,
        source_overlap_ratio: float
    ) -> VerdictType:
        """
        Determine verdict type WITH STRUCTURAL SHIFT GATING.

        CRITICAL GATES:
        1. Structural shift requires: agreement > 60% + market signals + no high overlap
        2. Disagreement alone ≠ structural shift (it's uncertainty)
        3. API failures prevent structural shift classification
        4. High source overlap prevents structural shift

        Args:
            agreement_score: Researcher-critic agreement (0-1)
            consistency: Narrative consistency
            confidence_change: Change from internal regime confidence (capped)
            has_challenges: Whether critic found challenges
            market_signals_available: Whether Kraken API succeeded
            source_overlap_ratio: How much R and C overlap (0-1)

        Returns:
            Verdict type (strongly conservative on structural shift)
        """

        # GATE 1: If market signals unavailable and confidence dropping → HIGH_NOISE
        if not market_signals_available and confidence_change < 0:
            return VerdictType.HIGH_NOISE_NO_ACTION

        # GATE 2: If source overlap too high → prevent structural shift
        if source_overlap_ratio > MAX_SOURCE_OVERLAP_RATIO:
            return VerdictType.HIGH_NOISE_NO_ACTION

        # GATE 3: High agreement, no challenges, high consistency → VALIDATED
        if (not has_challenges and agreement_score > 0.75 and
                consistency == NarrativeConsistency.HIGH):
            return VerdictType.REGIME_VALIDATED

        # GATE 4: High agreement, moderate consistency → QUESTIONABLE (conservative)
        if (not has_challenges and agreement_score > 0.75 and
                consistency == NarrativeConsistency.MODERATE):
            return VerdictType.REGIME_QUESTIONABLE

        # GATE 5: STRUCTURAL SHIFT HARDENING
        # Only emit POSSIBLE_STRUCTURAL_SHIFT if ALL of:
        # - Confidence delta significant (> 0.3 after capping)
        # - Market signals available (have data to validate)
        # - Agreement high enough (> 60%, not just disagreement)
        # - No high source overlap (independent analysis)
        if (abs(confidence_change) > 0.3 and
                market_signals_available and
                agreement_score >= MIN_AGREEMENT_FOR_SHIFT and
                source_overlap_ratio <= MAX_SOURCE_OVERLAP_RATIO):
            return VerdictType.POSSIBLE_STRUCTURAL_SHIFT_OBSERVE

        # GATE 6: Default to QUESTIONABLE (safest choice for uncertainty)
        return VerdictType.REGIME_QUESTIONABLE

    def _build_governance_summary(
        self,
        verdict: VerdictType,
        agreement_score: float,
        consistency: NarrativeConsistency,
        confidence_change: float,
        sufficiency: Optional[Dict[str, Any]] = None,
        independence: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build summary for governance (Layer 2 view).

        Args:
            verdict: Verdict type
            agreement_score: Researcher-critic agreement
            consistency: Narrative consistency
            confidence_change: Confidence change (capped)
            sufficiency: Data sufficiency check results
            independence: Source independence check results

        Returns:
            Governance summary
        """
        if verdict == VerdictType.INSUFFICIENT_DATA:
            reason = sufficiency.get("reason", "unknown") if sufficiency else "unknown"
            return (
                f"Insufficient external data for regime assessment. "
                f"Reason: {reason}. "
                f"Assessment: Defer regime-dependent governance changes."
            )
        elif verdict == VerdictType.REGIME_VALIDATED:
            return (
                f"External regime validates internal regime. Consensus: {agreement_score:.0%}. "
                f"Governance can proceed with standard confidence thresholds."
            )
        elif verdict == VerdictType.REGIME_QUESTIONABLE:
            return (
                f"External regime indicators mixed. Consensus: {agreement_score:.0%}. "
                f"Assessment suggests +20% confidence penalty on regime-dependent proposals may be warranted."
            )
        elif verdict == VerdictType.HIGH_NOISE_NO_ACTION:
            return (
                f"High noise in external indicators. Assessment indicates "
                f"regime-sensitive governance changes should await clarity improvement."
            )
        else:  # POSSIBLE_STRUCTURAL_SHIFT
            return (
                f"Possible structural shift detected (Δ confidence: {confidence_change:+.2f}). "
                f"Assessment suggests monitoring regime evolution before major governance adjustments."
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
            f"Confidence delta vs internal: {confidence_change:+.2f}. "
            f"Verdict reflects conservative interpretation of mixed indicators."
        )
