"""
Phase G Drift Detector (Stage 2): Five-condition AND logic.

Drift is declared ONLY if ALL five conditions hold simultaneously:
1. External confidence delta > 0.25
2. Minimum dwell time satisfied
3. Historical duration anomaly (>= 80th percentile)
4. Volatility regime shift confirmed
5. At least 5 independent external sources used

If ANY condition fails → no drift, no proposal.
This is intentionally conservative.
"""

import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from phase_g_regime.regime_alignment import (
    duration_percentile,
    volatility_shift_detected,
)

logger = logging.getLogger(__name__)

# Thresholds
CONFIDENCE_DELTA_THRESHOLD = 0.25
DURATION_PERCENTILE_THRESHOLD = 80.0
MIN_EXTERNAL_SOURCES = 5

# Dwell time per scope (hours)
MIN_DWELL_HOURS = {
    "crypto": 4.0,
    "swing": 72.0,  # 3 days
}

# Emergency drawdown override (bypasses dwell for crypto)
EMERGENCY_DRAWDOWN_THRESHOLD = -25.0


@dataclass
class DriftCondition:
    name: str
    met: bool
    value: Any
    threshold: Any
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DriftDetectionResult:
    drift_detected: bool
    conditions: List[DriftCondition]
    suggested_regime: Optional[str]
    confidence: float
    emergency_override: bool

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["conditions"] = [c.to_dict() for c in self.conditions]
        return d


class RegimeDriftDetector:
    """
    Stage 2: Detect regime drift using strict 5-condition AND logic.

    Conservative by design — all five conditions must be met.
    Emergency drawdown override available for extreme conditions only.
    """

    def detect(
        self,
        ctx,  # RegimeValidationContext
        validation_scores,  # RegimeValidationScores
        scope_type: str = "crypto",
    ) -> DriftDetectionResult:
        conditions: List[DriftCondition] = []
        emergency = False

        # ====================================================================
        # Condition 1: External confidence delta > 0.25
        # ====================================================================
        phase_f_confidence = self._extract_phase_f_confidence(ctx.phase_f_verdict)
        internal_confidence = ctx.current_regime_confidence
        delta = abs(internal_confidence - phase_f_confidence)

        conditions.append(DriftCondition(
            name="external_confidence_delta",
            met=delta > CONFIDENCE_DELTA_THRESHOLD,
            value=round(delta, 4),
            threshold=CONFIDENCE_DELTA_THRESHOLD,
            reason=f"delta={delta:.3f} {'>' if delta > CONFIDENCE_DELTA_THRESHOLD else '<='} {CONFIDENCE_DELTA_THRESHOLD}",
        ))

        # ====================================================================
        # Condition 2: Minimum dwell satisfied
        # ====================================================================
        min_dwell = MIN_DWELL_HOURS.get(scope_type, 4.0)
        duration = ctx.current_regime_duration_hours
        dwell_met = duration >= min_dwell

        # Emergency drawdown override (crypto only)
        if scope_type == "crypto" and ctx.drawdown < EMERGENCY_DRAWDOWN_THRESHOLD:
            dwell_met = True
            emergency = True
            logger.warning(
                "REGIME_EMERGENCY_OVERRIDE | drawdown=%.2f%% < %.1f%% | "
                "bypassing dwell requirement",
                ctx.drawdown, EMERGENCY_DRAWDOWN_THRESHOLD,
            )

        conditions.append(DriftCondition(
            name="minimum_dwell",
            met=dwell_met,
            value=round(duration, 1),
            threshold=min_dwell,
            reason=(
                f"duration={duration:.1f}h >= {min_dwell}h"
                if dwell_met
                else f"duration={duration:.1f}h < {min_dwell}h"
            ) + (" [EMERGENCY OVERRIDE]" if emergency else ""),
        ))

        # ====================================================================
        # Condition 3: Historical duration anomaly (>= 80th percentile)
        # ====================================================================
        pct = duration_percentile(
            ctx.current_regime_duration_hours,
            ctx.historical_regime_durations,
        )
        duration_anomaly = pct >= DURATION_PERCENTILE_THRESHOLD

        conditions.append(DriftCondition(
            name="duration_anomaly",
            met=duration_anomaly,
            value=round(pct, 1),
            threshold=DURATION_PERCENTILE_THRESHOLD,
            reason=f"percentile={pct:.1f}% {'>' if duration_anomaly else '<='} {DURATION_PERCENTILE_THRESHOLD}%",
        ))

        # ====================================================================
        # Condition 4: Volatility regime shift confirmed
        # ====================================================================
        vol_shifted = volatility_shift_detected(ctx.entry_volatility, ctx.volatility)

        conditions.append(DriftCondition(
            name="volatility_shift",
            met=vol_shifted,
            value={"entry": round(ctx.entry_volatility, 2), "current": round(ctx.volatility, 2)},
            threshold="band change",
            reason=(
                f"vol shifted from {ctx.entry_volatility:.1f}% to {ctx.volatility:.1f}%"
                if vol_shifted
                else f"vol stable at {ctx.volatility:.1f}% (same band as entry {ctx.entry_volatility:.1f}%)"
            ),
        ))

        # ====================================================================
        # Condition 5: At least 5 independent sources (Phase F)
        # ====================================================================
        enough_sources = ctx.num_external_sources >= MIN_EXTERNAL_SOURCES

        conditions.append(DriftCondition(
            name="minimum_sources",
            met=enough_sources,
            value=ctx.num_external_sources,
            threshold=MIN_EXTERNAL_SOURCES,
            reason=f"sources={ctx.num_external_sources} {'>=' if enough_sources else '<'} {MIN_EXTERNAL_SOURCES}",
        ))

        # ====================================================================
        # ALL conditions must be met
        # ====================================================================
        all_met = all(c.met for c in conditions)
        suggested = ctx.recalculated_regime if all_met else None

        # Confidence is based on how many conditions were met + validation drift score
        met_count = sum(1 for c in conditions if c.met)
        confidence = (met_count / len(conditions)) * validation_scores.drift_score if all_met else 0.0

        if all_met:
            logger.info(
                "REGIME_DRIFT_CONFIRMED | all %d conditions met | "
                "suggested=%s | confidence=%.3f | emergency=%s",
                len(conditions), suggested, confidence, emergency,
            )
        else:
            failed = [c.name for c in conditions if not c.met]
            logger.info(
                "REGIME_DRIFT_NOT_CONFIRMED | %d/%d conditions met | "
                "failed=%s",
                met_count, len(conditions), failed,
            )

        return DriftDetectionResult(
            drift_detected=all_met,
            conditions=conditions,
            suggested_regime=suggested,
            confidence=round(confidence, 4),
            emergency_override=emergency,
        )

    def _extract_phase_f_confidence(self, verdict: Optional[Dict]) -> float:
        """Extract regime confidence from Phase F verdict."""
        if not verdict or "verdict" not in verdict:
            return 0.5  # Neutral default
        return float(verdict["verdict"].get("regime_confidence", 0.5))
