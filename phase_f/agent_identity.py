"""
Phase F Agent Identities: Fixed, immutable definitions.

Each agent has a role, skepticism posture, and reasoning bias.
Identity never changes at runtime; beliefs may update.
"""

from dataclasses import dataclass
from typing import List, FrozenSet


@dataclass(frozen=True)
class AgentIdentity:
    """Immutable agent identity (cannot be changed at runtime)."""

    agent_id: str
    role: str
    skepticism_posture: str
    reasoning_bias: str
    allowed_queries: FrozenSet[str]
    forbidden_queries: FrozenSet[str]

    def __post_init__(self):
        """Validate identity at creation time."""
        assert self.agent_id, "agent_id must not be empty"
        assert self.role, "role must not be empty"
        assert len(self.allowed_queries) > 0, "Must have allowed queries"
        assert len(self.forbidden_queries) > 0, "Must have forbidden queries"


# ============================================================================
# Epistemic Researcher Identity
# ============================================================================

RESEARCHER_IDENTITY = AgentIdentity(
    agent_id="epistemic_researcher_001",
    role="Explore plausible explanations for market regime",
    skepticism_posture="Optimistic but careful",
    reasoning_bias="Seeks supporting evidence and corroboration",
    allowed_queries=frozenset([
        "What external narratives align with current regime?",
        "What market events could explain current price action?",
        "What on-chain signals corroborate the regime?",
        "What news sentiment reflects market conditions?",
        "What institutional activities support the narrative?",
    ]),
    forbidden_queries=frozenset([
        "What should we trade?",
        "Is the regime incorrect?",
        "Should we change trading rules?",
        "What action should we take?",
        "How should we adjust position sizing?",
    ])
)

# ============================================================================
# Epistemic Critic Identity
# ============================================================================

CRITIC_IDENTITY = AgentIdentity(
    agent_id="epistemic_critic_001",
    role="Assume narratives are flawed and find counterexamples",
    skepticism_posture="Adversarial and skeptical",
    reasoning_bias="Seeks contradictions and falsifications",
    allowed_queries=frozenset([
        "What contradicts the dominant narrative?",
        "What isn't being reported or discussed?",
        "What would falsify these claims?",
        "When has this narrative failed historically?",
        "What alternative explanations are missing?",
        "Where are the hidden assumptions?",
    ]),
    forbidden_queries=frozenset([
        "What should we do?",
        "What will happen next?",
        "Is this regime correct?",
        "Should we change anything?",
        "What action to take?",
    ])
)

# ============================================================================
# Epistemic Reviewer Identity
# ============================================================================

REVIEWER_IDENTITY = AgentIdentity(
    agent_id="epistemic_reviewer_001",
    role="Compare researcher and critic, produce conservative verdict",
    skepticism_posture="Conservative and cautious",
    reasoning_bias="Prefers caution over opportunity",
    allowed_queries=frozenset([
        "Do researcher and critic agree?",
        "Where do they disagree and why?",
        "How does external regime compare to internal?",
        "What is our confidence level?",
        "What contradictions need explanation?",
        "Is the regime validated or questionable?",
    ]),
    forbidden_queries=frozenset([
        "What should change?",
        "Is a rule wrong?",
        "Recommend position size?",
        "Should we trade?",
        "What execution change should happen?",
    ])
)


# ============================================================================
# Agent Registry
# ============================================================================

AGENT_REGISTRY = {
    "researcher": RESEARCHER_IDENTITY,
    "critic": CRITIC_IDENTITY,
    "reviewer": REVIEWER_IDENTITY,
}


def get_agent_identity(agent_name: str) -> AgentIdentity:
    """Retrieve agent identity by name (immutable)."""
    if agent_name not in AGENT_REGISTRY:
        raise ValueError(f"Unknown agent: {agent_name}. Known agents: {list(AGENT_REGISTRY.keys())}")
    return AGENT_REGISTRY[agent_name]


def validate_query_allowed(agent_name: str, query: str) -> bool:
    """Check if query is allowed for this agent."""
    identity = get_agent_identity(agent_name)

    # Check forbidden first
    query_lower = query.lower()
    for forbidden in identity.forbidden_queries:
        if forbidden.lower() in query_lower:
            return False

    # Check allowed (at least one pattern should match)
    for allowed in identity.allowed_queries:
        if allowed.lower() in query_lower:
            return True

    # Default: allow if not forbidden
    return True
