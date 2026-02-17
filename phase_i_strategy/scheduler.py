"""
Phase I Scheduler: Observatory cycle runner.

Called by crypto_main.py scheduler to run the observatory analysis cycle.
Runs performance scoring + anomaly detection, persists results.
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
from phase_i_strategy.observatory.performance_scorer import StrategyPerformanceScorer
from phase_i_strategy.observatory.anomaly_detector import StrategyAnomalyDetector

logger = logging.getLogger(__name__)


def run_observatory_cycle(runtime, trigger: str = "scheduled") -> None:
    """
    Run a single observatory analysis cycle.

    Steps:
    1. Score all strategies (rolling-window performance metrics)
    2. Persist performance snapshot
    3. Detect anomalies (ZERO_SIGNAL, ALL_FLAT, DEGRADATION)
    4. Persist anomalies
    5. Update run state

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

        # Step 1: Score all strategies
        scorer = StrategyPerformanceScorer(persistence)
        performance_scores = scorer.score_all_strategies()

        if performance_scores:
            # Step 2: Persist performance snapshot
            now_iso = datetime.now(timezone.utc).isoformat()
            snapshot = {
                "timestamp": now_iso,
                "trigger": trigger,
                "strategies": performance_scores,
            }
            persistence.append_performance_snapshot(snapshot)

            # Log summary
            for name, scores in performance_scores.items():
                logger.info(
                    "STRATEGY_HEALTH | strategy=%s health=%d win_rate=%.1f%% "
                    "trades=%d signals=%d flat_ratio=%.1f%%",
                    name,
                    scores.get("health_score", 0),
                    scores.get("win_rate", 0) * 100,
                    scores.get("trade_count", 0),
                    scores.get("signal_count", 0),
                    scores.get("flat_ratio", 0) * 100,
                )

        # Step 3: Detect anomalies (pass performance scores for DEGRADATION check)
        detector = StrategyAnomalyDetector(persistence)
        anomalies = detector.detect_anomalies(performance_scores=performance_scores)

        # Step 4: Persist anomalies
        if anomalies:
            for anomaly in anomalies:
                persistence.append_anomaly(anomaly)
                logger.warning(
                    "STRATEGY_ANOMALY | type=%s strategy=%s detail=%s",
                    anomaly.get("anomaly_type"),
                    anomaly.get("strategy_name"),
                    anomaly.get("detail"),
                )

        # Step 5: Update run state
        run_state["last_observatory_run"] = datetime.now(timezone.utc).isoformat()
        run_state["total_anomalies_detected"] = run_state.get("total_anomalies_detected", 0) + len(anomalies)
        run_state["last_performance_scores"] = {
            name: scores.get("health_score", 0) for name, scores in performance_scores.items()
        } if performance_scores else {}
        persistence.save_run_state(run_state)

        elapsed = time.monotonic() - start
        logger.info(
            "PHASE_I_OBSERVATORY_CYCLE_DONE | trigger=%s strategies=%d anomalies=%d elapsed=%.1fs",
            trigger, len(performance_scores), len(anomalies), elapsed,
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
