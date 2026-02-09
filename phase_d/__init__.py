"""
Phase D: Constitutional Governance Layer for BTC Regime Gate Analysis.

Phase D studies whether the BTC regime gate is potentially over-constraining
based on evidence from block detection, evidence collection, and eligibility
evaluation.

Key features:
- v0: Block detection + evidence collection (post-facto metrics)
- v1: 5-rule eligibility framework for Phase D eligibility flag

Design principles:
- READ-ONLY analysis layer (never trades, never overrides regimes)
- Informational only (no automatic actions)
- Feature-flagged (default FALSE, opt-in)
- Global kill-switch available
- Fail-safe: If Phase D fails → trading continues unchanged
"""

from phase_d.schemas import BlockType, BlockEvent, BlockEvidence, PhaseEligibilityResult, PhaseDEvent
from phase_d.persistence import PhaseDPersistence

__all__ = [
    "BlockType",
    "BlockEvent",
    "BlockEvidence",
    "PhaseEligibilityResult",
    "PhaseDEvent",
    "PhaseDPersistence",
]
