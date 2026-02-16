"""
Phase H: Scheduler Integration.

Thin wrapper that creates PhaseHAutonomyEngine and calls run_cycle().
Used by crypto_main.py to register as a CryptoSchedulerTask.
"""

import logging

from config.scope import get_scope
from phase_h_crypto_regime.autonomy_engine import PhaseHAutonomyEngine, PhaseHCycleResult

logger = logging.getLogger(__name__)


def run_phase_h_cycle(runtime, trigger: str = "scheduled") -> PhaseHCycleResult:
    """
    Run a single Phase H autonomy cycle.

    Args:
        runtime: RuntimeEnv with portfolio, trade_ledger, etc.
        trigger: What triggered this cycle

    Returns:
        PhaseHCycleResult
    """
    scope = get_scope()

    # Optionally attach verdict reader if available
    verdict_reader = None
    try:
        from governance.verdict_reader import VerdictReader
        verdict_reader = VerdictReader()
    except ImportError:
        logger.debug("VerdictReader not available, Phase F integration disabled")

    engine = PhaseHAutonomyEngine(
        scope=scope,
        runtime=runtime,
        verdict_reader=verdict_reader,
    )

    result = engine.run_cycle(trigger=trigger)

    logger.info(
        "PHASE_H_SCHEDULER | trigger=%s outcome=%s regime=%s cap=%.3f duration=%.1fms",
        trigger, result.action_taken, result.macro_regime,
        result.exposure_cap, result.duration_ms,
    )

    return result
