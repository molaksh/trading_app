"""
Environment Guard - Hard blockers for live trading safety.

CRITICAL SAFETY RULES:
- Live containers NEVER train ML
- Live containers NEVER modify ML models
- Environment must match expectations
- Ambiguity → HARD ERROR + HALT

This module enforces the separation between paper (learning) and live (execution).
"""

import logging
import os
import sys
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class TradingEnvironment(Enum):
    """Trading environment types."""
    PAPER = "paper"
    LIVE = "live"


class EnvironmentViolationError(Exception):
    """
    Raised when environment safety rules are violated.
    
    This is a FATAL error that should halt the container.
    """
    pass


class EnvironmentGuard:
    """
    Enforce environment-specific safety rules.
    
    Primary responsibility: Prevent ML training in live containers.
    """
    
    def __init__(self):
        """Initialize guard and validate environment."""
        self.environment = self._detect_environment()
        logger.info(f"EnvironmentGuard initialized: ENV={self.environment.value}")
    
    def _detect_environment(self) -> TradingEnvironment:
        """
        Detect current trading environment.
        
        Returns:
            TradingEnvironment enum
            
        Raises:
            EnvironmentViolationError: If environment ambiguous or invalid
        """
        env_str = os.getenv("ENV", "").strip().lower()
        
        if not env_str:
            raise EnvironmentViolationError(
                "ENV environment variable not set. "
                "Must be explicitly 'paper' or 'live'. "
                "HALTING for safety."
            )
        
        if env_str == "paper":
            return TradingEnvironment.PAPER
        elif env_str == "live":
            return TradingEnvironment.LIVE
        else:
            raise EnvironmentViolationError(
                f"Invalid ENV='{env_str}'. Must be 'paper' or 'live'. "
                f"HALTING for safety."
            )
    
    def assert_paper_only(self, action: str) -> None:
        """
        Assert that action is only allowed in paper environment.
        
        Used to block ML training, experimentation, and model modification in live.
        
        Args:
            action: Description of action being attempted
            
        Raises:
            EnvironmentViolationError: If called from live environment
        """
        if self.environment == TradingEnvironment.LIVE:
            error_msg = (
                f"CRITICAL SAFETY VIOLATION: {action} attempted in LIVE environment.\n"
                f"ML training/modification is FORBIDDEN in live containers.\n"
                f"This action is only allowed in paper containers.\n"
                f"HALTING immediately for safety."
            )
            logger.error("=" * 80)
            logger.error(error_msg)
            logger.error("=" * 80)
            raise EnvironmentViolationError(error_msg)
        
        logger.info(f"✓ Environment check passed for: {action} (ENV={self.environment.value})")
    
    def assert_live_only(self, action: str) -> None:
        """
        Assert that action is only allowed in live environment.
        
        Args:
            action: Description of action being attempted
            
        Raises:
            EnvironmentViolationError: If called from paper environment
        """
        if self.environment == TradingEnvironment.PAPER:
            error_msg = (
                f"SAFETY CHECK: {action} attempted in PAPER environment.\n"
                f"This action is intended for live containers only.\n"
                f"Blocking to prevent confusion."
            )
            logger.warning(error_msg)
            raise EnvironmentViolationError(error_msg)
        
        logger.info(f"✓ Environment check passed for: {action} (ENV={self.environment.value})")
    
    def is_paper(self) -> bool:
        """Check if running in paper environment."""
        return self.environment == TradingEnvironment.PAPER
    
    def is_live(self) -> bool:
        """Check if running in live environment."""
        return self.environment == TradingEnvironment.LIVE
    
    def validate_account_id(self, expected_prefix: Optional[str] = None) -> None:
        """
        Validate account ID matches environment.
        
        Args:
            expected_prefix: Optional expected prefix (e.g., 'PA' for paper)
            
        Raises:
            EnvironmentViolationError: If account doesn't match environment
        """
        # This will be enhanced when we add broker integration
        # For now, just log
        logger.info(f"Account validation placeholder (ENV={self.environment.value})")


# Global singleton instance
_guard_instance: Optional[EnvironmentGuard] = None


def get_environment_guard() -> EnvironmentGuard:
    """
    Get global EnvironmentGuard instance.
    
    Initializes on first call and validates environment.
    """
    global _guard_instance
    if _guard_instance is None:
        _guard_instance = EnvironmentGuard()
    return _guard_instance


def block_ml_training_in_live() -> None:
    """
    Hard blocker for ML training in live containers.
    
    Call this at the entry point of any ML training function.
    
    Raises:
        EnvironmentViolationError: If called from live environment
    """
    guard = get_environment_guard()
    guard.assert_paper_only("ML training")
