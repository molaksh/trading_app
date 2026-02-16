"""
Phase H: Drift Scoring.

Computes drift score to determine if a regime flip is warranted:

drift_score = 0.40 * macro_shift_strength
            + 0.30 * external_confidence_delta
            + 0.20 * volatility_expansion
            + 0.10 * historical_duration_anomaly

Flip candidate if drift_score >= DRIFT_FLIP_THRESHOLD (0.75).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from phase_h_crypto_regime.config import DRIFT_FLIP_THRESHOLD

logger = logging.getLogger(__name__)


@dataclass
class DriftResult:
    """Result of drift assessment."""
    drift_score: float          # 0.0 - 1.0
    is_flip_candidate: bool
    components: Dict[str, float] = field(default_factory=dict)
    reason: str = ""


class DriftScorer:
    """Computes drift score from macro shift, external confidence, vol, and duration."""

    WEIGHTS = {
        "macro_shift_strength": 0.40,
        "external_confidence_delta": 0.30,
        "volatility_expansion": 0.20,
        "historical_duration_anomaly": 0.10,
    }

    def compute_drift(
        self,
        current_regime: str,
        new_macro_result,
        run_state: Dict[str, Any],
        phase_f_confidence: Optional[float] = None,
    ) -> DriftResult:
        """
        Compute drift score between current regime and new macro result.

        Args:
            current_regime: Current active regime string
            new_macro_result: CompositeMacroResult from this cycle
            run_state: Persisted run state with history
            phase_f_confidence: Optional Phase F verdict confidence

        Returns:
            DriftResult
        """
        components = {}

        # Component 1: Macro shift strength
        components["macro_shift_strength"] = self._macro_shift(
            current_regime, new_macro_result.macro_regime, new_macro_result.macro_score,
        )

        # Component 2: External confidence delta
        components["external_confidence_delta"] = self._external_delta(
            new_macro_result.macro_confidence, phase_f_confidence,
        )

        # Component 3: Volatility expansion
        vol_score = new_macro_result.component_scores.get("volatility_expansion", 0.5)
        # Invert: high vol expansion (low score from macro) = high drift signal
        components["volatility_expansion"] = 1.0 - vol_score

        # Component 4: Historical duration anomaly
        components["historical_duration_anomaly"] = self._duration_anomaly(run_state)

        # Weighted sum
        drift_score = sum(
            self.WEIGHTS[k] * components[k] for k in self.WEIGHTS
        )
        drift_score = max(0.0, min(1.0, drift_score))

        is_flip_candidate = drift_score >= DRIFT_FLIP_THRESHOLD
        reason = (
            f"drift={drift_score:.3f} threshold={DRIFT_FLIP_THRESHOLD} "
            f"current={current_regime} proposed={new_macro_result.macro_regime}"
        )

        return DriftResult(
            drift_score=round(drift_score, 4),
            is_flip_candidate=is_flip_candidate,
            components={k: round(v, 4) for k, v in components.items()},
            reason=reason,
        )

    def _macro_shift(self, current: str, proposed: str, macro_score: float) -> float:
        """Strength of the regime shift (0-1)."""
        if current == proposed:
            return 0.0

        # Distance between regimes
        regime_order = {"RISK_ON": 3, "NEUTRAL": 2, "RISK_OFF": 1, "PANIC": 0}
        current_val = regime_order.get(current, 2)
        proposed_val = regime_order.get(proposed, 2)
        distance = abs(current_val - proposed_val) / 3.0

        return min(1.0, distance)

    def _external_delta(
        self, macro_confidence: float, phase_f_confidence: Optional[float],
    ) -> float:
        """Delta between internal and external confidence."""
        if phase_f_confidence is None:
            return 0.3  # moderate default when no external data

        delta = abs(macro_confidence - phase_f_confidence)
        # Normalize: 0.0-0.5 delta -> 0-1
        return min(1.0, delta * 2.0)

    def _duration_anomaly(self, run_state: Dict[str, Any]) -> float:
        """How long current regime has persisted vs expected."""
        regime_since = run_state.get("current_regime_since")
        if not regime_since:
            return 0.0

        try:
            since = datetime.fromisoformat(regime_since)
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            hours = (now - since).total_seconds() / 3600.0
        except Exception:
            return 0.0

        # Past transitions for duration percentile
        transitions = run_state.get("regime_transitions", [])
        durations = []
        for t in transitions:
            d = t.get("duration_hours")
            if d is not None:
                durations.append(d)

        if not durations or len(durations) < 3:
            # Not enough history; use simple threshold
            return min(1.0, hours / 48.0)

        # Percentile of current duration
        count_below = sum(1 for d in durations if d < hours)
        percentile = count_below / len(durations)

        # If >= 80th percentile, full anomaly signal
        if percentile >= 0.80:
            return 1.0
        return percentile
