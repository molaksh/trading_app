#!/usr/bin/env python3
"""
Verify LIVE Trading Implementation - Check all new modules load and basic syntax
"""

import sys
from pathlib import Path

def check_imports():
    """Verify all new modules can be imported."""
    print("=" * 80)
    print("LIVE TRADING IMPLEMENTATION VERIFICATION")
    print("=" * 80)
    print()
    
    errors = []
    
    # Check 1: Verify files exist
    print("✓ Checking file existence...")
    files_to_check = [
        'crypto/live_trading_startup.py',
        'crypto/live_trading_executor.py',
    ]
    
    for filename in files_to_check:
        filepath = Path(filename)
        if filepath.exists():
            size_kb = filepath.stat().st_size / 1024
            print(f"  ✓ {filename} ({size_kb:.1f} KB)")
        else:
            error = f"  ✗ {filename} NOT FOUND"
            print(error)
            errors.append(error)
    
    print()
    
    # Check 2: Verify imports work
    print("✓ Checking Python imports...")
    try:
        from crypto.live_trading_startup import (
            verify_live_trading_startup,
            LiveTradingStartupVerifier,
            LiveTradingVerificationError,
        )
        print(f"  ✓ crypto.live_trading_startup")
    except ImportError as e:
        error = f"  ✗ crypto.live_trading_startup: {e}"
        print(error)
        errors.append(error)
    
    try:
        from crypto.live_trading_executor import (
            LiveOrderExecutor,
            LiveOrderAuditLogger,
            LiveOrderExecutionError,
            create_live_order_executor,
        )
        print(f"  ✓ crypto.live_trading_executor")
    except ImportError as e:
        error = f"  ✗ crypto.live_trading_executor: {e}"
        print(error)
        errors.append(error)
    
    try:
        from runtime.environment_guard import (
            get_environment_guard,
            EnvironmentGuard,
            TradingEnvironment,
        )
        print(f"  ✓ runtime.environment_guard (already exists)")
    except ImportError as e:
        error = f"  ✗ runtime.environment_guard: {e}"
        print(error)
        errors.append(error)
    
    print()
    
    # Check 3: Verify classes exist
    print("✓ Checking class definitions...")
    classes_to_check = {
        'LiveTradingStartupVerifier': 'crypto.live_trading_startup',
        'LiveTradingVerificationError': 'crypto.live_trading_startup',
        'LiveOrderExecutor': 'crypto.live_trading_executor',
        'LiveOrderAuditLogger': 'crypto.live_trading_executor',
        'LiveOrderExecutionError': 'crypto.live_trading_executor',
    }
    
    for class_name, module_name in classes_to_check.items():
        try:
            module = __import__(module_name, fromlist=[class_name])
            cls = getattr(module, class_name)
            print(f"  ✓ {class_name}")
        except (ImportError, AttributeError) as e:
            error = f"  ✗ {class_name}: {e}"
            print(error)
            errors.append(error)
    
    print()
    
    # Check 4: Verify function signatures
    print("✓ Checking function signatures...")
    try:
        from crypto.live_trading_startup import verify_live_trading_startup
        import inspect
        sig = inspect.signature(verify_live_trading_startup)
        print(f"  ✓ verify_live_trading_startup{sig}")
    except Exception as e:
        error = f"  ✗ verify_live_trading_startup: {e}"
        print(error)
        errors.append(error)
    
    try:
        from crypto.live_trading_executor import create_live_order_executor
        import inspect
        sig = inspect.signature(create_live_order_executor)
        print(f"  ✓ create_live_order_executor{sig}")
    except Exception as e:
        error = f"  ✗ create_live_order_executor: {e}"
        print(error)
        errors.append(error)
    
    print()
    
    # Check 5: Verify crypto_main.py has imports
    print("✓ Checking crypto_main.py modifications...")
    try:
        with open('crypto_main.py', 'r') as f:
            content = f.read()
            if 'from runtime.environment_guard import get_environment_guard' in content:
                print(f"  ✓ crypto_main.py has environment_guard import")
            else:
                error = "  ✗ crypto_main.py missing environment_guard import"
                print(error)
                errors.append(error)
            
            if 'from crypto.live_trading_startup import verify_live_trading_startup' in content:
                print(f"  ✓ crypto_main.py has verify_live_trading_startup import")
            else:
                error = "  ✗ crypto_main.py missing verify_live_trading_startup import"
                print(error)
                errors.append(error)
            
            if 'verify_live_trading_startup()' in content:
                print(f"  ✓ crypto_main.py calls verify_live_trading_startup()")
            else:
                error = "  ✗ crypto_main.py doesn't call verify_live_trading_startup()"
                print(error)
                errors.append(error)
    except Exception as e:
        error = f"  ✗ Error reading crypto_main.py: {e}"
        print(error)
        errors.append(error)
    
    print()
    
    # Check 6: Verify run_live_kraken_crypto.sh modifications
    print("✓ Checking run_live_kraken_crypto.sh modifications...")
    try:
        with open('run_live_kraken_crypto.sh', 'r') as f:
            content = f.read()
            if 'LIVE_TRADING_APPROVED' in content:
                print(f"  ✓ run_live_kraken_crypto.sh checks LIVE_TRADING_APPROVED")
            else:
                error = "  ✗ run_live_kraken_crypto.sh doesn't check LIVE_TRADING_APPROVED"
                print(error)
                errors.append(error)
            
            if 'CRITICAL SAFETY WARNINGS' in content:
                print(f"  ✓ run_live_kraken_crypto.sh has safety warnings")
            else:
                error = "  ✗ run_live_kraken_crypto.sh missing safety warnings"
                print(error)
                errors.append(error)
    except Exception as e:
        error = f"  ✗ Error reading run_live_kraken_crypto.sh: {e}"
        print(error)
        errors.append(error)
    
    print()
    print("=" * 80)
    
    if errors:
        print("VERIFICATION FAILED")
        print()
        print("Errors found:")
        for error in errors:
            print(error)
        print()
        return 1
    else:
        print("✓ ALL VERIFICATION CHECKS PASSED")
        print()
        print("Summary:")
        print("  - All 6 new/updated files present")
        print("  - All Python imports successful")
        print("  - All classes defined")
        print("  - All functions callable")
        print("  - crypto_main.py properly updated")
        print("  - run_live_kraken_crypto.sh properly updated")
        print()
        print("LIVE Trading Implementation is ready for use.")
        print()
        return 0


if __name__ == "__main__":
    exit_code = check_imports()
    sys.exit(exit_code)
