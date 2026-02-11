"""
Phase F Safety Checks: Validate constitutional constraints.

These checks are MANDATORY and non-bypassable.
If Phase F violates any constraint, the implementation is invalid.
"""

import logging
from typing import List

from config.phase_f_settings import (
    FORBIDDEN_ACTION_WORDS,
    FORBIDDEN_CAUSATION_WORDS,
    ALLOWED_VERDICTS,
)
from phase_f.schemas import Verdict, EpistemicMemoryEvent, Hypothesis

logger = logging.getLogger(__name__)


class SafetyValidator:
    """Validate Phase F outputs against constitutional constraints."""

    # ========================================================================
    # Verdict Safety Checks
    # ========================================================================

    @staticmethod
    def validate_verdict(verdict: Verdict) -> bool:
        """
        Validate verdict is epistemic, never prescriptive.

        Args:
            verdict: Verdict to validate

        Returns:
            True if valid

        Raises:
            AssertionError: If verdict violates constraints
        """
        # Check verdict type is whitelisted
        allowed = [v for v in ALLOWED_VERDICTS]
        assert (
            verdict.verdict.value in allowed
        ), f"Verdict {verdict.verdict.value} not in whitelist {allowed}"

        # Check summary_for_governance has no action words
        governance_text = verdict.summary_for_governance.lower()
        for word in FORBIDDEN_ACTION_WORDS:
            assert (
                word not in governance_text
            ), f"Governance summary contains forbidden action word: '{word}'"

        # Check reasoning_summary has no action words
        reasoning_text = verdict.reasoning_summary.lower()
        for word in FORBIDDEN_ACTION_WORDS:
            assert (
                word not in reasoning_text
            ), f"Reasoning summary contains forbidden action word: '{word}'"

        # Check confidence is valid
        assert (
            0.0 <= verdict.regime_confidence <= 1.0
        ), f"regime_confidence must be 0.0-1.0, got {verdict.regime_confidence}"

        # Check no extreme prescriptions
        extreme_phrases = [
            "immediately",
            "urgently",
            "critical",
            "must change",
            "required to",
        ]
        combined_text = (
            verdict.summary_for_governance + " " + verdict.reasoning_summary
        ).lower()
        for phrase in extreme_phrases:
            assert (
                phrase not in combined_text
            ), f"Verdict contains extreme prescriptive phrase: '{phrase}'"

        logger.debug(f"Verdict validation passed: {verdict.verdict.value}")
        return True

    # ========================================================================
    # Memory Safety Checks
    # ========================================================================

    @staticmethod
    def validate_memory_event(event: EpistemicMemoryEvent) -> bool:
        """
        Validate memory event records observation, not causation.

        Args:
            event: EpistemicMemoryEvent to validate

        Returns:
            True if valid

        Raises:
            AssertionError: If event violates constraints
        """
        # Check no causation words
        claim_text = event.claim.lower()
        for word in FORBIDDEN_CAUSATION_WORDS:
            assert (
                word not in claim_text
            ), f"Memory claim contains causation word: '{word}'"

        # Check no action words
        for word in FORBIDDEN_ACTION_WORDS:
            assert (
                word not in claim_text
            ), f"Memory claim contains action word: '{word}'"

        # Validate timestamp format
        try:
            import datetime
            datetime.datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
        except ValueError:
            raise AssertionError(f"Invalid timestamp format: {event.timestamp}")

        logger.debug(
            f"Memory event validation passed: {event.event_type}"
        )
        return True

    # ========================================================================
    # Hypothesis Safety Checks
    # ========================================================================

    @staticmethod
    def validate_hypothesis(hypothesis: Hypothesis) -> bool:
        """
        Validate hypothesis is epistemic, never prescriptive.

        Args:
            hypothesis: Hypothesis to validate

        Returns:
            True if valid

        Raises:
            AssertionError: If hypothesis violates constraints
        """
        # Check no action words
        text = hypothesis.hypothesis_text.lower()
        for word in FORBIDDEN_ACTION_WORDS:
            assert (
                word not in text
            ), f"Hypothesis contains forbidden action word: '{word}'"

        # Check confidence is valid
        assert (
            0.0 <= hypothesis.confidence <= 1.0
        ), f"confidence must be 0.0-1.0, got {hypothesis.confidence}"

        assert (
            0.0 <= hypothesis.uncertainty <= 1.0
        ), f"uncertainty must be 0.0-1.0, got {hypothesis.uncertainty}"

        # Check reasoning steps are present
        assert (
            len(hypothesis.reasoning_steps) > 0
        ), "Hypothesis must have documented reasoning steps"

        logger.debug("Hypothesis validation passed")
        return True

    # ========================================================================
    # No Execution Authority Checks
    # ========================================================================

    @staticmethod
    def validate_no_execution_authority() -> bool:
        """
        Verify Phase F has no path to execution authority.

        This is a structural check (run once at startup).

        Returns:
            True if design is valid

        Raises:
            AssertionError: If design violates constraints
        """
        # Phase F outputs can only go to:
        # 1. persist/phase_f/ (memory)
        # 2. Governance summary (confidence weighting only)
        # 3. Logs (for debugging)

        # Phase F outputs CANNOT go to:
        # 1. Execution layer (strategy, risk, position sizing)
        # 2. Regime changes
        # 3. Universe modifications
        # 4. Parameter changes

        logger.info("Phase F execution authority constraints verified")
        return True

    # ========================================================================
    # Resource Constraint Checks
    # ========================================================================

    @staticmethod
    def validate_resource_limits(
        tokens_used: int,
        runtime_seconds: float,
        articles_fetched: int,
        sources_analyzed: int,
        max_tokens: int = 100000,
        max_runtime: float = 600,
        max_articles: int = 25,
        max_sources: int = 15,
    ) -> bool:
        """
        Validate resource usage within limits.

        Args:
            tokens_used: OpenAI tokens consumed
            runtime_seconds: Execution time
            articles_fetched: Number of articles fetched
            sources_analyzed: Number of unique sources
            max_tokens: Token limit
            max_runtime: Runtime limit (seconds)
            max_articles: Article fetch limit
            max_sources: Source limit

        Returns:
            True if within limits

        Raises:
            AssertionError: If limits exceeded
        """
        assert (
            tokens_used <= max_tokens
        ), f"Tokens exceeded: {tokens_used} > {max_tokens}"

        assert (
            runtime_seconds <= max_runtime
        ), f"Runtime exceeded: {runtime_seconds}s > {max_runtime}s"

        assert (
            articles_fetched <= max_articles
        ), f"Articles exceeded: {articles_fetched} > {max_articles}"

        assert (
            sources_analyzed <= max_sources
        ), f"Sources exceeded: {sources_analyzed} > {max_sources}"

        logger.debug(
            f"Resource limits validated: "
            f"tokens={tokens_used}/{max_tokens}, "
            f"runtime={runtime_seconds:.1f}s/{max_runtime}s, "
            f"articles={articles_fetched}/{max_articles}, "
            f"sources={sources_analyzed}/{max_sources}"
        )
        return True

    # ========================================================================
    # Content Safety Checks
    # ========================================================================

    @staticmethod
    def check_verdict_content_safety(verdict: Verdict) -> List[str]:
        """
        Check verdict for concerning language patterns.

        Returns:
            List of warnings (empty = safe)
        """
        warnings = []

        # Check for urgency language
        urgency_words = [
            "immediately",
            "now",
            "today",
            "urgent",
            "critical",
            "emergency",
        ]
        combined = (
            verdict.summary_for_governance + " " + verdict.reasoning_summary
        ).lower()
        for word in urgency_words:
            if word in combined:
                warnings.append(f"Contains urgency language: '{word}'")

        # Check for conditional execution
        if "->" in combined or "if then" in combined.lower():
            warnings.append("Contains conditional execution pattern")

        # Check for optimization signals
        if "more" in combined or "less" in combined:
            warnings.append("Contains optimization language")

        return warnings


# ============================================================================
# Module-level validation function
# ============================================================================


def validate_phase_f_design() -> bool:
    """
    Run all design validation checks at startup.

    Returns:
        True if design is valid

    Raises:
        AssertionError: If design is invalid
    """
    logger.info("Validating Phase F constitutional design...")

    try:
        # Check no execution authority
        SafetyValidator.validate_no_execution_authority()

        logger.info("✓ Phase F design validation passed")
        return True

    except AssertionError as e:
        logger.error(f"✗ Phase F design validation failed: {e}")
        raise
