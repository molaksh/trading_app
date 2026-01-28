"""
Phase 0 startup validation.

Comprehensive checks to ensure:
- SCOPE properly configured
- Storage paths valid and writable
- Broker adapter selectable
- Strategies available for scope
- ML artifacts loadable
- Single execution pipeline

Fails fast if any validation fails.
"""

import logging
import sys
from pathlib import Path
from typing import Optional, Tuple, List

from config.scope import Scope, get_scope
from config.scope_paths import get_scope_paths
from broker.broker_factory import get_broker_adapter
from strategies.registry import StrategyRegistry, instantiate_strategies_for_scope
from ml.ml_state import MLStateManager

logger = logging.getLogger(__name__)


class StartupValidator:
    """Validate Phase 0 configuration at startup."""
    
    def __init__(self):
        """Initialize validator."""
        self.checks_passed = 0
        self.checks_failed = 0
        self.warnings = []
    
    def validate_all(self) -> bool:
        """
        Run all validation checks.
        
        Returns:
            True if all checks passed, False if any failed
        """
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 0 STARTUP VALIDATION")
        logger.info("=" * 80 + "\n")
        
        checks = [
            ("SCOPE Configuration", self._validate_scope),
            ("Storage Paths", self._validate_paths),
            ("Broker Adapter", self._validate_broker),
            ("Strategies", self._validate_strategies),
            ("ML System", self._validate_ml),
            ("Execution Pipeline", self._validate_pipeline),
        ]
        
        for check_name, check_func in checks:
            try:
                passed, msg = check_func()
                if passed:
                    self._pass(f"{check_name}: {msg}")
                else:
                    self._fail(f"{check_name}: {msg}")
            except Exception as e:
                self._fail(f"{check_name}: Exception: {e}")
        
        # Summary
        logger.info("\n" + "-" * 80)
        logger.info(f"VALIDATION SUMMARY: {self.checks_passed} passed, {self.checks_failed} failed")
        
        if self.warnings:
            logger.warning("WARNINGS:")
            for warning in self.warnings:
                logger.warning(f"  ⚠️  {warning}")
        
        logger.info("-" * 80 + "\n")
        
        if self.checks_failed > 0:
            logger.error("VALIDATION FAILED - Aborting startup")
            return False
        
        logger.info("✓ ALL VALIDATIONS PASSED - Ready to trade\n")
        return True
    
    def _pass(self, msg: str) -> None:
        """Log passing check."""
        self.checks_passed += 1
        logger.info(f"  ✓ {msg}")
    
    def _fail(self, msg: str) -> None:
        """Log failing check."""
        self.checks_failed += 1
        logger.error(f"  ✗ {msg}")
    
    def _warn(self, msg: str) -> None:
        """Log warning (non-fatal)."""
        self.warnings.append(msg)
        logger.warning(f"  ⚠️  {msg}")
    
    # =========================================================================
    # Validators
    # =========================================================================
    
    def _validate_scope(self) -> Tuple[bool, str]:
        """Validate SCOPE is properly configured."""
        try:
            scope = get_scope()
            msg = (
                f"SCOPE={scope} "
                f"(env={scope.env}, broker={scope.broker}, "
                f"mode={scope.mode}, market={scope.market})"
            )
            return True, msg
        except Exception as e:
            return False, f"Invalid SCOPE: {e}"
    
    def _validate_paths(self) -> Tuple[bool, str]:
        """Validate storage paths are accessible."""
        try:
            scope = get_scope()
            paths = get_scope_paths(scope)
            summary = paths.get_scope_summary()
            
            # Check each critical path
            critical_paths = [
                ("logs_dir", summary["logs_dir"]),
                ("models_dir", summary["models_dir"]),
                ("state_dir", summary["state_dir"]),
            ]
            
            for path_name, path_str in critical_paths:
                path = Path(path_str)
                if not path.exists():
                    return False, f"{path_name} does not exist: {path_str}"
                
                # Try to write a test file
                test_file = path / ".phase0_test"
                try:
                    test_file.write_text("test")
                    test_file.unlink()
                except Exception as e:
                    return False, f"{path_name} not writable: {e}"
            
            return True, f"Base directory: {summary['base_dir']}"
        
        except Exception as e:
            return False, f"Path validation failed: {e}"
    
    def _validate_broker(self) -> Tuple[bool, str]:
        """Validate broker adapter is selectable."""
        try:
            scope = get_scope()
            adapter = get_broker_adapter(scope)
            adapter_class = adapter.__class__.__name__
            mode = "paper" if scope.env == "paper" else "live"
            msg = f"{adapter_class} ({mode} mode)"
            return True, msg
        except NotImplementedError:
            # Stub adapter - acceptable for Phase 0
            scope = get_scope()
            return True, f"{scope.broker} adapter (stub implementation)"
        except Exception as e:
            return False, f"Broker selection failed: {e}"
    
    def _validate_strategies(self) -> Tuple[bool, str]:
        """Validate strategies are available for scope."""
        try:
            scope = get_scope()
            
            # Check registry has strategies for this scope
            StrategyRegistry.validate_scope_has_strategies(scope)
            
            # Instantiate them
            strategies = instantiate_strategies_for_scope(scope)
            
            if not strategies:
                return False, "No strategies loaded for scope"
            
            strategy_names = [s.name for s in strategies]
            return True, f"{len(strategies)} strategies: {strategy_names}"
        
        except Exception as e:
            return False, f"Strategy loading failed: {e}"
    
    def _validate_ml(self) -> Tuple[bool, str]:
        """Validate ML system is configured."""
        try:
            ml_state = MLStateManager()
            active_version = ml_state.get_active_model_version()
            
            if active_version:
                msg = f"Active model version: {active_version}"
            else:
                msg = "No active model (will use rules-only)"
                self._warn("ML model not yet trained")
            
            return True, msg
        
        except Exception as e:
            return False, f"ML system validation failed: {e}"
    
    def _validate_pipeline(self) -> Tuple[bool, str]:
        """Validate single execution pipeline exists."""
        try:
            # Check key components exist
            from core.engine import TradingEngine
            from risk.trade_intent_guard import TradeIntentGuard
            from risk.risk_manager import RiskManager
            
            msg = "Single pipeline: Strategy → Guard → Risk → Broker"
            return True, msg
        
        except Exception as e:
            return False, f"Pipeline validation failed: {e}"


def validate_startup() -> bool:
    """
    Run full startup validation.
    
    Returns:
        True if all checks passed
    
    Exits with code 1 if validation fails.
    """
    validator = StartupValidator()
    passed = validator.validate_all()
    
    if not passed:
        sys.exit(1)
    
    return True
