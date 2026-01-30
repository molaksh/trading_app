"""
Live Trading Startup Guardrails.

CRITICAL SAFETY CHECKS before ANY live trade:
- Broker connectivity verified
- Correct environment (LIVE ≠ PAPER)
- Account ID verified
- Buying power > minimum threshold
- Market clock accessible
- Reconciliation passed (no unknown positions)

PHILOSOPHY:
- Fail fast and loud
- Any doubt → BLOCK startup
- Better to delay than trade incorrectly
"""

import logging
import os
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime

from runtime.environment_guard import get_environment_guard, TradingEnvironment

logger = logging.getLogger(__name__)


@dataclass
class StartupValidationResult:
    """Result of startup validation checks."""
    
    passed: bool
    failures: List[str]
    warnings: List[str]
    checks_run: int
    checks_passed: int
    timestamp: str
    
    def is_safe_to_trade(self) -> bool:
        """Check if safe to start trading."""
        return self.passed and len(self.failures) == 0


class LiveTradingGuardrails:
    """
    Startup validation and runtime guardrails for live trading.
    
    CRITICAL: These checks run BEFORE any live trade execution.
    """
    
    def __init__(self, broker_client=None, account_reconciler=None):
        """
        Initialize guardrails.
        
        Args:
            broker_client: Broker API client
            account_reconciler: Account reconciliation system
        """
        self.broker_client = broker_client
        self.account_reconciler = account_reconciler
        self.environment_guard = get_environment_guard()
        
        # Minimum requirements (configurable)
        self.min_buying_power = float(os.getenv("MIN_BUYING_POWER", "1000"))
        self.required_account_id_prefix = os.getenv("LIVE_ACCOUNT_PREFIX", "")
    
    def validate_startup(self) -> StartupValidationResult:
        """
        Run all startup validation checks.
        
        Returns:
            StartupValidationResult with details
            
        Raises:
            Exception: If validation fails catastrophically
        """
        logger.info("=" * 80)
        logger.info("LIVE TRADING STARTUP VALIDATION")
        logger.info("=" * 80)
        
        failures = []
        warnings = []
        checks_run = 0
        checks_passed = 0
        
        # Check 1: Environment validation
        checks_run += 1
        try:
            if not self.environment_guard.is_live():
                failures.append("ENV must be 'live' for live trading")
            else:
                checks_passed += 1
                logger.info("✓ Environment: LIVE")
        except Exception as e:
            failures.append(f"Environment check failed: {e}")
        
        # Check 2: Broker connectivity
        checks_run += 1
        if self._check_broker_connectivity():
            checks_passed += 1
            logger.info("✓ Broker connectivity verified")
        else:
            failures.append("Broker connectivity failed")
        
        # Check 3: Account validation
        checks_run += 1
        account_check = self._check_account_validity()
        if account_check["valid"]:
            checks_passed += 1
            logger.info(f"✓ Account validated: {account_check.get('account_id', 'N/A')}")
        else:
            failures.append(f"Account validation failed: {account_check.get('reason', 'Unknown')}")
        
        # Check 4: Buying power
        checks_run += 1
        buying_power_check = self._check_buying_power()
        if buying_power_check["sufficient"]:
            checks_passed += 1
            logger.info(f"✓ Buying power sufficient: ${buying_power_check['amount']:.2f}")
        else:
            failures.append(
                f"Insufficient buying power: ${buying_power_check['amount']:.2f} "
                f"< ${self.min_buying_power:.2f}"
            )
        
        # Check 5: Market clock sanity
        checks_run += 1
        if self._check_market_clock():
            checks_passed += 1
            logger.info("✓ Market clock accessible")
        else:
            failures.append("Market clock check failed")
        
        # Check 6: Reconciliation
        checks_run += 1
        recon_check = self._check_reconciliation()
        if recon_check["passed"]:
            checks_passed += 1
            logger.info("✓ Account reconciliation passed")
            if recon_check.get("warnings"):
                warnings.extend(recon_check["warnings"])
        else:
            failures.append(f"Reconciliation failed: {recon_check.get('reason', 'Unknown')}")
        
        # Summary
        passed = len(failures) == 0
        
        result = StartupValidationResult(
            passed=passed,
            failures=failures,
            warnings=warnings,
            checks_run=checks_run,
            checks_passed=checks_passed,
            timestamp=datetime.now().isoformat(),
        )
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"VALIDATION RESULT: {'PASSED ✓' if passed else 'FAILED ✗'}")
        logger.info(f"Checks: {checks_passed}/{checks_run} passed")
        
        if failures:
            logger.error("FAILURES:")
            for failure in failures:
                logger.error(f"  ✗ {failure}")
        
        if warnings:
            logger.warning("WARNINGS:")
            for warning in warnings:
                logger.warning(f"  ⚠ {warning}")
        
        logger.info("=" * 80)
        
        if not passed:
            logger.error("STARTUP VALIDATION FAILED - REFUSING TO START LIVE TRADING")
            raise RuntimeError(
                f"Live trading startup validation failed: {len(failures)} check(s) failed. "
                f"Review logs for details."
            )
        
        return result
    
    def _check_broker_connectivity(self) -> bool:
        """Check broker API connectivity."""
        if not self.broker_client:
            logger.warning("No broker client provided")
            return False
        
        try:
            # Try to get account info as connectivity test
            account = self.broker_client.get_account()
            return account is not None
        except Exception as e:
            logger.error(f"Broker connectivity check failed: {e}")
            return False
    
    def _check_account_validity(self) -> Dict:
        """Validate account ID and status."""
        if not self.broker_client:
            return {"valid": False, "reason": "No broker client"}
        
        try:
            account = self.broker_client.get_account()
            account_id = getattr(account, "account_number", "UNKNOWN")
            
            # Check account ID prefix (if configured)
            if self.required_account_id_prefix:
                if not account_id.startswith(self.required_account_id_prefix):
                    return {
                        "valid": False,
                        "reason": f"Account ID '{account_id}' doesn't match expected prefix '{self.required_account_id_prefix}'"
                    }
            
            # Check account status
            status = getattr(account, "status", "UNKNOWN")
            if status != "ACTIVE":
                return {
                    "valid": False,
                    "reason": f"Account status is '{status}' (expected ACTIVE)"
                }
            
            return {"valid": True, "account_id": account_id}
        except Exception as e:
            return {"valid": False, "reason": str(e)}
    
    def _check_buying_power(self) -> Dict:
        """Check buying power meets minimum threshold."""
        if not self.broker_client:
            return {"sufficient": False, "amount": 0}
        
        try:
            account = self.broker_client.get_account()
            buying_power = float(getattr(account, "buying_power", 0))
            
            return {
                "sufficient": buying_power >= self.min_buying_power,
                "amount": buying_power,
            }
        except Exception as e:
            logger.error(f"Buying power check failed: {e}")
            return {"sufficient": False, "amount": 0}
    
    def _check_market_clock(self) -> bool:
        """Check that market clock is accessible."""
        if not self.broker_client:
            return False
        
        try:
            clock = self.broker_client.get_clock()
            return clock is not None
        except Exception as e:
            logger.error(f"Market clock check failed: {e}")
            return False
    
    def _check_reconciliation(self) -> Dict:
        """Check account reconciliation status."""
        if not self.account_reconciler:
            return {"passed": False, "reason": "No reconciler provided"}
        
        try:
            # Run reconciliation
            result = self.account_reconciler.reconcile()
            
            # Check for unknown positions
            if result.get("status") != "READY":
                return {
                    "passed": False,
                    "reason": f"Reconciliation status: {result.get('status')}"
                }
            
            # Check for safe mode
            if result.get("safe_mode"):
                return {
                    "passed": False,
                    "reason": "Account in SAFE MODE"
                }
            
            # Check for external positions
            warnings = []
            if result.get("external_positions_count", 0) > 0:
                warnings.append(
                    f"{result['external_positions_count']} external positions detected "
                    "(will block duplicate BUY orders)"
                )
            
            return {
                "passed": True,
                "warnings": warnings,
            }
        except Exception as e:
            logger.error(f"Reconciliation check failed: {e}")
            return {"passed": False, "reason": str(e)}


