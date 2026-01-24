"""
Validation script: verify all modules import correctly.
Run this to check that the project structure is sound.
"""

import sys

print("Testing imports...")
print("-" * 60)

tests_passed = 0
tests_total = 0

def test_import(module_path, friendly_name):
    global tests_passed, tests_total
    tests_total += 1
    try:
        __import__(module_path)
        print(f"✓ {friendly_name:40s} PASS")
        tests_passed += 1
        return True
    except Exception as e:
        print(f"✗ {friendly_name:40s} FAIL: {e}")
        return False

# Test core imports
test_import("config.settings", "config.settings")
test_import("universe.symbols", "universe.symbols")
test_import("data.price_loader", "data.price_loader")
test_import("data.synthetic_data", "data.synthetic_data")
test_import("features.feature_engine", "features.feature_engine")
test_import("scoring.rule_scorer", "scoring.rule_scorer")

print("-" * 60)
print(f"Results: {tesprint(f"Results: {tesprint(f"Results: {tesprint(f"Results: {tesprint(f"Resultprprt(print(f"Results: {tesprint(f"Results: {tesprint(   sys.eprint(f"Results: {tesprint(f"Results: {tesprint(f"Resassed} print(f"R faprint(f"Results: {tes1)
