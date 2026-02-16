"""
Phase I Scheduler: Observatory cycle runner.

Called by crypto_main.py scheduler to run the observatory analysis cycle.
"""

import logging
import time
from datetime import datetime, timezone

from phase_i_strategy.config import (
    PHASE_I_STRATEGY_ENABLED,
    PHASE_I_STRATEGY_KILL_SWITCH,
    MAX_OBSERVATORY_CYCLE_SECONDS,
)
from phase_i_strategy.persistence import PhaseIPersistence
from phase_i_strategy.observatory.anomaly_detector import StrategyAnomalyDetector

logger = logging.getLogger(__name__)


def run_observatory_cycle(runtime, trigger: str = "scheduled") -> None:
    """
    Run a single observatory analysis cycle.

    Reads recent signals, detects anomalies, persists results.

    Args:
        runtime: The application runtime object (for scope).
        trigger: What triggered this cycle ('startup', 'scheduled').
    """
    if not PHASE_I_STRATEGY_ENABLED or PHASE_I_STRATEGY_KILL_SWITCH:
        return

    scope = str(runtime.scope)
    start = time.monotonic()
    logger.info("PHASE_I_OBSERVATORY_CYCLE_START | trigger=%s scope=%s", trigger, scope)

    try:
        persistence = PhaseIPersistence(scope)
        run_state = persistence.load_run_state()

        detector = StrategyAnomalyDetector(persistence)
        anomalies = detector.detect_anomalies()

        if anomalies:
            for anomaly in anomalies:
                persistence.append_anomaly(anomaly)
                logger.warning(
                    "STRATEGY_ANOMALY | type=%s strategy=%s detail=%s",
                    anomaly.get("anomaly_type"),
                    anomaly.get("strategy_name"),
                    anomaly.get("detail"),
                )

        # Update run state
        run_state["last_observatory_run"] = datetime.now(timezone.utc).isoformat()
        run_state["total_anomalies_detected"] = run_state.get("total_anomalies_detected", 0) + len(anomalies)
        persistence.save_run_state(run_state)

        elapsed = time.monotonic() - start
        logger.info(
            "PHASE_I_OBSERVATORY_CYCLE_DONE | trigger=%s anomalies=%d elapsed=%.1fs",
            trigger, len(anomalies), elapsed,
        )

        if elapsed > MAX_OBSERVATORY_CYCLE_SECONDS:
            logger.warning(
                "PHASE_I_OBSERVATORY_SLOW | elapsed=%.1fs > limit=%ds",
                elapsed, MAX_OBSERVATORY_CYCLE_SECONDS,
            )

    except Exception as e:
        elapsed = time.monotonic() - start
        logger.error(
            "PHASE_I_OBSERVATORY_CYCLE_FAILED | trigger=%s error=%s elapsed=%.1fs",
            trigger, e, elapsed,
            exc_info=True,
        )
