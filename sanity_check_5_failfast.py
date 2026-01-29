"""
Sanity Check 5: Fail-Fast Validation Test

Tests that invalid configurations fail immediately at startup,
before any trading loop begins.

Expected behavior:
1. Invalid SCOPE format → raises ValueError
2. Unsupported market → raises ValueError
3. Unsupported mode → raises ValueError
4. Missing PERSISTENCE_ROOT → creates directories
5. Valid SCOPEs pass validation
"""

import os
import sys
import shutil
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_invalid_scope_format():
    """Test that invalid SCOPE format raises ValueError."""
    print("TEST 5.1: Invalid SCOPE Format")
    
    # Save original
    original_scope = os.environ.get("SCOPE")
    
    test_cases = [
        ("invalid", "Should have 4 underscore-separated parts"),
        ("paper_alpaca_swing", "Missing market component"),
        ("paper_alpaca", "Too few components"),
        ("paper_alpaca_swing_us_extra", "Too many components"),
    ]
    
    for invalid_scope, reason in test_cases:
        os.environ["SCOPE"] = invalid_scope
        try:
            # Force reload of SCOPE
            from importlib import reload
            import config.scope
            reload(config.scope)
            scope = config.scope.get_scope()
            print(f"  ✗ FAILED: '{invalid_scope}' should have failed ({reason})")
            sys.exit(1)
        except ValueError as e:
            print(f"  ✓ '{invalid_scope}' correctly rejected: {str(e)[:60]}")
    
    # Restore original
    if original_scope:
        os.environ["SCOPE"] = original_scope
    else:
        if "SCOPE" in os.environ:
            del os.environ["SCOPE"]
    
    print("  ✓ Invalid SCOPE formats correctly rejected\n")


def test_unsupported_market():
    """Test that unsupported markets raise ValueError."""
    print("TEST 5.2: Unsupported Market")
    
    # Save original
    original_scope = os.environ.get("SCOPE")
    original_base = os.environ.get("PERSISTENCE_ROOT")
    
    # Use temp dir
    temp_dir = tempfile.mkdtemp(prefix="test_failfast_")
    os.environ["PERSISTENCE_ROOT"] = temp_dir
    
    invalid_markets = ["europe", "asia", "invalid"]
    
    for market in invalid_markets:
        os.environ["SCOPE"] = f"paper_alpaca_swing_{market}"
        try:
            from importlib import reload
            import config.scope
            reload(config.scope)
            scope = config.scope.get_scope()
            
            # Try to validate
            from startup.validator import validate_startup
            validate_startup()
            print(f"  ✗ FAILED: Market '{market}' should have been rejected")
            sys.exit(1)
        except ValueError as e:
            print(f"  ✓ Market '{market}' correctly rejected: {str(e)[:60]}")
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)
    
    if original_scope:
        os.environ["SCOPE"] = original_scope
    if original_base:
        os.environ["PERSISTENCE_ROOT"] = original_base
    
    print("  ✓ Unsupported markets correctly rejected\n")


def test_unsupported_mode():
    """Test that unsupported modes raise ValueError."""
    print("TEST 5.3: Unsupported Mode")
    
    # Save original
    original_scope = os.environ.get("SCOPE")
    original_base = os.environ.get("PERSISTENCE_ROOT")
    
    # Use temp dir
    temp_dir = tempfile.mkdtemp(prefix="test_failfast_")
    os.environ["PERSISTENCE_ROOT"] = temp_dir
    
    invalid_modes = ["scalping", "arbitrage", "invalid"]
    
    for mode in invalid_modes:
        os.environ["SCOPE"] = f"paper_alpaca_{mode}_us"
        try:
            from importlib import reload
            import config.scope
            reload(config.scope)
            scope = config.scope.get_scope()
            
            # Try to validate
            from startup.validator import validate_startup
            validate_startup()
                original_base = os.environ.get("PERSISTENCE_ROOT")
            sys.exit(1)
        except ValueError as e:
            print(f"  ✓ Mode '{mode}' correctly rejected: {str(e)[:60]}")
    
                os.environ["PERSISTENCE_ROOT"] = test_dir
    shutil.rmtree(temp_dir, ignore_errors=True)
    
    if original_scope:
        os.environ["SCOPE"] = original_scope
    if original_base:
        os.environ["PERSISTENCE_ROOT"] = original_base
    
    print("  ✓ Unsupported modes correctly rejected\n")


