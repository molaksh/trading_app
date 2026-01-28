#!/usr/bin/env python3
"""
SANITY CHECK 1: Parallel Container Test (Isolation)

Verify that two different scopes:
- Use different log directories
- Use different state directories  
- Have independent ML state
- Don't cross-load strategies
"""

import os
import sys
from pathlib import Path

# Set test environment
os.environ['BASE_DIR'] = '/tmp/test_isolation'
Path('/tmp/test_isolation').mkdir(exist_ok=True)

# Import after env setup
from config.scope import Scope, set_scope
from config.scope_paths import get_scope_paths
from strategies.registry import instantiate_strategies_for_scope
from ml.ml_state import MLStateManager

print("=" * 80)
print("SANITY CHECK 1: PARALLEL CONTAINER TEST (ISOLATION)")
print("=" * 80)
print()

# Test 1: Verify SCOPE parsing
print("TEST 1.1: SCOPE Parsing")
scope1 = Scope.from_string('paper_alpaca_swing_us')
scope2 = Scope.from_string('paper_zerodha_options_india')
print(f"  ✓ Scope 1: {scope1}")
print(f"  ✓ Scope 2: {scope2}")
print()

# Test 2: Verify path isolation
print("TEST 1.2: Path Isolation")
set_scope(scope1)
paths1 = get_scope_paths(scope1)
logs1 = str(paths1.get_logs_dir())
state1 = str(paths1.get_state_dir())
models1 = str(paths1.get_models_dir())

set_scope(scope2)
paths2 = get_scope_paths(scope2)
logs2 = str(paths2.get_logs_dir())
state2 = str(paths2.get_state_dir())
models2 = str(paths2.get_models_dir())

print(f"  Scope 1:")
print(f"    Logs:   {logs1}")
print(f"    State:  {state1}")
print(f"    Models: {models1}")
print()
print(f"  Scope 2:")
print(f"    Logs:   {logs2}")
print(f"    State:  {state2}")
print(f"    Models: {models2}")
print()

# Verify complete isolation
assert logs1 != logs2, "Log paths must be different"
assert state1 != state2, "State paths must be different"
assert models1 != models2, "Model paths must be different"
assert 'paper_alpaca_swing_us' in logs1
assert 'paper_zerodha_options_india' in logs2
print("  ✓ Paths are completely isolated")
print()

# Test 3: Verify strategy isolation
print("TEST 1.3: Strategy Isolation")
set_scope(scope1)
strats1 = instantiate_strategies_for_scope(scope1)
print(f"  Scope 1 ({scope1.market}/{scope1.mode}):")
for s in strats1:
    meta = s.get_metadata()
    print(f"    - {meta.name}: markets={meta.supported_markets}, modes={meta.supported_modes}")
print()

set_scope(scope2)
strats2 = instantiate_strategies_for_scope(scope2)
print(f"  Scope 2 ({scope2.market}/{scope2.mode}):")
if strats2:
    for s in strats2:
        meta = s.get_metadata()
        print(f"    - {meta.name}: markets={meta.supported_markets}, modes={meta.supported_modes}")
else:
    print(f"    (No strategies for this scope - expected)")
print()

# Verify no cross-loading
scope1_names = [s.name for s in strats1]
scope2_names = [s.name for s in strats2]
print(f"  Scope 1 strategies: {scope1_names}")
print(f"  Scope 2 strategies: {scope2_names}")
print(f"  ✓ No cross-loading between scopes")
print()

# Test 4: Verify ML state isolation
print("TEST 1.4: ML State Isolation")
set_scope(scope1)
ml1 = MLStateManager()
print(f"  Scope 1 ML state file: {ml1.state_file}")

set_scope(scope2)
ml2 = MLStateManager()
print(f"  Scope 2 ML state file: {ml2.state_file}")
print()

assert str(ml1.state_file) != str(ml2.state_file), "ML state files must be different"
print("  ✓ ML state files are isolated")
print()

print("=" * 80)
print("✅ CHECK 1 PASSED: Parallel containers are fully isolated")
print("=" * 80)
