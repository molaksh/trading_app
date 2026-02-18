"""
Phase I: Strategy Intelligence & Autonomy.

Phase I-A (Observatory): Tracks per-strategy signal generation and performance,
detects anomalies (zero signals, degradation, staleness).

Phase I-B (Research Engine): Backtests parameter variations during downtime,
validates via walk-forward, and records findings for future governance.

Public API for Phase I strategy module.
"""

from phase_i_strategy.config import (
    PHASE_I_STRATEGY_ENABLED,
    PHASE_I_STRATEGY_KILL_SWITCH,
    PHASE_I_RESEARCH_ENABLED,
)

__all__ = [
    "PHASE_I_STRATEGY_ENABLED",
    "PHASE_I_STRATEGY_KILL_SWITCH",
    "PHASE_I_RESEARCH_ENABLED",
]