def test_missing_base_dir():
    """Test that PERSISTENCE_ROOT path creation works."""
    print("TEST 5.4: PERSISTENCE_ROOT Path Creation")
    
    # Save original
    original_scope = os.environ.get("SCOPE")
    original_base = os.environ.get("PERSISTENCE_ROOT")
    
    # Set valid scope and point to non-existent directory
    os.environ["SCOPE"] = "paper_alpaca_swing_us"
    test_dir = "/tmp/test_nonexistent_base_dir_12345"
    os.environ["PERSISTENCE_ROOT"] = test_dir
    
    # Clean up if exists from previous run
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    
    try:
        from importlib import reload
        import config.scope
        reload(config.scope)
        scope = config.scope.get_scope()
        
        # Create ScopePathResolver instance
        from config.scope_paths import ScopePathResolver
        paths = ScopePathResolver(scope)
        
        # Get path (should work even if directory doesn't exist yet)
        logs_dir = paths.get_logs_dir()
                if original_base:
                    os.environ["PERSISTENCE_ROOT"] = original_base
        # Create the directories
        os.makedirs(logs_dir, exist_ok=True)
        os.makedirs(state_dir, exist_ok=True)
        
        if os.path.exists(logs_dir) and os.path.exists(state_dir):
            print(f"  ✓ Directories created successfully")
            # Cleanup
            shutil.rmtree(test_dir, ignore_errors=True)
        else:
            print(f"  ✗ FAILED: Directories not created")
            sys.exit(1)
            
    except Exception as e:
                os.environ["PERSISTENCE_ROOT"] = temp_dir
        shutil.rmtree(test_dir, ignore_errors=True)
        sys.exit(1)
    
    # Restore original
    if original_scope:
        os.environ["SCOPE"] = original_scope
    if original_base:
        os.environ["PERSISTENCE_ROOT"] = original_base
    
    print("  ✓ PERSISTENCE_ROOT path creation works\n")


def test_valid_scope_passes():
    """Test that valid SCOPE passes parsing."""
    print("TEST 5.5: Valid SCOPE Passes Parsing")
    
    # Save original
    original_scope = os.environ.get("SCOPE")
    original_base = os.environ.get("PERSISTENCE_ROOT")
    
    # Use temp dir
    temp_dir = tempfile.mkdtemp(prefix="test_failfast_")
    os.environ["PERSISTENCE_ROOT"] = temp_dir
    
    valid_scopes = [
        "paper_alpaca_swing_us",
        "paper_ibkr_daytrade_us",
        "paper_zerodha_options_india",
    ]
    
    for scope_str in valid_scopes:
        os.environ["SCOPE"] = scope_str
                if original_base:
                    os.environ["PERSISTENCE_ROOT"] = original_base
            import config.scope
            reload(config.scope)
            scope = config.scope.get_scope()
            
            # Verify scope was parsed correctly
            env, broker, mode, market = scope_str.split("_")
            assert scope.env == env, f"Expected env={env}, got {scope.env}"
            assert scope.broker == broker, f"Expected broker={broker}, got {scope.broker}"
            assert scope.mode == mode, f"Expected mode={mode}, got {scope.mode}"
            assert scope.market == market, f"Expected market={market}, got {scope.market}"
            
            print(f"  ✓ '{scope_str}' parsed correctly")
        except Exception as e:
            print(f"  ✗ FAILED: '{scope_str}' should have parsed: {e}")
            sys.exit(1)
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)
    
    if original_scope:
        os.environ["SCOPE"] = original_scope
    if original_base:
        os.environ["PERSISTENCE_ROOT"] = original_base
    
    print("  ✓ Valid SCOPEs correctly accepted\n")


def main():
    print("=" * 80)
    print("SANITY CHECK 5: FAIL-FAST VALIDATION TEST")
    print("=" * 80)
    print()
    
    # Run all tests
    test_invalid_scope_format()
    test_unsupported_market()
    test_unsupported_mode()
    test_missing_base_dir()
    test_valid_scope_passes()
    
    print("=" * 80)
    print("✅ CHECK 5 PASSED: Fail-fast validation test successful")
    print("=" * 80)


if __name__ == "__main__":
    main()
