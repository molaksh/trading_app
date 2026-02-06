#!/usr/bin/env python3
"""
Manual verification of crypto ML orchestration fix.

Simulates the key scenarios without pytest:
- ML skip with no trades (MAIN FIX)
- ML skip with ML not implemented
- Correct event logging
"""

import sys
import logging
from io import StringIO
from unittest.mock import patch, MagicMock

# Capture logs
log_stream = StringIO()
handler = logging.StreamHandler(log_stream)
handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))

# Setup logger
logger = logging.getLogger('crypto_main')
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Import after setup
from crypto_main import _task_ml_training
from runtime.environment_guard import TradingEnvironment

print("=" * 80)
print("CRYPTO ML ORCHESTRATION VERIFICATION")
print("=" * 80)

# TEST 1: ML skip with no trades
print("\n[TEST 1] ML Training Skip with No Trades")
print("-" * 80)

mock_runtime = MagicMock()
mock_runtime.trade_ledger.get_all_trades.return_value = []

log_stream.truncate(0)
log_stream.seek(0)

with patch('crypto_main.get_environment_guard') as mock_guard:
    with patch('crypto_main.build_paper_trading_runtime', return_value=mock_runtime):
        mock_guard_instance = MagicMock()
        mock_guard_instance.environment = TradingEnvironment.PAPER
        mock_guard.return_value = mock_guard_instance
        
        result = _task_ml_training(runtime=mock_runtime)

logs = log_stream.getvalue()
print("Logs captured:")
print(logs)

# Verify outcomes
passed = True
checks = [
    ("ML_TRAINING_SKIPPED in logs", "ML_TRAINING_SKIPPED" in logs),
    ("no_trades_available cited", "no_trades_available" in logs),
    ("trade_count=0 shown", "trade_count=0" in logs),
    ("NO fake completion log", "ML_TRAINING_COMPLETED" not in logs),
    ("NO placeholder 'feature extraction'", "feature extraction" not in logs),
    ("Runtime returned unchanged", result is mock_runtime),
]

for check_name, result_val in checks:
    status = "✅ PASS" if result_val else "❌ FAIL"
    print(f"  {status}: {check_name}")
    if not result_val:
        passed = False

# TEST 2: ML skip when orchestrator not implemented
print("\n[TEST 2] ML Training Skip - Orchestrator Not Implemented")
print("-" * 80)

mock_runtime2 = MagicMock()
mock_runtime2.trade_ledger.get_all_trades.return_value = [
    {"id": "trade_1", "status": "CLOSED"}
]
mock_runtime2._get_ml_orchestrator.side_effect = NotImplementedError("Not ready")

log_stream.truncate(0)
log_stream.seek(0)

with patch('crypto_main.get_environment_guard') as mock_guard:
    with patch('crypto_main.build_paper_trading_runtime', return_value=mock_runtime2):
        mock_guard_instance = MagicMock()
        mock_guard_instance.environment = TradingEnvironment.PAPER
        mock_guard.return_value = mock_guard_instance
        
        result = _task_ml_training(runtime=mock_runtime2)

logs = log_stream.getvalue()
print("Logs captured:")
print(logs)

checks2 = [
    ("ML_TRAINING_SKIPPED in logs", "ML_TRAINING_SKIPPED" in logs),
    ("ml_orchestrator_not_implemented cited", "ml_orchestrator_not_implemented" in logs),
    ("trade_count=1 shown", "trade_count=1" in logs),
    ("NO fake completion", "ML_TRAINING_COMPLETED" not in logs),
    ("Runtime returned unchanged", result is mock_runtime2),
]

for check_name, result_val in checks2:
    status = "✅ PASS" if result_val else "❌ FAIL"
    print(f"  {status}: {check_name}")
    if not result_val:
        passed = False

# TEST 3: Proper logging when ML succeeds
print("\n[TEST 3] ML Training Success - Correct Event Sequence")
print("-" * 80)

mock_runtime3 = MagicMock()
mock_runtime3.trade_ledger.get_all_trades.return_value = [
    {"id": "trade_1", "status": "CLOSED"},
    {"id": "trade_2", "status": "CLOSED"},
]

mock_orchestrator = MagicMock()
mock_orchestrator.run_offline_ml_cycle.return_value = {
    "model_version": "v_2026_02_06_001",
    "metrics": {"accuracy": 0.72}
}
mock_runtime3._get_ml_orchestrator.return_value = mock_orchestrator

log_stream.truncate(0)
log_stream.seek(0)

with patch('crypto_main.get_environment_guard') as mock_guard:
    with patch('crypto_main.build_paper_trading_runtime', return_value=mock_runtime3):
        mock_guard_instance = MagicMock()
        mock_guard_instance.environment = TradingEnvironment.PAPER
        mock_guard.return_value = mock_guard_instance
        
        result = _task_ml_training(runtime=mock_runtime3)

logs = log_stream.getvalue()
print("Logs captured:")
print(logs)

checks3 = [
    ("ML_TRAINING_START logged", "ML_TRAINING_START" in logs),
    ("trade_count=2 shown", "trade_count=2" in logs),
    ("ML_TRAINING_COMPLETED logged", "ML_TRAINING_COMPLETED" in logs),
    ("Model version cited", "v_2026_02_06_001" in logs),
    ("Runtime returned unchanged", result is mock_runtime3),
]

for check_name, result_val in checks3:
    status = "✅ PASS" if result_val else "❌ FAIL"
    print(f"  {status}: {check_name}")
    if not result_val:
        passed = False

# Summary
print("\n" + "=" * 80)
if passed:
    print("✅ ALL VERIFICATION CHECKS PASSED")
    print("=" * 80)
    sys.exit(0)
else:
    print("❌ SOME CHECKS FAILED - SEE ABOVE")
    print("=" * 80)
    sys.exit(1)
