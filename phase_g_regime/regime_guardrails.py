"""
Phase G Regime Guardrails (Stage 4): Constitutional constraints for regime proposals.

Before any proposal reaches governance:
1. Enforce cooldown (minimum dwell time)
2. Block during insufficient liquidity
3. Block if Phase F verdict = insufficient data
4. Block if external disagreement > 40%
5. Cap maximum regime flips per week

If blocked → emit REGIME_CHANGE_DEFERRED.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)

# Guardrail constants
MAX_FLIPS_PER_WEEK = 2
MAX_EXTERNAL_DISAGREEMENT = 0.40
EMERGENCY_DRAWDOWN_THRESHOLD = -25.0

MIN_DWELL_HOURS = {
    "crypto": 4.0,
    "swing": 72.0,
}


class RegimeGuardrails:
    """
    Constitutional constraints for regime change proposals.
    Every check is logged. No silent decisions.
    """

    def check_proposal(
        self,
        proposal: Dict[str, Any],
        run_state: Dict[str, Any],
        current_drawdown: float,
        scope_type: str = "crypto",
    ) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """
        Apply all guardrail checks to a regime change proposal.

        Returns:
            (approved, reason, check_log)
            - approved: True if all guardrails pass
            - reason: human-readable reason if blocked
            - check_log: list of all check records for audit
        """
        checks: List[Dict[str, Any]] = []
        emergency = current_drawdown < EMERGENCY_DRAWDOWN_THRESHOLD

        # ====================================================================
        # 1. Cooldown / dwell time
        # ====================================================================
        min_dwell = MIN_DWELL_HOURS.get(scope_type, 4.0)
        regime_entered = run_state.get("regime_entered_utc")
        duration_hours = 0.0

        if regime_entered:
            try:
                entered_dt = datetime.fromisoformat(regime_entered)
                if entered_dt.tzinfo is None:
                    entered_dt = entered_dt.replace(tzinfo=timezone.utc)
                duration_hours = (datetime.now(timezone.utc) - entered_dt).total_seconds() / 3600
            except (ValueError, TypeError):
                pass

        dwell_ok = duration_hours >= min_dwell or emergency
        checks.append({
            "check": "cooldown_dwell",
            "passed": dwell_ok,
            "duration_hours": round(duration_hours, 1),
            "min_dwell_hours": min_dwell,
            "emergency_override": emergency,
            "reason": (
                f"dwell {duration_hours:.1f}h >= {min_dwell}h"
                if dwell_ok and not emergency
                else f"emergency override (drawdown={current_drawdown:.1f}%)"
                if emergency
                else f"dwell {duration_hours:.1f}h < {min_dwell}h"
            ),
        })

        if not dwell_ok:
            return False, f"REGIME_CHANGE_DEFERRED: minimum dwell not met ({duration_hours:.1f}h < {min_dwell}h)", checks

        # ====================================================================
        # 2. Insufficient liquidity
        # ====================================================================
        # Placeholder: block if proposal metadata indicates low liquidity
        low_liquidity = proposal.get("low_liquidity", False)
        checks.append({
            "check": "liquidity",
            "passed": not low_liquidity,
            "reason": "liquidity insufficient" if low_liquidity else "liquidity OK",
        })

        if low_liquidity:
            return False, "REGIME_CHANGE_DEFERRED: insufficient liquidity", checks

        # ====================================================================
        # 3. Phase F data sufficiency
        # ====================================================================
        verdict_type = proposal.get("phase_f_verdict_type")
        data_sufficient = verdict_type not in (None, "INSUFFICIENT_DATA")
        checks.append({
            "check": "phase_f_data",
            "passed": data_sufficient,
            "verdict_type": verdict_type,
            "reason": (
                f"Phase F verdict: {verdict_type}"
                if data_sufficient
                else "Phase F data insufficient or unavailable"
            ),
        })

        if not data_sufficient:
            return False, "REGIME_CHANGE_DEFERRED: Phase F data insufficient", checks

        # ====================================================================
        # 4. External disagreement threshold
        # ====================================================================
        cross_asset_score = proposal.get("cross_asset_score", 1.0)
        external_disagreement = 1.0 - cross_asset_score
        disagreement_ok = external_disagreement <= MAX_EXTERNAL_DISAGREEMENT

        checks.append({
            "check": "external_disagreement",
            "passed": disagreement_ok,
            "disagreement": round(external_disagreement, 3),
            "threshold": MAX_EXTERNAL_DISAGREEMENT,
            "reason": (
                f"disagreement {external_disagreement:.1%} <= {MAX_EXTERNAL_DISAGREEMENT:.0%}"
                if disagreement_ok
                else f"disagreement {external_disagreement:.1%} > {MAX_EXTERNAL_DISAGREEMENT:.0%}"
            ),
        })

        if not disagreement_ok:
            return False, f"REGIME_CHANGE_DEFERRED: external disagreement {external_disagreement:.1%} > {MAX_EXTERNAL_DISAGREEMENT:.0%}", checks

        # ====================================================================
        # 5. Maximum flips per week
        # ====================================================================
        changes = run_state.get("regime_changes_this_week", [])
        # Prune entries older than 7 days
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        recent_changes = [c for c in changes if c.get("timestamp", "") >= cutoff]
        flips = len(recent_changes)
        flips_ok = flips < MAX_FLIPS_PER_WEEK

        checks.append({
            "check": "max_flips_per_week",
            "passed": flips_ok,
            "flips_this_week": flips,
            "max_allowed": MAX_FLIPS_PER_WEEK,
            "reason": (
                f"flips this week: {flips} < {MAX_FLIPS_PER_WEEK}"
                if flips_ok
                else f"flips this week: {flips} >= {MAX_FLIPS_PER_WEEK}"
            ),
        })

        if not flips_ok:
            return False, f"REGIME_CHANGE_DEFERRED: max regime flips per week reached ({flips})", checks

        # ====================================================================
        # All guardrails passed
        # ====================================================================
        return True, "all guardrails passed", checks
