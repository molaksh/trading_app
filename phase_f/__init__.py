"""
Phase F: Epistemic Market Intelligence

A READ-ONLY observation layer that forms beliefs about external market conditions
and regime validity. Phase F has ZERO authority over execution.

Core Components:
- Epistemic Researcher: Explores plausible explanations
- Epistemic Critic: Assumes narratives are flawed
- Epistemic Reviewer: Compares both, produces verdict

Design Principles:
✅ Observation only (no execution authority)
✅ Epistemic beliefs (probabilistic, uncertain)
✅ Constitutional constraints (immutable, enforced)
✅ Append-only memory (audit trail)
✅ Scheduled off-hours (slow, reflective)
✅ Resource-bounded (timeouts, token limits, cost caps)
"""

from phase_f.schemas import (
    Claim,
    Hypothesis,
    Verdict,
    ResearcherReport,
    CriticReport,
    EpistemicMemoryEvent,
    SemanticMemorySummary,
    InternalContextSnapshot,
    Phase_F_RunMetadata,
)
from phase_f.agent_identity import (
    AgentIdentity,
    RESEARCHER_IDENTITY,
    CRITIC_IDENTITY,
    REVIEWER_IDENTITY,
    get_agent_identity,
    validate_query_allowed,
)
from phase_f.persistence import Phase_F_Persistence, get_persistence
from phase_f.safety_checks import SafetyValidator, validate_phase_f_design

__all__ = [
    # Schemas
    "Claim",
    "Hypothesis",
    "Verdict",
    "ResearcherReport",
    "CriticReport",
    "EpistemicMemoryEvent",
    "SemanticMemorySummary",
    "InternalContextSnapshot",
    "Phase_F_RunMetadata",
    # Agent Identity
    "AgentIdentity",
    "RESEARCHER_IDENTITY",
    "CRITIC_IDENTITY",
    "REVIEWER_IDENTITY",
    "get_agent_identity",
    "validate_query_allowed",
    # Persistence
    "Phase_F_Persistence",
    "get_persistence",
    # Safety
    "SafetyValidator",
    "validate_phase_f_design",
]
