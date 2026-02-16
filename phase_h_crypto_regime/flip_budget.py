"""
Phase H: Flip Budget Control.

Tracks regime flips over a rolling 7-day window.
Max 3 flips allowed. Emits AUTONOMY_LOCK when exceeded and locks for 24h.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple

from phase_h_crypto_regime.config import MAX_FLIPS_PER_7_DAYS, FLIP_LOCKOUT_HOURS

logger = logging.getLogger(__name__)


class FlipBudget:
    """Tracks and enforces flip budget over rolling 7-day window."""

    def can_flip(self, run_state: Dict[str, Any]) -> Tuple[bool, int, str]:
        """
        Check if a flip is allowed.

        Args:
            run_state: Persisted run state with flip_history

        Returns:
            (allowed, remaining, reason)
        """
        now = datetime.now(timezone.utc)

        # Check lockout
        fail_safe = run_state.get("fail_safe_state", {})
        lockout_until = fail_safe.get("flip_lockout_until")
        if lockout_until:
            try:
                lockout_ts = datetime.fromisoformat(lockout_until)
                if lockout_ts.tzinfo is None:
                    lockout_ts = lockout_ts.replace(tzinfo=timezone.utc)
                if now < lockout_ts:
                    return (False, 0, f"AUTONOMY_LOCK: locked until {lockout_until}")
            except Exception:
                pass

        # Count flips in last 7 days
        flip_history = run_state.get("flip_history", [])
        cutoff = now - timedelta(days=7)

        recent_flips = 0
        for flip in flip_history:
            try:
                ts = datetime.fromisoformat(flip["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    recent_flips += 1
            except Exception:
                continue

        remaining = MAX_FLIPS_PER_7_DAYS - recent_flips

        if remaining <= 0:
            return (False, 0, f"FLIP_BUDGET_EXHAUSTED: {recent_flips}/{MAX_FLIPS_PER_7_DAYS} in 7d")

        return (True, remaining, f"budget_ok: {recent_flips}/{MAX_FLIPS_PER_7_DAYS} used")

    def record_flip(
        self,
        run_state: Dict[str, Any],
        from_regime: str,
        to_regime: str,
    ) -> None:
        """
        Record a flip in run_state.

        Args:
            run_state: Mutable run state dict
            from_regime: Previous regime
            to_regime: New regime
        """
        now = datetime.now(timezone.utc)

        if "flip_history" not in run_state:
            run_state["flip_history"] = []

        run_state["flip_history"].append({
            "timestamp": now.isoformat(),
            "from_regime": from_regime,
            "to_regime": to_regime,
        })

        # Trim history to last 30 entries
        run_state["flip_history"] = run_state["flip_history"][-30:]

        # Check if budget is now exhausted — set lockout
        _, remaining, _ = self.can_flip(run_state)
        if remaining <= 0:
            lockout_until = now + timedelta(hours=FLIP_LOCKOUT_HOURS)
            run_state.setdefault("fail_safe_state", {})["flip_lockout_until"] = lockout_until.isoformat()
            logger.warning(
                "AUTONOMY_LOCK | flip budget exhausted, locked until %s",
                lockout_until.isoformat(),
            )
