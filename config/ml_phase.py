"""
ML Learning Phase Configuration.

Defines how ML training uses paper vs live data.

CRITICAL RULES:
- Phases are MANUALLY configured via ML_LEARNING_PHASE env var
- Phase changes require PAPER container restart
- LIVE container is phase-unaware (only loads frozen models)
- Auto-promotion is FORBIDDEN
"""

import logging
import os
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class MLLearningPhase(Enum):
    """
    ML learning phases control data source mixing for training.
    
    All training happens in PAPER container only.
    """
    
    PHASE_1 = "PHASE_1"  # Early live: paper ledger only
    PHASE_2 = "PHASE_2"  # Stable live: paper primary + tagged live (low weight)
    PHASE_3 = "PHASE_3"  # Mature: paper primary + live constraints
    
    @classmethod
    def from_string(cls, phase_str: str) -> "MLLearningPhase":
        """
        Parse phase from string.
        
        Args:
            phase_str: Phase string (e.g., "PHASE_1")
            
        Returns:
            MLLearningPhase enum
            
        Raises:
            ValueError: If invalid phase string
        """
        phase_str = phase_str.strip().upper()
        try:
            return cls[phase_str]
        except KeyError:
            valid_phases = [p.value for p in cls]
            raise ValueError(
                f"Invalid ML_LEARNING_PHASE: '{phase_str}'. "
                f"Must be one of: {valid_phases}"
            )


class MLPhaseConfig:
    """
    ML learning phase configuration and validation.
    
    Only applies to PAPER containers (where training happens).
    LIVE containers are phase-unaware.
    """
    
    def __init__(self):
        """
        Initialize phase config from environment.
        
        Reads ML_LEARNING_PHASE env var.
        Defaults to PHASE_1 if not set (safest option).
        """
        self.phase = self._load_phase()
        self._log_phase_config()
    
    def _load_phase(self) -> MLLearningPhase:
        """
        Load phase from environment variable.
        
        Returns:
            MLLearningPhase enum
        """
        phase_str = os.getenv("ML_LEARNING_PHASE", "PHASE_1").strip()
        
        try:
            phase = MLLearningPhase.from_string(phase_str)
            logger.info(f"ML_LEARNING_PHASE loaded: {phase.value}")
            return phase
        except ValueError as e:
            logger.warning(
                f"{e}\n"
                f"Defaulting to PHASE_1 for safety."
            )
            return MLLearningPhase.PHASE_1
    
    def _log_phase_config(self) -> None:
        """Log current phase configuration and training rules."""
        logger.info("=" * 80)
        logger.info("ML LEARNING PHASE CONFIGURATION")
        logger.info("=" * 80)
        logger.info(f"Current Phase: {self.phase.value}")
        logger.info("")
        
        if self.phase == MLLearningPhase.PHASE_1:
            logger.info("PHASE_1 — EARLY LIVE")
            logger.info("  Training Data:")
            logger.info("    ✓ Paper ledger: PRIMARY (100% weight)")
            logger.info("    ✗ Live ledger: EXCLUDED from training")
            logger.info("  Live Data Usage:")
            logger.info("    → Evaluation only (validate model on live executions)")
            logger.info("    → Stored but not used for training")
            logger.info("  Rationale:")
            logger.info("    → Live execution artifacts (slippage, fills) not yet understood")
            logger.info("    → Learn from clean paper data first")
        
        elif self.phase == MLLearningPhase.PHASE_2:
            logger.info("PHASE_2 — STABLE LIVE")
            logger.info("  Training Data:")
            logger.info("    ✓ Paper ledger: PRIMARY (70-80% weight)")
            logger.info("    ✓ Live ledger: SECONDARY (20-30% weight, tagged)")
            logger.info("  Live Data Usage:")
            logger.info("    → Used for realism calibration")
            logger.info("    → Lower weight to prevent execution artifact bias")
            logger.info("  Rationale:")
            logger.info("    → Live execution is stable and understood")
            logger.info("    → Incorporate real execution patterns carefully")
        
        elif self.phase == MLLearningPhase.PHASE_3:
            logger.info("PHASE_3 — MATURE SYSTEM")
            logger.info("  Training Data:")
            logger.info("    ✓ Paper ledger: ALWAYS PRIMARY (never dominated)")
            logger.info("    ✓ Live ledger: CONSTRAINTS & REFINEMENT")
            logger.info("  Live Data Usage:")
            logger.info("    → Refine execution assumptions")
            logger.info("    → Constrain models with live performance bounds")
            logger.info("    → Paper data prevents overfitting to live artifacts")
            logger.info("  Rationale:")
            logger.info("    → System mature with extensive live history")
            logger.info("    → Live data improves realism without sacrificing robustness")
        
        logger.info("")
        logger.info("IMPORTANT:")
        logger.info("  ⚠ Phase changes require MANUAL config update + container restart")
        logger.info("  ⚠ No auto-promotion (system may recommend, human decides)")
        logger.info("  ⚠ This config ONLY affects PAPER container (where training runs)")
        logger.info("=" * 80)
    
    def get_phase(self) -> MLLearningPhase:
        """Get current learning phase."""
        return self.phase
    
    def is_phase_1(self) -> bool:
        """Check if in PHASE_1 (paper only)."""
        return self.phase == MLLearningPhase.PHASE_1
    
    def is_phase_2(self) -> bool:
        """Check if in PHASE_2 (paper primary + live secondary)."""
        return self.phase == MLLearningPhase.PHASE_2
    
    def is_phase_3(self) -> bool:
        """Check if in PHASE_3 (mature system)."""
        return self.phase == MLLearningPhase.PHASE_3
    
    def validate_environment_compatibility(self) -> None:
        """
        Validate that ML phase config is being used correctly.
        
        Phases only apply to PAPER containers.
        Warns if accessed from LIVE container (should never happen).
        """
        from runtime.environment_guard import get_environment_guard
        guard = get_environment_guard()
        
        if guard.is_live():
            logger.warning(
                "ML_LEARNING_PHASE accessed from LIVE container. "
                "This is unexpected - phases only apply to paper training. "
                "Live containers should only load frozen models."
            )


# Global singleton
_phase_config: Optional[MLPhaseConfig] = None


def get_ml_phase_config() -> MLPhaseConfig:
    """
    Get global ML phase configuration.
    
    Initializes on first call.
    Only relevant in PAPER containers where training happens.
    """
    global _phase_config
    if _phase_config is None:
        _phase_config = MLPhaseConfig()
    return _phase_config
