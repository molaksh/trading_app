"""
Phase H: Full Crypto Regime Autonomy.

Autonomous composite-macro + per-asset regime management with
hard fail-safe protections. Paper mode auto-applies flips;
live mode generates proposals only (unless explicitly enabled).

Public API for Phase H crypto regime autonomy module.
"""

from phase_h_crypto_regime.config import (
    PHASE_H_CRYPTO_ENABLED,
    PHASE_H_CRYPTO_LIVE_AUTONOMY,
    PHASE_H_CRYPTO_KILL_SWITCH,
)
from phase_h_crypto_regime.autonomy_engine import PhaseHAutonomyEngine

__all__ = [
    "PhaseHAutonomyEngine",
    "PHASE_H_CRYPTO_ENABLED",
    "PHASE_H_CRYPTO_LIVE_AUTONOMY",
    "PHASE_H_CRYPTO_KILL_SWITCH",
]
