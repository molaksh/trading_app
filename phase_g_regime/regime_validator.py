"""
Phase G Regime Validator (Stage 1): Computes 4 validation scores.

Inputs:
  - Current internal regime + confidence
  - Recalculated regime from fresh data
  - Phase F verdict
  - Cross-asset regime (SPY or ETH peer)
  - Volatility / drawdown metrics
  - Historical regime durations

Outputs:
  - Internal Regime Score (0-1)
  - External Confidence Score (0-1)
  - Regime Drift Score (0-1)
  - Cross-Asset Alignment Score (0-1)
  - Verdict: REGIME_VALIDATED | REGIME_INSUFFICIENT_DATA |
             REGIME_UNCERTAIN | REGIME_DRIFT_DETECTED
"""

import time
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from phase_g_regime.regime_alignment import (
    regime_agreement_score,
    duration_percentile,
    volatility_shift_detected,
)

logger = logging.getLogger(__name__)


@dataclass
class RegimeValidationContext:
    """All inputs needed for a regime validation cycle."""
    scope: str
    current_regime: Optional[str]
    current_regime_confidence: float
    recalculated_regime: Optional[str]
    recalculated_confidence: float
    phase_f_verdict: Optional[Dict[str, Any]]
    cross_asset_regime: Optional[str]
    volatility: float
    volatility_percentile: float
    drawdown: float
    current_regime_duration_hours: float
    historical_regime_durations: List[float]
    num_external_sources: int
    entry_volatility: float


@dataclass
class RegimeValidationScores:
    """Four validation dimension scores, each 0-1."""
    internal_score: float
    external_score: float
    drift_score: float
    cross_asset_score: float

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class RegimeValidationResult:
    """Output of a validation cycle."""
    run_id: str
    timestamp_utc: str
    scope: str
    current_regime: Optional[str]
    recalculated_regime: Optional[str]
    scores: RegimeValidationScores
    verdict: str
    evidence: Dict[str, Any]
    duration_ms: float

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


