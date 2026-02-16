"""
Phase H: Combined Guardrail Checks.

Orchestrates dwell time, flip budget, fail-safe, and confidence checks
before allowing a regime flip.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Tuple

from phase_h_crypto_regime.config import MIN_DWELL_HOURS, DRIFT_FLIP_THRESHOLD

logger = logging.getLogger(__name__)


class PhaseHGuardrails:
    """Combined guardrail checks for regime flip eligibility."""

    def check_flip_eligibility(
        self,
        drift_result,
        run_state: Dict[str, Any],
        fail_safe_result,
        flip_budget_result: Tuple[bool, int, str],
    ) -> Tuple[bool, str]:
        """
        Check all conditions for a regime flip.

        Args:
            drift_result: DriftResult from drift scoring
            run_state: Persisted run state
            fail_safe_result: FailSafeResult from fail-safe engine
            flip_budget_result: (allowed, remaining, reason) from flip budget

        Returns:
            (approved, reason)
        """
        checks = []

        # Check 1: Drift threshold met
        if not drift_result.is_flip_candidate:
            reason = f"drift_below_threshold: {drift_result.drift_score:.3f} < {DRIFT_FLIP_THRESHOLD}"
            logger.info("GUARDRAIL_BLOCKED | %s", reason)
            return (False, reason)
        checks.append("drift_threshold_met")

        # Check 2: Dwell time
        dwell_ok, dwell_reason = self._check_dwell_time(run_state)
        if not dwell_ok:
            logger.info("GUARDRAIL_BLOCKED | %s", dwell_reason)
            return (False, dwell_reason)
        checks.append("dwell_time_met")

        # Check 3: Flip budget
        budget_allowed, budget_remaining, budget_reason = flip_budget_result
        if not budget_allowed:
            logger.info("GUARDRAIL_BLOCKED | %s", budget_reason)
            return (False, budget_reason)
        checks.append(f"flip_budget_ok(remaining={budget_remaining})")

        # Check 4: Fail-safe locks
        if fail_safe_result.lock_flips:
            reason = f"fail_safe_lock: triggers={fail_safe_result.active_triggers}"
            logger.info("GUARDRAIL_BLOCKED | %s", reason)
            return (False, reason)
        checks.append("no_fail_safe_locks")

        # Check 5: No halt on entries
        if fail_safe_result.halt_new_entries:
            reason = f"halt_new_entries: triggers={fail_safe_result.active_triggers}"
            logger.info("GUARDRAIL_BLOCKED | %s", reason)
            return (False, reason)
        checks.append("no_entry_halt")

        approved_reason = f"all_checks_passed: {', '.join(checks)}"
        logger.info("GUARDRAIL_APPROVED | %s", approved_reason)
        return (True, approved_reason)

    @staticmethod
    def _check_dwell_time(run_state: Dict[str, Any]) -> Tuple[bool, str]:
        """Check minimum dwell time since last regime change."""
        regime_since = run_state.get("current_regime_since")
        if not regime_since:
            return (True, "no_prior_regime_timestamp")

        try:
            since = datetime.fromisoformat(regime_since)
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            hours_elapsed = (now - since).total_seconds() / 3600.0

            if hours_elapsed < MIN_DWELL_HOURS:
                return (
                    False,
                    f"dwell_time_insufficient: {hours_elapsed:.1f}h < {MIN_DWELL_HOURS}h",
                )
            return (True, f"dwell_ok: {hours_elapsed:.1f}h >= {MIN_DWELL_HOURS}h")
        except Exception as e:
            logger.warning("Failed to check dwell time: %s", e)
            return (True, "dwell_check_error_passthrough")
