"""
Strict JSON schemas for all governance agent outputs.

Uses Pydantic for validation. All agent outputs MUST conform to these schemas.
"""

from typing import List, Dict, Any, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field, validator


class ProposalEvidence(BaseModel):
    """Evidence backing a proposal."""
    missed_signals: int = Field(..., description="Number of missed high-confidence signals")
    scan_starvation: List[str] = Field(default_factory=list, description="Symbols never scanned")
    performance_notes: str = Field("", description="Performance observations")
    dead_symbols: List[str] = Field(default_factory=list, description="Symbols with no fills")

    class Config:
        frozen = True


class ProposalSchema(BaseModel):
    """Schema for Agent 1 (Proposer) output."""
    proposal_id: str = Field(..., description="UUID of proposal")
    environment: Literal["paper", "live"] = Field(..., description="Trading environment")
    proposal_type: Literal[
        "ADD_SYMBOLS",
        "REMOVE_SYMBOLS",
        "ADJUST_RULE",
        "ADJUST_THRESHOLD"
    ] = Field(..., description="Type of proposal")
    symbols: List[str] = Field(..., description="Affected symbols")
    rationale: str = Field(..., description="Why this proposal is made")
    evidence: ProposalEvidence = Field(..., description="Supporting evidence")
    risk_notes: str = Field("", description="Identified risks")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level 0-1")
    non_binding: bool = Field(True, description="MUST be true - no auto-apply")

    @validator("non_binding")
    def non_binding_must_be_true(cls, v):
        """Constitutional requirement: proposals are never binding."""
        if v is not True:
            raise ValueError("non_binding must always be True (constitutional requirement)")
        return v

    @validator("symbols")
    def symbols_not_empty(cls, v):
        """At least one symbol required."""
        if not v:
            raise ValueError("symbols list cannot be empty")
        return v

    class Config:
        frozen = True


class CriticismSchema(BaseModel):
    """Schema for Agent 2 (Critic) output."""
    proposal_id: str = Field(..., description="UUID of referenced proposal")
    criticisms: List[str] = Field(..., description="List of critical observations")
    counter_evidence: str = Field("", description="Counter-arguments")
    recommendation: Literal["PROCEED", "CAUTION", "REJECT"] = Field(
        ..., description="Critic's recommendation"
    )

    @validator("criticisms")
    def criticisms_not_empty(cls, v):
        """Critic must provide at least one criticism."""
        if not v:
            raise ValueError("criticisms list cannot be empty")
        return v

    class Config:
        frozen = True


class ConstitutionalViolation(BaseModel):
    """Single constitutional violation."""
    rule_name: str = Field(..., description="Name of violated rule")
    violation: str = Field(..., description="Description of violation")
    severity: Literal["CRITICAL", "MAJOR", "MINOR"] = Field(...)


class AuditSchema(BaseModel):
    """Schema for Agent 3 (Auditor) output."""
    proposal_id: str = Field(..., description="UUID of referenced proposal")
    constitution_passed: bool = Field(..., description="True if all rules pass")
    violations: List[ConstitutionalViolation] = Field(
        default_factory=list, description="Constitutional violations found"
    )

    @validator("violations")
    def violations_required_if_failed(cls, v, values):
        """If constitution failed, violations must be present."""
        if "constitution_passed" in values and not values["constitution_passed"]:
            if not v:
                raise ValueError("violations required when constitution_passed is False")
        return v

    class Config:
        frozen = True


class SynthesisSchema(BaseModel):
    """Schema for Agent 4 (Synthesizer) output."""
    proposal_id: str = Field(..., description="UUID of referenced proposal")
    summary: str = Field(..., description="Human-readable summary")
    key_risks: List[str] = Field(..., description="Key risks to highlight")
    final_recommendation: Literal["APPROVE", "REJECT", "DEFER"] = Field(
        ..., description="Final recommendation"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level")

    @validator("key_risks")
    def key_risks_not_empty(cls, v):
        """Always identify at least one risk."""
        if not v:
            raise ValueError("key_risks must include at least one item")
        return v

    class Config:
        frozen = True


class GovernanceEvent(BaseModel):
    """Event for governance_events.jsonl logging."""
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    event_type: Literal[
        "GOVERNANCE_PROPOSAL_CREATED",
        "GOVERNANCE_PROPOSAL_CRITIQUED",
        "GOVERNANCE_PROPOSAL_AUDITED",
        "GOVERNANCE_PROPOSAL_SYNTHESIZED",
        "GOVERNANCE_PROPOSAL_APPROVED",
        "GOVERNANCE_PROPOSAL_REJECTED",
        "GOVERNANCE_PROPOSAL_EXPIRED",
        "GOVERNANCE_CONSTITUTION_VIOLATION",
        "GOVERNANCE_JOB_STARTED",
        "GOVERNANCE_JOB_COMPLETED",
        "GOVERNANCE_JOB_FAILED",
    ] = Field(..., description="Type of event")
    proposal_id: Optional[str] = Field(None, description="Associated proposal ID")
    environment: Optional[Literal["paper", "live"]] = Field(None, description="Trading environment")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional details")

    class Config:
        frozen = True


class ApprovalSchema(BaseModel):
    """Schema for human approval record."""
    proposal_id: str = Field(..., description="UUID of approved proposal")
    approved_at: str = Field(..., description="ISO 8601 approval timestamp")
    approved_by: str = Field(..., description="Username of approver")
    notes: str = Field("", description="Approval notes")

    class Config:
        frozen = True