class KillSwitch:
    """
    Emergency kill switch for live trading.
    
    Can be triggered automatically or manually to halt all trading.
    """
    
    def __init__(self):
        """Initialize kill switch."""
        self._is_active = False
        self._trigger_reason = None
        self._trigger_timestamp = None
    
    def activate(self, reason: str, automatic: bool = False) -> None:
        """
        Activate kill switch (halt all trading).
        
        Args:
            reason: Reason for activation
            automatic: True if auto-triggered, False if manual
        """
        self._is_active = True
        self._trigger_reason = reason
        self._trigger_timestamp = datetime.now().isoformat()
        
        trigger_type = "AUTOMATIC" if automatic else "MANUAL"
        
        logger.error("=" * 80)
        logger.error(f"🚨 KILL SWITCH ACTIVATED ({trigger_type})")
        logger.error("=" * 80)
        logger.error(f"Reason: {reason}")
        logger.error(f"Time: {self._trigger_timestamp}")
        logger.error("ALL TRADING HALTED")
        logger.error("=" * 80)
    
    def deactivate(self) -> None:
        """Deactivate kill switch (resume trading)."""
        if self._is_active:
            logger.info("Kill switch deactivated - trading resumed")
            self._is_active = False
            self._trigger_reason = None
            self._trigger_timestamp = None
    
    def is_active(self) -> bool:
        """Check if kill switch is active."""
        return self._is_active
    
    def get_status(self) -> Dict:
        """Get kill switch status."""
        return {
            "active": self._is_active,
            "reason": self._trigger_reason,
            "timestamp": self._trigger_timestamp,
        }


# Global kill switch instance
_kill_switch: Optional[KillSwitch] = None


def get_kill_switch() -> KillSwitch:
    """Get global kill switch instance."""
    global _kill_switch
    if _kill_switch is None:
        _kill_switch = KillSwitch()
    return _kill_switch
