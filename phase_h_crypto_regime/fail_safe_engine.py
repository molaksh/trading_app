"""
Phase H: Fail-Safe Engine.

Implements 4 fail-safe layers (higher priority overrides lower):
  A) Circuit Breakers: daily PnL, intraday drawdown, consecutive stops
  B) Shock Mode: extreme drawdown + vol expansion
  C) Data Integrity Gate: missing data, stale timestamps, Phase F issues
  D) Auto-Revert: regime flip + performance deterioration → revert

All reads are read-only from runtime (portfolio, trade ledger).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from phase_h_crypto_regime.config import (
    CB_DAILY_PNL_LIMIT,
    CB_INTRADAY_DRAWDOWN_LIMIT,
    CB_CONSECUTIVE_STOPS,
    CB_STOP_WINDOW_HOURS,
    CB_COOLDOWN_HOURS_MIN,
    CB_COOLDOWN_HOURS_MAX,
    SHOCK_DRAWDOWN_THRESHOLD,
    SHOCK_VOL_MULTIPLIER,
    SHOCK_LOCK_HOURS,
    DATA_CONFIDENCE_DECAY,
    DATA_CONFIDENCE_FLOOR,
    DATA_EXPOSURE_SAFETY_FACTOR,
    REVERT_EVAL_HOURS_MIN,
    REVERT_EVAL_HOURS_MAX,
    REVERT_LOCK_HOURS,
)

logger = logging.getLogger(__name__)


@dataclass
class FailSafeContext:
    """Context for fail-safe evaluation."""
    daily_pnl_pct: float = 0.0
    intraday_drawdown_pct: float = 0.0
    consecutive_stops: int = 0
    stop_timestamps: List[str] = field(default_factory=list)
    current_drawdown_pct: float = 0.0
    current_vol_percentile: float = 0.5
    baseline_vol: float = 0.0
    current_vol: float = 0.0
    data_quality_ok: bool = True
    phase_f_verdict: Optional[str] = None
    phase_f_confidence: Optional[float] = None
    current_regime: str = "NEUTRAL"
    last_flip_timestamp: Optional[str] = None
    pnl_since_flip_pct: float = 0.0
    run_state: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FailSafeResult:
    """Result of fail-safe evaluation."""
    halt_new_entries: bool = False
    exposure_override: Optional[float] = None
    lock_flips: bool = False
    revert_regime: Optional[str] = None
    confidence_decay: float = 0.0
    active_triggers: List[str] = field(default_factory=list)
    reason_trace: List[str] = field(default_factory=list)


class FailSafeEngine:
    """
    Evaluates 4 fail-safe layers in priority order.
    Higher priority overrides lower.
    """

    def evaluate(self, ctx: FailSafeContext) -> FailSafeResult:
        """
        Evaluate all fail-safe layers.

        Args:
            ctx: FailSafeContext with current state

        Returns:
            FailSafeResult with combined actions
        """
        result = FailSafeResult()
        now = datetime.now(timezone.utc)

        # Check if existing fail-safes are still active
        self._check_active_locks(ctx.run_state, result, now)

        # Layer A: Circuit Breakers
        self._check_circuit_breakers(ctx, result, now)

        # Layer B: Shock Mode
        self._check_shock_mode(ctx, result, now)

        # Layer C: Data Integrity Gate
        self._check_data_integrity(ctx, result)

        # Layer D: Auto-Revert
        self._check_auto_revert(ctx, result, now)

        if result.active_triggers:
            logger.warning(
                "FAIL_SAFE_ACTIVE | triggers=%s halt=%s exposure_override=%s lock_flips=%s revert=%s",
                result.active_triggers, result.halt_new_entries,
                result.exposure_override, result.lock_flips, result.revert_regime,
            )

        return result

    def _check_active_locks(
        self, run_state: Dict[str, Any], result: FailSafeResult, now: datetime,
    ) -> None:
        """Check if any existing fail-safe locks are still active."""
        fs = run_state.get("fail_safe_state", {})

        # Circuit breaker
        cb_until = fs.get("circuit_breaker_until")
        if cb_until:
            try:
                cb_ts = datetime.fromisoformat(cb_until)
                if cb_ts.tzinfo is None:
                    cb_ts = cb_ts.replace(tzinfo=timezone.utc)
                if now < cb_ts:
                    result.halt_new_entries = True
                    result.active_triggers.append("CIRCUIT_BREAKER_ACTIVE")
                    result.reason_trace.append(f"Circuit breaker active until {cb_until}")
            except Exception:
                pass

        # Shock mode
        shock_until = fs.get("shock_mode_until")
        if shock_until:
            try:
                shock_ts = datetime.fromisoformat(shock_until)
                if shock_ts.tzinfo is None:
                    shock_ts = shock_ts.replace(tzinfo=timezone.utc)
                if now < shock_ts:
                    result.halt_new_entries = True
                    result.lock_flips = True
                    result.exposure_override = 0.10
                    result.active_triggers.append("SHOCK_MODE_ACTIVE")
                    result.reason_trace.append(f"Shock mode active until {shock_until}")
            except Exception:
                pass

        # Revert lock
        revert_until = fs.get("revert_lock_until")
        if revert_until:
            try:
                revert_ts = datetime.fromisoformat(revert_until)
                if revert_ts.tzinfo is None:
                    revert_ts = revert_ts.replace(tzinfo=timezone.utc)
                if now < revert_ts:
                    result.lock_flips = True
                    result.active_triggers.append("REVERT_LOCK_ACTIVE")
                    result.reason_trace.append(f"Revert lock active until {revert_until}")
            except Exception:
                pass

    def _check_circuit_breakers(
        self, ctx: FailSafeContext, result: FailSafeResult, now: datetime,
    ) -> None:
        """Layer A: Circuit breakers on PnL and consecutive stops."""
        triggered = False
        reasons = []

        # Daily PnL limit
        if ctx.daily_pnl_pct <= CB_DAILY_PNL_LIMIT:
            triggered = True
            reasons.append(f"daily_pnl={ctx.daily_pnl_pct:.4f} <= {CB_DAILY_PNL_LIMIT}")

        # Intraday drawdown
        if ctx.intraday_drawdown_pct <= CB_INTRADAY_DRAWDOWN_LIMIT:
            triggered = True
            reasons.append(
                f"intraday_dd={ctx.intraday_drawdown_pct:.4f} <= {CB_INTRADAY_DRAWDOWN_LIMIT}"
            )

        # Consecutive stops in window
        if ctx.consecutive_stops >= CB_CONSECUTIVE_STOPS:
            recent_stops = self._count_recent_stops(ctx.stop_timestamps, CB_STOP_WINDOW_HOURS)
            if recent_stops >= CB_CONSECUTIVE_STOPS:
                triggered = True
                reasons.append(
                    f"consecutive_stops={recent_stops} >= {CB_CONSECUTIVE_STOPS} in {CB_STOP_WINDOW_HOURS}h"
                )

        if triggered:
            result.halt_new_entries = True
            cooldown_hours = self._compute_cooldown(ctx)
            until = now + timedelta(hours=cooldown_hours)

            result.active_triggers.append("CIRCUIT_BREAKER")
            result.reason_trace.extend(reasons)
            result.reason_trace.append(f"HALT_NEW_ENTRIES for {cooldown_hours}h until {until.isoformat()}")

            # Update run state
            fs = ctx.run_state.setdefault("fail_safe_state", {})
            fs["circuit_breaker_active"] = True
            fs["circuit_breaker_until"] = until.isoformat()

    def _check_shock_mode(
        self, ctx: FailSafeContext, result: FailSafeResult, now: datetime,
    ) -> None:
        """Layer B: Shock mode on extreme drawdown or vol expansion."""
        triggered = False
        reasons = []

        # Extreme drawdown
        if ctx.current_drawdown_pct <= SHOCK_DRAWDOWN_THRESHOLD:
            triggered = True
            reasons.append(f"drawdown={ctx.current_drawdown_pct:.4f} <= {SHOCK_DRAWDOWN_THRESHOLD}")

        # Vol expansion
        if ctx.baseline_vol > 0 and ctx.current_vol > 0:
            vol_ratio = ctx.current_vol / ctx.baseline_vol
            if vol_ratio >= SHOCK_VOL_MULTIPLIER:
                triggered = True
                reasons.append(f"vol_ratio={vol_ratio:.2f} >= {SHOCK_VOL_MULTIPLIER}")

        if triggered:
            result.halt_new_entries = True
            result.lock_flips = True
            result.exposure_override = 0.10
            until = now + timedelta(hours=SHOCK_LOCK_HOURS)

            result.active_triggers.append("SHOCK_MODE")
            result.reason_trace.extend(reasons)

            fs = ctx.run_state.setdefault("fail_safe_state", {})
            fs["shock_mode_active"] = True
            fs["shock_mode_until"] = until.isoformat()

    def _check_data_integrity(
        self, ctx: FailSafeContext, result: FailSafeResult,
    ) -> None:
        """Layer C: Data integrity gate."""
        reasons = []
        decay = 0.0

        if not ctx.data_quality_ok:
            decay += DATA_CONFIDENCE_DECAY
            reasons.append("data_quality_issue")

        if ctx.phase_f_verdict == "INSUFFICIENT_DATA":
            decay += DATA_CONFIDENCE_DECAY
            reasons.append("phase_f_insufficient_data")
            result.lock_flips = True

        if decay > 0:
            result.confidence_decay = decay
            result.active_triggers.append("DATA_INTEGRITY")
            result.reason_trace.extend(reasons)

            # Reduce exposure
            current_override = result.exposure_override
            data_factor = DATA_EXPOSURE_SAFETY_FACTOR
            if current_override is not None:
                result.exposure_override = min(current_override, data_factor)
            else:
                result.exposure_override = data_factor

    def _check_auto_revert(
        self, ctx: FailSafeContext, result: FailSafeResult, now: datetime,
    ) -> None:
        """Layer D: Auto-revert if flip + performance deterioration."""
        if result.lock_flips:
            return  # Already locked by higher priority

        last_flip = ctx.last_flip_timestamp
        if not last_flip:
            return

        try:
            flip_ts = datetime.fromisoformat(last_flip)
            if flip_ts.tzinfo is None:
                flip_ts = flip_ts.replace(tzinfo=timezone.utc)
            hours_since = (now - flip_ts).total_seconds() / 3600.0
        except Exception:
            return

        # Only evaluate within revert window
        if hours_since < REVERT_EVAL_HOURS_MIN or hours_since > REVERT_EVAL_HOURS_MAX:
            return

        # Check if performance deteriorated since flip
        if ctx.pnl_since_flip_pct < -0.01:  # Worse than -1%
            last_stable = ctx.run_state.get("last_stable_regime", "NEUTRAL")
            result.revert_regime = last_stable
            result.lock_flips = True

            until = now + timedelta(hours=REVERT_LOCK_HOURS)
            result.active_triggers.append("AUTO_REVERT")
            result.reason_trace.append(
                f"pnl_since_flip={ctx.pnl_since_flip_pct:.4f} < -1%, "
                f"reverting to {last_stable}, lock {REVERT_LOCK_HOURS}h"
            )

            fs = ctx.run_state.setdefault("fail_safe_state", {})
            fs["revert_lock_active"] = True
            fs["revert_lock_until"] = until.isoformat()

    @staticmethod
    def _count_recent_stops(timestamps: List[str], window_hours: float) -> int:
        """Count stop-losses within the given hour window."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=window_hours)
        count = 0
        for ts_str in timestamps:
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    count += 1
            except Exception:
                continue
        return count

    @staticmethod
    def _compute_cooldown(ctx: FailSafeContext) -> float:
        """Compute adaptive cooldown hours based on severity."""
        severity = 0.0
        if ctx.daily_pnl_pct <= CB_DAILY_PNL_LIMIT:
            severity += abs(ctx.daily_pnl_pct) / abs(CB_DAILY_PNL_LIMIT)
        if ctx.intraday_drawdown_pct <= CB_INTRADAY_DRAWDOWN_LIMIT:
            severity += abs(ctx.intraday_drawdown_pct) / abs(CB_INTRADAY_DRAWDOWN_LIMIT)
        severity = min(severity, 2.0) / 2.0  # Normalize to 0-1

        cooldown = CB_COOLDOWN_HOURS_MIN + severity * (CB_COOLDOWN_HOURS_MAX - CB_COOLDOWN_HOURS_MIN)
        return cooldown
