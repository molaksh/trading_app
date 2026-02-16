"""
Phase I: Strategy Intelligence & Autonomy.

Tracks per-strategy signal generation and performance, detects anomalies
(zero signals, degradation, staleness), and provides the observatory
foundation for future research and governance phases.

Public API for Phase I strategy module.
"""

from phase_i_strategy.config import (
    PHASE_I_STRATEGY_ENABLED,
    PHASE_I_STRATEGY_KILL_SWITCH,
)

__all__ = [
    "PHASE_I_STRATEGY_ENABLED",
    "PHASE_I_STRATEGY_KILL_SWITCH",
]
