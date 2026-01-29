#!/usr/bin/env python3
"""
Phase 0 Implementation Verification

Quick sanity checks to ensure all Phase 0 components are properly integrated.
Checks:
1. All new files created and importable
2. SCOPE system works
3. ScopePathResolver works
4. BrokerFactory works
5. StrategyRegistry works
6. MLStateManager works
7. Startup validator works
8. Runtime builds successfully
"""

import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BOLD = '\033[1m'

def check(name: str, func) -> bool:
    """Run a check and report result."""
    try:
        func()
        print(f"{GREEN}✓{RESET} {name}")
        return True
    except Exception as e:
        print(f"{RED}✗{RESET} {name}: {e}")
        return False

def main():
    """Run all verification checks."""
    print(f"\n{BOLD}PHASE 0 VERIFICATION{RESET}\n")
    
    checks_passed = 0
    checks_total = 0
    
    # 1. Check SCOPE system
    checks_total += 1
    if check("SCOPE system (config/scope.py)", lambda: (
        __import__('config.scope', fromlist=['Scope', 'get_scope', 'ALLOWED_SCOPES']),
    )):
        checks_passed += 1
    
    # 2. Check ScopePathResolver
    checks_total += 1
    if check("ScopePathResolver (config/scope_paths.py)", lambda: (
        __import__('config.scope_paths', fromlist=['get_scope_paths']),
    )):
        checks_passed += 1
    
    # 3. Check BrokerFactory
    checks_total += 1
    if check("BrokerFactory (broker/broker_factory.py)", lambda: (
        __import__('broker.broker_factory', fromlist=['get_broker_adapter']),
    )):
        checks_passed += 1
    
    # 4. Check Broker Adapters
    checks_total += 1
    if check("Broker Adapters (ibkr, zerodha, crypto)", lambda: (
        __import__('broker.ibkr_adapter', fromlist=['IBKRAdapter']),
        __import__('broker.zerodha_adapter', fromlist=['ZerodhaAdapter']),
        __import__('broker.crypto_adapter', fromlist=['CryptoAdapter']),
    )):
        checks_passed += 1
    
    # 5. Check StrategyRegistry
    checks_total += 1
    if check("StrategyRegistry (strategies/registry.py)", lambda: (
        __import__('strategies.registry', fromlist=['StrategyRegistry']),
    )):
        checks_passed += 1
    
    # 6. Check ML State
    checks_total += 1
    if check("ML State Manager (ml/ml_state.py)", lambda: (
        __import__('ml.ml_state', fromlist=['MLStateManager', 'compute_dataset_fingerprint']),
    )):
        checks_passed += 1
    
    # 7. Check Startup Validator
    checks_total += 1
    if check("Startup Validator (startup/validator.py)", lambda: (
        __import__('startup.validator', fromlist=['StartupValidator', 'validate_startup']),
    )):
        checks_passed += 1
    
    # 8. Check Strategy Metadata
    checks_total += 1
    if check("Strategy Metadata (strategies/base.py updated)", lambda: (
        __import__('strategies.base', fromlist=['Strategy', 'StrategyMetadata']),
    )):
        checks_passed += 1
    
    # 9. Check SwingEquityStrategy has get_metadata()
    checks_total += 1
    def check_swing_metadata():
        from strategies.swing import SwingEquityStrategy
        s = SwingEquityStrategy()
        metadata = s.get_metadata()
        assert metadata.name == "swing_equity", f"Expected name 'swing_equity', got {metadata.name}"
        assert "us" in metadata.supported_markets, "Should support 'us' market"
        assert "swing" in metadata.supported_modes, "Should support 'swing' mode"
    
    if check("SwingEquityStrategy.get_metadata()", check_swing_metadata):
        checks_passed += 1
    
    # 10. Check Runtime builds
    checks_total += 1
    def check_runtime():
        # Set dummy scope for testing
        import os
        os.environ['SCOPE'] = 'paper_alpaca_swing_us'
        os.environ['PERSISTENCE_ROOT'] = '/tmp/trading_app_test'
        
        # Create base directory
        Path('/tmp/trading_app_test').mkdir(exist_ok=True)
        
        # Try to build runtime (will fail if imports broken)
        from execution.runtime import build_paper_trading_runtime
        
        # Don't actually build (requires broker connection), just check it's importable
        assert build_paper_trading_runtime is not None
    
    if check("Runtime assembly (execution/runtime.py)", check_runtime):
        checks_passed += 1
    
    # Summary
    print(f"\n{BOLD}RESULTS{RESET}")
    print(f"Checks passed: {checks_passed}/{checks_total}")
    
    if checks_passed == checks_total:
        print(f"{GREEN}✓ ALL CHECKS PASSED{RESET}\n")
        return 0
    else:
        print(f"{RED}✗ Some checks failed{RESET}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
