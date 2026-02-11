"""
Phase F Schemas: Pydantic models for epistemic agent outputs.

All models are immutable (frozen) to prevent mutation.
All verdicts are validated to prevent prescriptive language.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime


class SentimentEnum(str, Enum):
    """Article sentiment (factual classification only)."""
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"


class NarrativeConsistency(str, Enum):
    """How consistent is the external narrative?"""
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


class VerdictType(str, Enum):
    """Allowed verdict types (whitelist)."""
    REGIME_VALIDATED = "REGIME_VALIDATED"
    REGIME_QUESTIONABLE = "REGIME_QUESTIONABLE"
    HIGH_NOISE_NO_ACTION = "HIGH_NOISE_NO_ACTION"
    POSSIBLE_STRUCTURAL_SHIFT_OBSERVE = "POSSIBLE_STRUCTURAL_SHIFT_OBSERVE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# ============================================================================
# External Data Extraction
# ============================================================================


class Claim(BaseModel):
    """Factual statement extracted from external source."""

    model_config = ConfigDict(frozen=True)

    claim_text: str = Field(
        ..., description="Factual claim extracted from article"
    )
    source: str = Field(..., description="Source name (e.g., 'CoinTelegraph')")
    source_url: str = Field(..., description="Full URL to article")
    publication_timestamp: str = Field(
        ..., description="ISO format timestamp of publication"
    )
    confidence_in_claim: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence this is factual (not opinion)"
    )
    is_factual: bool = Field(
        ..., description="True if factual, False if opinion/speculation"
    )
    sentiment: SentimentEnum = Field(
        ..., description="Market sentiment implied by claim"
    )

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, v):
        """Validate URL format."""
        assert v.startswith("http"), "URL must start with http/https"
        return v

    @field_validator("publication_timestamp")
    @classmethod
    def validate_timestamp(cls, v):
        """Validate ISO timestamp."""
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"Invalid ISO timestamp: {v}")
        return v


# ============================================================================
# Agent Reasoning
# ============================================================================


class Hypothesis(BaseModel):
    """Belief formed by agent reasoning (probabilistic, uncertain)."""

    model_config = ConfigDict(frozen=True)

    hypothesis_text: str = Field(
        ..., description="Natural language hypothesis statement"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this hypothesis (0.0-1.0)",
    )
    uncertainty: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Epistemic uncertainty (bounds confidence)",
    )
    supporting_claims: List[Claim] = Field(
        default_factory=list, description="Claims supporting hypothesis"
    )
    contradicting_claims: List[Claim] = Field(
        default_factory=list, description="Claims contradicting hypothesis"
    )
    memory_references: List[str] = Field(
        default_factory=list, description="IDs of similar past events"
    )
    reasoning_steps: List[str] = Field(
        ..., description="How confidence was derived (audit trail)"
    )

    @field_validator("reasoning_steps")
    @classmethod
    def validate_reasoning_steps(cls, v):
        """Verify reasoning is non-empty and documented."""
        assert len(v) > 0, "Reasoning steps must not be empty"
        return v

    @field_validator("hypothesis_text")
    @classmethod
    def no_prescriptive_language(cls, v):
        """Hypothesis must be descriptive, never prescriptive."""
        forbidden = ["execute", "trade", "buy", "sell", "should", "must"]
        text_lower = v.lower()
        for word in forbidden:
            assert (
                word not in text_lower
            ), f"Hypothesis contains forbidden action word: {word}"
        return v


# ============================================================================
# Agent Reports
# ============================================================================


class ResearcherReport(BaseModel):
    """Output from Epistemic Researcher agent."""

    model_config = ConfigDict(frozen=True)

    hypotheses: List[Hypothesis] = Field(
        ..., description="Plausible explanations formed"
    )
    sources_analyzed: int = Field(..., description="Number of unique sources")
    articles_fetched: int = Field(..., description="Number of articles reviewed")
    tokens_used: int = Field(..., description="OpenAI tokens consumed")
    runtime_seconds: float = Field(..., description="Execution time")


class CriticReport(BaseModel):
    """Output from Epistemic Critic agent."""

    model_config = ConfigDict(frozen=True)

    challenges: List[Hypothesis] = Field(
        ..., description="Adversarial challenges to narrative"
    )
    counterexamples: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Cases where narrative failed historically",
    )
    contradictions: List[Dict[str, Any]] = Field(
        default_factory=list, description="Internal contradictions in narrative"
    )
    sources_analyzed: int = Field(..., description="Number of unique sources")
    articles_fetched: int = Field(..., description="Number of articles reviewed")
    tokens_used: int = Field(..., description="OpenAI tokens consumed")
    runtime_seconds: float = Field(..., description="Execution time")


# ============================================================================
# Verdict (Core Output)
# ============================================================================


class Verdict(BaseModel):
    """
    Conservative reviewer verdict about regime validity.

    CRITICAL: This is NEVER prescriptive. It expresses belief, not decision.
    """

    model_config = ConfigDict(frozen=True)

    verdict: VerdictType = Field(
        ..., description="Verdict type (from whitelist)"
    )
    regime_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in internal regime validity"
    )
    confidence_change_from_internal: float = Field(
        ...,
        description="Delta from last known internal confidence (can be negative)",
    )
    narrative_consistency: NarrativeConsistency = Field(
        ..., description="How consistent are external narratives?"
    )
    num_sources_analyzed: int = Field(
        ..., description="Total unique sources used by all agents"
    )
    num_contradictions: int = Field(
        ..., description="Number of major contradictions found"
    )
    summary_for_governance: str = Field(
        ...,
        description="Layer 2: Used by Phase C for confidence weighting (confidential)",
    )
    reasoning_summary: str = Field(
        ..., description="High-level explanation of verdict"
    )

    @field_validator("verdict")
    @classmethod
    def validate_verdict_type(cls, v):
        """Verdict must be from whitelist."""
        allowed = [e.value for e in VerdictType]
        assert v.value in allowed, f"Verdict {v.value} not in whitelist {allowed}"
        return v

    @field_validator("summary_for_governance")
    @classmethod
    def no_action_words_governance(cls, v):
        """Governance summary must be epistemic, not prescriptive."""
        forbidden = [
            "execute",
            "trade",
            "buy",
            "sell",
            "position",
            "remove",
            "add",
            "change",
            "reduce",
            "increase",
        ]
        text_lower = v.lower()
        for word in forbidden:
            assert (
                word not in text_lower
            ), f"Governance summary contains forbidden action word: {word}"
        return v

    @field_validator("reasoning_summary")
    @classmethod
    def no_action_words_reasoning(cls, v):
        """Reasoning must be epistemic, not prescriptive."""
        forbidden = [
            "execute",
            "trade",
            "buy",
            "sell",
            "should",
            "must",
            "recommend",
        ]
        text_lower = v.lower()
        for word in forbidden:
            assert (
                word not in text_lower
            ), f"Reasoning contains forbidden word: {word}"
        return v


# ============================================================================
# Memory Models
# ============================================================================


class EpistemicMemoryEvent(BaseModel):
    """
    Append-only episodic memory record.

    Records OBSERVATIONS, never CAUSATION.
    Never used as optimization signal.
    """

    model_config = ConfigDict(frozen=True)

    timestamp: str = Field(..., description="ISO format timestamp")
    event_type: str = Field(
        ..., description="EXTERNAL_CLAIM, NARRATIVE_SHIFT, PRICE_REACTION, etc."
    )
    source: str = Field(..., description="Where observation came from")
    claim: str = Field(..., description="What was claimed/observed")
    market_snapshot: Dict[str, Any] = Field(
        ..., description="Market state at time of event"
    )
    researcher_belief: Optional[Hypothesis] = Field(
        None, description="What researcher believed about this"
    )
    critic_challenge: Optional[Hypothesis] = Field(
        None, description="What critic challenged"
    )
    outcome_7d_later: Optional[Dict[str, Any]] = Field(
        None, description="Market outcome 7 days later"
    )

    @field_validator("claim")
    @classmethod
    def no_causation_words(cls, v):
        """Claim must be observation, not causal reasoning."""
        forbidden = ["causes", "leads to", "->", "results in", "makes", "forces"]
        text_lower = v.lower()
        for word in forbidden:
            assert word not in text_lower, f"Claim contains forbidden word: {word}"
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v):
        """Validate ISO timestamp."""
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"Invalid ISO timestamp: {v}")
        return v


class SemanticMemorySummary(BaseModel):
    """
    Versioned semantic summary of patterns.

    Updated weekly/monthly by reviewer.
    Never used as rules or triggers.
    """

    model_config = ConfigDict(frozen=True)

    period_start: str = Field(
        ..., description="Start of analysis period (ISO format)"
    )
    period_end: str = Field(
        ..., description="End of analysis period (ISO format)"
    )
    version: int = Field(
        ..., ge=1, description="Version number (never overwritten)"
    )
    patterns: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Pattern observations with confidence scores",
    )
    notes: str = Field(
        default="",
        description="Reviewer notes about patterns (not rules)",
    )

    @field_validator("patterns")
    @classmethod
    def no_rules_in_patterns(cls, v):
        """Patterns must be observations, not rules."""
        for pattern in v:
            pattern_text = str(pattern).lower()
            assert "if" not in pattern_text, "Patterns must not encode rules"
            assert "->" not in pattern_text, "Patterns must not be conditional"
        return v


# ============================================================================
# Internal Context Snapshot
# ============================================================================


class InternalContextSnapshot(BaseModel):
    """Snapshot of current trading system state."""

    model_config = ConfigDict(frozen=True)

    timestamp: str = Field(..., description="When snapshot was taken")
    current_regime: str = Field(..., description="Current regime (RISK_ON, etc.)")
    regime_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Internal confidence in regime"
    )
    regime_change_ts: Optional[str] = Field(
        None, description="When regime last changed"
    )
    volatility: float = Field(..., description="Current realized volatility")
    trend_slope: float = Field(..., description="Current trend slope")
    drawdown_pct: float = Field(..., description="Current drawdown %")
    num_open_positions: int = Field(..., description="Number of open trades")
    universe_size: int = Field(..., description="Size of trading universe")


# ============================================================================
# Run Metadata
# ============================================================================


class Phase_F_RunMetadata(BaseModel):
    """Metadata for a complete Phase F run."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(..., description="Unique run identifier")
    start_timestamp: str = Field(..., description="When run started")
    end_timestamp: Optional[str] = Field(None, description="When run completed")
    status: str = Field(
        ..., pattern="^(RUNNING|COMPLETED|TIMEOUT|ERROR|COST_CAP_EXCEEDED)$"
    )
    researcher_runtime_seconds: float = Field(default=0)
    critic_runtime_seconds: float = Field(default=0)
    reviewer_runtime_seconds: float = Field(default=0)
    total_runtime_seconds: float = Field(default=0)
    total_tokens_used: int = Field(default=0)
    total_cost_usd: float = Field(default=0.0)
    error_message: Optional[str] = Field(None)
