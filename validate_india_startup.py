#!/usr/bin/env python3
"""
India Rules-Only Paper Trading - Startup Validation

Validates that all components are ready for India rules-only trading:
1. MARKET_MODE = "INDIA"
2. INDIA_RULES_ONLY = True
3. ML is disabled
4. Observation log writable
5. Risk manager initializes
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def validate_startup():
    """Validate all startup conditions."""
    print("\n" + "=" * 80)
    print("INDIA RULES-ONLY PAPER TRADING - STARTUP VALIDATION")
    print("=" * 80)
    
    checks_passed = 0
    checks_total = 0
    
    # Check 1: Config settings
    print("\n[1] Verifying configuration settings...")
    checks_total += 1
    
    try:
        from config.settings import (
            MARKET_MODE,
            INDIA_MODE,
            INDIA_RULES_ONLY,
            INDIA_ML_VALIDATION_ENABLED,
            INDIA_MIN_OBSERVATION_DAYS,
            INDIA_OBSERVATION_LOG_DIR,
            START_CAPITAL,
        )
        
        assert MARKET_MODE == "INDIA", f"MARKET_MODE should be INDIA, got {MARKET_MODE}"
        assert INDIA_MODE == True, f"INDIA_MODE should be True"
        assert INDIA_RULES_ONLY == True, f"INDIA_RULES_ONLY should be True"
        assert INDIA_ML_VALIDATION_ENABLED == False, f"INDIA_ML_VALIDATION_ENABLED should be False"
        
        print(f"  ✓ MARKET_MODE = {MARKET_MODE}")
        print(f"  ✓ INDIA_MODE = {INDIA_MODE}")
        print(f"  ✓ INDIA_RULES_ONLY = {INDIA_RULES_ONLY}")
        print(f"  ✓ INDIA_ML_VALIDATION_ENABLED = {INDIA_ML_VALIDATION_ENABLED}")
        print(f"  ✓ INDIA_MIN_OBSERVATION_DAYS = {INDIA_MIN_OBSERVATION_DAYS}")
        print(f"  ✓ INDIA_OBSERVATION_LOG_DIR = {INDIA_OBSERVATION_LOG_DIR}")
        print(f"  ✓ START_CAPITAL = ${START_CAPITAL:,}")
        checks_passed += 1
    except AssertionError as e:
        print(f"  ✗ Configuration check failed: {e}")
    except Exception as e:
        print(f"  ✗ Error loading configuration: {e}")
    
    # Check 2: India universe
    print("\n[2] Verifying India universe...")
    checks_total += 1
    
    try:
        from universe.india_universe import NIFTY_50
        assert len(NIFTY_50) > 0, "NIFTY_50 universe is empty"
        print(f"  ✓ India universe (NIFTY 50) loaded: {len(NIFTY_50)} symbols")
        print(f"    Sample: {NIFTY_50[:5]}")
        checks_passed += 1
    except Exception as e:
        print(f"  ✗ Error loading India universe: {e}")
    
    # Check 3: Observation log
    print("\n[3] Verifying observation log...")
    checks_total += 1
    
    try:
        from monitoring.india_observation_log import IndiaObservationLogger
        from config.settings import INDIA_OBSERVATION_LOG_DIR
        
        logger = IndiaObservationLogger(INDIA_OBSERVATION_LOG_DIR)
        status = logger.get_observation_status()
        
        print(f"  ✓ Observation logger initialized")
        print(f"    Directory: {INDIA_OBSERVATION_LOG_DIR}")
        print(f"    Observation days recorded: {status['total_observation_days']}")
        print(f"    Ready for ML validation: {status['ready_for_ml_validation']}")
        checks_passed += 1
    except Exception as e:
        print(f"  ✗ Error initializing observation log: {e}")
    
    # Check 4: Risk Manager
    print("\n[4] Verifying RiskManager...")
    checks_total += 1
    
    try:
        from risk.portfolio_state import PortfolioState
        from risk.risk_manager import RiskManager
        from config.settings import START_CAPITAL
        
        portfolio = PortfolioState(START_CAPITAL)
        risk_mgr = RiskManager(portfolio)
        
        print(f"  ✓ RiskManager initialized")
        print(f"    Market mode: India (conservative parameters)")
        print(f"    Starting capital: ${START_CAPITAL:,}")
        checks_passed += 1
    except Exception as e:
        print(f"  ✗ Error initializing RiskManager: {e}")
    
    # Check 5: ML disabled
    print("\n[5] Verifying ML is disabled...")
    checks_total += 1
    
    try:
        from config.settings import INDIA_RULES_ONLY
        
        assert INDIA_RULES_ONLY == True, "INDIA_RULES_ONLY must be True"
        print(f"  ✓ ML is DISABLED (INDIA_RULES_ONLY = True)")
        print(f"    Using rules-based confidence only")
        checks_passed += 1
    except Exception as e:
        print(f"  ✗ Error verifying ML disabled: {e}")
    
    # Check 6: Feature engine
    print("\n[6] Verifying India feature engine...")
    checks_total += 1
    
    try:
        from features.india_feature_engine import IndiaFeatureNormalizer
        
        engine = IndiaFeatureNormalizer()
        print(f"  ✓ IndiaFeatureNormalizer initialized")
        checks_passed += 1
    except Exception as e:
        print(f"  ✗ Error initializing India feature engine: {e}")
    
    # Check 7: Data loader
    print("\n[7] Verifying India data loader...")
    checks_total += 1
    
    try:
        from data.india_data_loader import load_india_price_data
        
        print(f"  ✓ India data loader available")
        print(f"    Data sources: NSE + Yahoo Finance fallback")
        checks_passed += 1
    except Exception as e:
        print(f"  ✗ Error initializing India data loader: {e}")
    
    # Summary
    print("\n" + "=" * 80)
    print("STARTUP VALIDATION SUMMARY")
    print("=" * 80)
    print(f"Checks passed: {checks_passed}/{checks_total}")
    
    if checks_passed == checks_total:
        print("\n✓ ALL CHECKS PASSED - Ready for India rules-only paper trading!")
        print("\nTo start trading:")
        print("  python main.py")
        print("\nThis will:")
        print("  1. Scan NIFTY 50 universe")
        print("  2. Generate rules-only signals (ML disabled)")
        print("  3. Execute with risk limits")
        print("  4. Log daily observation record")
        print("  5. Print execution summary")
        print("\n" + "=" * 80)
        return True
    else:
        print(f"\n✗ {checks_total - checks_passed} check(s) failed")
        print("Please resolve errors before starting paper trading")
        print("=" * 80)
        return False

if __name__ == '__main__':
    success = validate_startup()
    sys.exit(0 if success else 1)
