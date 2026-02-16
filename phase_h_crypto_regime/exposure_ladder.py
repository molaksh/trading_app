"""
Phase H: Exposure Ladder (Risk Thermostat).

Maps macro regime + confidence to effective exposure cap.

effective_exposure_cap = base_cap * clamp(macro_confidence, 0.35, 0.95)
"""

import logging

from phase_h_crypto_regime.config import (
    EXPOSURE_CAPS,
    CONFIDENCE_CLAMP_LOW,
    CONFIDENCE_CLAMP_HIGH,
)

logger = logging.getLogger(__name__)


class ExposureLadder:
    """Maps macro regime + confidence to exposure cap and position size multiplier."""

    def compute_exposure_cap(self, macro_regime: str, macro_confidence: float) -> float:
        """
        Compute effective exposure cap.

        Args:
            macro_regime: RISK_ON, NEUTRAL, RISK_OFF, PANIC
            macro_confidence: 0.0 - 1.0

        Returns:
            Effective exposure cap (0.0 - 1.0)
        """
        base_cap = EXPOSURE_CAPS.get(macro_regime, EXPOSURE_CAPS["NEUTRAL"])
        clamped_conf = max(CONFIDENCE_CLAMP_LOW, min(CONFIDENCE_CLAMP_HIGH, macro_confidence))
        effective = base_cap * clamped_conf

        logger.debug(
            "EXPOSURE_CAP | regime=%s base=%.2f conf=%.4f clamped=%.4f effective=%.4f",
            macro_regime, base_cap, macro_confidence, clamped_conf, effective,
        )
        return round(effective, 4)

    def compute_position_size_multiplier(self, macro_regime: str) -> float:
        """
        Position size multiplier based on macro regime.

        Returns:
            Multiplier (0.0 - 1.0)
        """
        multipliers = {
            "RISK_ON": 1.0,
            "NEUTRAL": 0.75,
            "RISK_OFF": 0.50,
            "PANIC": 0.25,
        }
        return multipliers.get(macro_regime, 0.50)
