"""
Phase G: Unified Autonomous Universe Governance.

Public API for universe governance module.
"""

from universe.governance.governor import UniverseGovernor, GovernanceDecision
from universe.governance.scorer import UniverseScorer, ScoredCandidate
from universe.governance.config import PHASE_G_ENABLED, PHASE_G_DRY_RUN

__all__ = [
    "UniverseGovernor",
    "GovernanceDecision",
    "UniverseScorer",
    "ScoredCandidate",
    "PHASE_G_ENABLED",
    "PHASE_G_DRY_RUN",
]