class RegimeValidator:
    """
    Stage 1: Compute four validation scores and determine verdict.

    Conservative by design — defaults to REGIME_VALIDATED when uncertain.
    """

    def validate(
        self, ctx: RegimeValidationContext, run_id: str
    ) -> RegimeValidationResult:
        start = time.time()

        # Insufficient data guard
        if ctx.current_regime is None and ctx.recalculated_regime is None:
            return self._build_result(
                run_id, ctx,
                scores=RegimeValidationScores(0.5, 0.5, 0.0, 0.5),
                verdict="REGIME_INSUFFICIENT_DATA",
                evidence={"reason": "no regime data available"},
                start_time=start,
            )

        if ctx.recalculated_regime is None:
            return self._build_result(
                run_id, ctx,
                scores=RegimeValidationScores(0.5, 0.5, 0.0, 0.5),
                verdict="REGIME_INSUFFICIENT_DATA",
                evidence={"reason": "could not recalculate regime from data"},
                start_time=start,
            )

        # Score 1: Internal regime agreement
        internal = regime_agreement_score(ctx.current_regime, ctx.recalculated_regime)

        # Score 2: External confidence
        external = self._compute_external_score(ctx)

        # Score 3: Drift
        drift = self._compute_drift_score(ctx)

        # Score 4: Cross-asset alignment
        cross_asset = self._compute_cross_asset_score(ctx)

        scores = RegimeValidationScores(
            internal_score=round(internal, 4),
            external_score=round(external, 4),
            drift_score=round(drift, 4),
            cross_asset_score=round(cross_asset, 4),
        )

        # Determine verdict
        verdict = self._determine_verdict(scores, ctx)

        evidence = {
            "current_regime": ctx.current_regime,
            "recalculated_regime": ctx.recalculated_regime,
            "cross_asset_regime": ctx.cross_asset_regime,
            "volatility": round(ctx.volatility, 2),
            "drawdown": round(ctx.drawdown, 2),
            "duration_hours": round(ctx.current_regime_duration_hours, 1),
            "num_external_sources": ctx.num_external_sources,
            "phase_f_verdict_type": self._get_verdict_type(ctx.phase_f_verdict),
        }

        return self._build_result(
            run_id, ctx, scores, verdict, evidence, start,
        )

    # ========================================================================
    # Score computations
    # ========================================================================

    def _compute_external_score(self, ctx: RegimeValidationContext) -> float:
        """Phase F verdict confidence mapped to 0-1."""
        if not ctx.phase_f_verdict or "verdict" not in ctx.phase_f_verdict:
            return 0.5  # Neutral when no verdict available

        v = ctx.phase_f_verdict["verdict"]
        verdict_type = v.get("verdict", "")
        regime_confidence = float(v.get("regime_confidence", 0.5))

        # Base from verdict type
        base_map = {
            "REGIME_VALIDATED": 0.85,
            "POSSIBLE_STRUCTURAL_SHIFT_OBSERVE": 0.50,
            "REGIME_QUESTIONABLE": 0.30,
            "HIGH_NOISE_NO_ACTION": 0.20,
        }
        base = base_map.get(verdict_type, 0.5)

        # Blend with reported confidence
        score = base * 0.6 + regime_confidence * 0.4
        return min(1.0, max(0.0, score))

    def _compute_drift_score(self, ctx: RegimeValidationContext) -> float:
        """
        Composite drift signal (0-1). Higher = more evidence of drift.

        Components:
        - Regime disagreement (internal vs recalculated)
        - Duration anomaly (current duration vs historical)
        - Volatility shift since regime entry
        """
        components = []

        # Regime disagreement
        agreement = regime_agreement_score(ctx.current_regime, ctx.recalculated_regime)
        disagreement = 1.0 - agreement
        components.append(disagreement * 0.5)

        # Duration anomaly
        pct = duration_percentile(
            ctx.current_regime_duration_hours,
            ctx.historical_regime_durations,
        )
        duration_anomaly = max(0.0, (pct - 50.0) / 50.0)  # 0 at 50th, 1 at 100th
        components.append(duration_anomaly * 0.3)

        # Volatility shift
        vol_shifted = volatility_shift_detected(ctx.entry_volatility, ctx.volatility)
        components.append((1.0 if vol_shifted else 0.0) * 0.2)

        return min(1.0, sum(components))

    def _compute_cross_asset_score(self, ctx: RegimeValidationContext) -> float:
        """Agreement between internal regime and cross-asset regime."""
        if ctx.cross_asset_regime is None:
            return 0.5  # Neutral when unavailable
        return regime_agreement_score(ctx.current_regime, ctx.cross_asset_regime)

    # ========================================================================
    # Verdict logic
    # ========================================================================

    def _determine_verdict(
        self, scores: RegimeValidationScores, ctx: RegimeValidationContext
    ) -> str:
        """
        Conservative verdict determination.
        Drift only declared when internal score is low AND drift score is high.
        """
        # Strong agreement, low drift → validated
        if scores.internal_score >= 0.6 and scores.drift_score < 0.4:
            return "REGIME_VALIDATED"

        # Clear disagreement with high drift evidence
        if scores.internal_score < 0.5 and scores.drift_score >= 0.5:
            return "REGIME_DRIFT_DETECTED"

        # Everything else is uncertain
        return "REGIME_UNCERTAIN"

    # ========================================================================
    # Helpers
    # ========================================================================

    def _get_verdict_type(self, verdict: Optional[Dict]) -> Optional[str]:
        if verdict and "verdict" in verdict:
            return verdict["verdict"].get("verdict")
        return None

    def _build_result(
        self, run_id, ctx, scores, verdict, evidence=None, start_time=None,
    ) -> RegimeValidationResult:
        duration_ms = (time.time() - start_time) * 1000 if start_time else 0.0
        return RegimeValidationResult(
            run_id=run_id,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            scope=ctx.scope,
            current_regime=ctx.current_regime,
            recalculated_regime=ctx.recalculated_regime,
            scores=scores,
            verdict=verdict,
            evidence=evidence or {},
            duration_ms=round(duration_ms, 1),
        )
