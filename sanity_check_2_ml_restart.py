#!/usr/bin/env python3
"""
SANITY CHECK 2: Restart Test (ML State)

Verify that:
- On startup, ML loads active model (no training)
- After restart, no training runs
- Model version remains unchanged
"""

import os
import json
from pathlib import Path

# Setup
os.environ['BASE_DIR'] = '/tmp/test_ml_restart'
os.environ['SCOPE'] = 'paper_alpaca_swing_us'
Path('/tmp/test_ml_restart/paper_alpaca_swing_us/state').mkdir(parents=True, exist_ok=True)

from config.scope import Scope, set_scope
from ml.ml_state import MLStateManager, compute_dataset_fingerprint

print("=" * 80)
print("SANITY CHECK 2: RESTART TEST (ML STATE)")
print("=" * 80)
print()

# Initialize scope
scope = Scope.from_string('paper_alpaca_swing_us')
set_scope(scope)

print("TEST 2.1: Initial State Setup")
ml = MLStateManager()
print(f"  State file: {ml.state_file}")
state_data = json.loads(ml.state_file.read_text()) if ml.state_file.exists() else {}
print(f"  Initial state: {state_data}")
print()

# Simulate first training run
print("TEST 2.2: Simulate First Training Run")
test_fingerprint = "abc123fingerprint"
test_run_id = "run_2026_01_27_v1"
ml.update_dataset_fingerprint(test_fingerprint, test_run_id)
ml.promote_model("v1")

print(f"  After training:")
print(f"    Fingerprint: {test_fingerprint}")
print(f"    Run ID: {test_run_id}")
print(f"    Active model: v1")
print()

# Verify state was persisted
saved_state = json.loads(ml.state_file.read_text())
print(f"  Saved state: {saved_state}")
assert saved_state['active_model_version'] == 'v1'
assert saved_state['last_dataset_fingerprint'] == test_fingerprint
print(f"  ✓ State persisted correctly")
print()

# Simulate restart: create new manager (reload from disk)
print("TEST 2.3: Simulate Restart")
del ml  # Delete old instance
ml_restart = MLStateManager()  # Load fresh from disk
reloaded_state = json.loads(ml_restart.state_file.read_text())
print(f"  Reloaded state: {reloaded_state}")
print(f"  Active model: {ml_restart.get_active_model_version()}")
assert ml_restart.get_active_model_version() == 'v1'
print(f"  ✓ Model version persisted across restart")
print()

# Test idempotency: same fingerprint should skip training
print("TEST 2.4: Idempotency Check (Same Data)")
same_fingerprint = test_fingerprint  # Same data
should_train = ml_restart.should_train(same_fingerprint)
print(f"  Data fingerprint: {same_fingerprint}")
print(f"  Should train? {should_train}")
assert should_train is False, "Should skip training if data unchanged"
print(f"  ✓ Training skipped (data unchanged)")
print()

# Test new data: different fingerprint should require training
print("TEST 2.5: Training Required (New Data)")
new_fingerprint = "xyz789newfingerprint"
should_train_new = ml_restart.should_train(new_fingerprint)
print(f"  Data fingerprint: {new_fingerprint}")
print(f"  Should train? {should_train_new}")
assert should_train_new is True, "Should train if data changed"
print(f"  ✓ Training required (new data detected)")
print()

# Simulate second training with new data
print("TEST 2.6: Second Training Run")
ml_restart.update_dataset_fingerprint(new_fingerprint, "run_2026_01_27_v2")
ml_restart.promote_model("v2")
print(f"  Promoted model to v2")
print()

# Restart again and verify v2 is active
print("TEST 2.7: Second Restart Verification")
del ml_restart
ml_final = MLStateManager()
final_state = json.loads(ml_final.state_file.read_text())
print(f"  Reloaded state: {final_state}")
print(f"  Active model: {ml_final.get_active_model_version()}")
assert ml_final.get_active_model_version() == 'v2'
print(f"  ✓ Model progressed from v1 → v2")
print()

print("=" * 80)
print("✅ CHECK 2 PASSED: ML state persists correctly across restarts")
print("=" * 80)
