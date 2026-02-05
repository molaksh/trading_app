# CRYPTO SYSTEM DEPLOYMENT CHECKLIST

Complete verification checklist before production deployment.

## Pre-Deployment Verification

### ✓ Code Quality

- [ ] All 76 unit tests passing
  ```bash
  pytest tests/crypto/ -v --tb=short
  ```

- [ ] Code coverage ≥ 90%
  ```bash
  pytest tests/crypto/ --cov=crypto --cov-report=term-missing
  ```

- [ ] No import errors
  ```bash
  python -c "from crypto.artifacts import CryptoArtifactStore; print('✓')"
  python -c "from broker.kraken import KrakenAdapter; print('✓')"
  ```

- [ ] All modules importable
  ```bash
  python -c "import crypto; import broker.kraken; print('✓')"
  ```

### ✓ Configuration Validation

- [ ] Paper config exists and is valid
  ```bash
  ls -la config/crypto/paper.kraken.crypto.global.yaml
  grep "SCOPE:" config/crypto/paper.kraken.crypto.global.yaml
  ```

- [ ] Live config exists and is valid
  ```bash
  ls -la config/crypto/live.kraken.crypto.global.yaml
  grep "SCOPE:" config/crypto/live.kraken.crypto.global.yaml
  ```

- [ ] Both configs have correct SCOPE names
  ```bash
  grep "paper_kraken_crypto_global" config/crypto/paper.kraken.crypto.global.yaml
  grep "live_kraken_crypto_global" config/crypto/live.kraken.crypto.global.yaml
  ```

- [ ] Artifact paths are isolated from swing
  ```bash
  grep "swing" config/crypto/*.yaml  # Should be EMPTY
  grep "kraken_global" config/crypto/*.yaml  # Should have matches
  ```

### ✓ Directory Structure

- [ ] All required directories created
  ```bash
  ls -la crypto/
  ls -la config/crypto/
  ls -la tools/crypto/
  ls -la tests/crypto/
  ls -la broker/kraken/
  ```

- [ ] Data directories for artifacts
  ```bash
  mkdir -p data/artifacts/crypto/kraken_global/{models,candidates,validations,shadow}
  mkdir -p data/logs/crypto/kraken_global/{observations,trades,approvals,registry}
  mkdir -p data/datasets/crypto/kraken_global/{training,validation,live}
  mkdir -p data/ledger/crypto/kraken_global
  ```

### ✓ Docker Images

- [ ] Trading app image built
  ```bash
  docker build -t trading_app:latest .
  ```

- [ ] Image contains all crypto modules
  ```bash
  docker run --rm trading_app:latest python -c "from crypto.artifacts import CryptoArtifactStore; print('✓')"
  ```

### ✓ Artifact Store

- [ ] CryptoArtifactStore class implemented
  ```bash
  grep -l "class CryptoArtifactStore" crypto/artifacts/__init__.py
  ```

- [ ] Isolation guards in place
  ```bash
  grep -A2 "assert.*swing" crypto/artifacts/__init__.py
  ```

- [ ] SHA256 verification working
  ```bash
  grep -l "hashlib.sha256" crypto/artifacts/__init__.py
  ```

### ✓ Universe Configuration

- [ ] CryptoUniverse with Kraken mappings
  ```bash
  grep "XXBTZUSD" crypto/universe/__init__.py
  grep "XETHZUSD" crypto/universe/__init__.py
  ```

- [ ] All 10 symbols mapped
  ```bash
  grep "add_symbol\|KRAKEN_MAPPING" crypto/universe/__init__.py | wc -l
  # Should show creation of multiple symbols
  ```

### ✓ Downtime Scheduler

- [ ] DowntimeScheduler with 03:00-05:00 UTC window
  ```bash
  grep "03:00" crypto/scheduling/__init__.py
  grep "05:00" crypto/scheduling/__init__.py
  ```

- [ ] TradingState enum
  ```bash
  grep "class TradingState" crypto/scheduling/__init__.py
  ```

- [ ] 12 test cases passing
  ```bash
  pytest tests/crypto/test_downtime_scheduler.py -v --tb=line | grep "passed"
  ```

### ✓ ML Pipeline

- [ ] MLPipeline class implemented
  ```bash
  grep "class MLPipeline" crypto/ml_pipeline/__init__.py
  ```

- [ ] 4 validation gates
  ```bash
  grep "INTEGRITY_CHECK\|SCHEMA_CHECK\|OOS_METRICS\|RISK_CHECKS" crypto/ml_pipeline/__init__.py
  ```

- [ ] Training during downtime only
  ```bash
  grep "downtime_scheduler.is_training_allowed" crypto/ml_pipeline/__init__.py
  ```

- [ ] 14 test cases passing
  ```bash
  pytest tests/crypto/test_ml_pipeline.py -v --tb=line | grep "passed"
  ```

### ✓ Paper Simulator

- [ ] PaperKrakenSimulator with realistic fills
  ```bash
  grep "class PaperKrakenSimulator" broker/kraken/paper.py
  ```

- [ ] Fee and slippage simulation
  ```bash
  grep "maker_fee\|taker_fee\|slippage" broker/kraken/paper.py
  ```

- [ ] 12 test cases passing
  ```bash
  pytest tests/crypto/test_paper_simulator.py -v --tb=line | grep "passed"
  ```

### ✓ Model Approval Tools

- [ ] validate_model.py executable
  ```bash
  ls -la tools/crypto/validate_model.py
  python tools/crypto/validate_model.py --help
  ```

- [ ] promote_model.py with --confirm flag
  ```bash
  grep "confirm" tools/crypto/promote_model.py
  python tools/crypto/promote_model.py --help
  ```

- [ ] rollback_model.py with audit log
  ```bash
  grep "approvals.jsonl" tools/crypto/rollback_model.py
  python tools/crypto/rollback_model.py --help
  ```

### ✓ Broker Adapters

- [ ] KrakenAdapter skeleton
  ```bash
  grep "class KrakenAdapter" broker/kraken/__init__.py
  ```

- [ ] OrderStatus enum
  ```bash
  grep "class OrderStatus" broker/kraken/__init__.py
  ```

- [ ] Core methods (get_balances, submit_order, etc)
  ```bash
  grep "def get_balances\|def submit_market_order\|def get_positions" broker/kraken/__init__.py
  ```

### ✓ Documentation

- [ ] CRYPTO_README.md (2500+ lines)
  ```bash
  wc -l CRYPTO_README.md
  # Should show > 2500
  ```

- [ ] CRYPTO_TESTING_GUIDE.md
  ```bash
  ls -la CRYPTO_TESTING_GUIDE.md
  wc -l CRYPTO_TESTING_GUIDE.md
  # Should show > 300
  ```

- [ ] Architecture diagram in README
  ```bash
  grep "Architecture\|graph\|Market Data" CRYPTO_README.md
  ```

- [ ] Model lifecycle diagram
  ```bash
  grep "candidates\|validations\|approved" CRYPTO_README.md
  ```

## Docker Container Testing

### ✓ Paper Container

- [ ] Container starts without errors
  ```bash
  timeout 30 ./run_paper_kraken_crypto.sh &
  sleep 5
  docker logs trading_app_paper_kraken_crypto | grep -i "starting\|ready"
  docker stop trading_app_paper_kraken_crypto
  ```

- [ ] Correct SCOPE set
  ```bash
  docker run --rm -e SCOPE=test -e CONFIG=config/crypto/paper.kraken.crypto.global.yaml \
    trading_app:latest python -c "from execution.runtime import runtime; print(runtime.scope.name)"
  ```

- [ ] Data directories mounted
  ```bash
  docker run --rm -v "$(pwd)/data:/data" trading_app:latest ls /data/artifacts/crypto/kraken_global/
  ```

### ✓ Live Container

- [ ] Container can start (requires API keys)
  ```bash
  export KRAKEN_API_KEY="test"
  export KRAKEN_API_SECRET="test"
  # Don't actually run; just verify script is executable
  ls -la run_live_kraken_crypto.sh
  ```

- [ ] Correct environment variables passed
  ```bash
  grep "KRAKEN_API_KEY\|KRAKEN_API_SECRET" run_live_kraken_crypto.sh
  ```

- [ ] Model approval gate set
  ```bash
  grep "VERIFY_MODEL_INTEGRITY\|APPROVED_MODEL_PATH" config/crypto/live.kraken.crypto.global.yaml
  ```

## API Integration

### ✓ Kraken API Setup

- [ ] API credentials available
  ```bash
  echo $KRAKEN_API_KEY | grep -q "."  # Non-empty
  echo $KRAKEN_API_SECRET | grep -q "."  # Non-empty
  ```

- [ ] API tier documented
  ```bash
  grep "KRAKEN_API_TIER" config/crypto/live.kraken.crypto.global.yaml
  ```

- [ ] Read-only test successful (if possible)
  ```bash
  # This would test actual API connectivity, skip if using test keys
  ```

## Safety Gates

### ✓ Model Approval Blocking

- [ ] Live reads only approved_model.json
  ```bash
  grep "approved_model.json" config/crypto/live.kraken.crypto.global.yaml
  ```

- [ ] Never reads candidates directory
  ```bash
  grep -v "candidates" config/crypto/live.kraken.crypto.global.yaml | grep "MODEL_PATH"
  ```

- [ ] Promotion requires explicit flag
  ```bash
  grep "confirm" tools/crypto/promote_model.py
  ```

### ✓ Isolation Guards

- [ ] Swing artifacts never accessed from crypto code
  ```bash
  grep -r "swing" crypto/ broker/kraken/ tools/crypto/ || echo "✓ No swing references"
  ```

- [ ] Crypto artifacts never written to swing paths
  ```bash
  grep -A5 "assert.*root.*swing" crypto/artifacts/__init__.py
  ```

### ✓ Downtime Enforcement

- [ ] Training only during 03:00-05:00 UTC
  ```bash
  grep "03:00\|05:00" crypto/scheduling/__init__.py
  ```

- [ ] Trading blocked during downtime
  ```bash
  grep "is_trading_allowed" crypto/ml_pipeline/__init__.py
  ```

## Performance Validation

### ✓ Test Execution Speed

- [ ] All 76 tests complete in < 30 seconds
  ```bash
  time pytest tests/crypto/ -q
  # Should show total time < 30s
  ```

- [ ] No timeout issues
  ```bash
  pytest tests/crypto/ --timeout=5 -q
  # All tests should complete within 5s each
  ```

### ✓ Memory Usage

- [ ] Simulator handles 1000+ trades efficiently
  ```bash
  python -c "
  from broker.kraken.paper import PaperKrakenSimulator
  sim = PaperKrakenSimulator()
  for i in range(100):
      sim.submit_market_order('BTC/USD', 0.01, 'buy', 50000)
  print('✓ Handled 100 trades')
  "
  ```

## Integration Testing

### ✓ Full System Workflow

- [ ] Artifact isolation working
  ```bash
  pytest tests/crypto/test_artifact_isolation.py -v | grep "passed"
  ```

- [ ] Model lifecycle complete
  ```bash
  pytest tests/crypto/test_model_approval_gates.py::TestModelApprovalGates::test_approved_model_workflow -v
  ```

- [ ] Trading cycle functional
  ```bash
  pytest tests/crypto/test_integration.py::TestIntegrationTradingCycle -v | grep "passed"
  ```

- [ ] Error handling robust
  ```bash
  pytest tests/crypto/test_integration.py::TestIntegrationErrorHandling -v | grep "passed"
  ```

## Final Sign-Off

### ✓ Team Review

- [ ] Code review complete (if applicable)
- [ ] Security audit passed
- [ ] Performance approved
- [ ] Documentation reviewed

### ✓ Backup Plan

- [ ] Previous swing system still operational
- [ ] Rollback procedure documented
- [ ] Data backup before switchover

### ✓ Monitoring Setup

- [ ] Log aggregation configured
- [ ] Alert thresholds set
- [ ] Dashboard created
- [ ] On-call rotation scheduled

## Deployment Steps

### Step 1: Pre-Deployment
```bash
# Verify all checks above
chmod +x run_paper_kraken_crypto.sh
chmod +x run_live_kraken_crypto.sh
```

### Step 2: Paper Testing
```bash
# Start paper container
./run_paper_kraken_crypto.sh &

# Verify training occurs during downtime
# Wait 24 hours for full cycle

# Check for errors
docker logs trading_app_paper_kraken_crypto | grep -i "error\|failed"
```

### Step 3: Live Deployment
```bash
# With Kraken API credentials set
export KRAKEN_API_KEY="actual-key"
export KRAKEN_API_SECRET="actual-secret"

./run_live_kraken_crypto.sh &

# Monitor first 24 hours
docker logs trading_app_live_kraken_crypto -f
```

### Step 4: Post-Deployment
```bash
# Verify trading happening
docker logs trading_app_live_kraken_crypto | grep -i "trade\|order"

# Check artifact creation
ls -la data/artifacts/crypto/kraken_global/models/

# Monitor model promotion
cat data/artifacts/crypto/kraken_global/models/approvals.jsonl
```

## Success Criteria

✓ All 76 tests passing
✓ Docker containers run without errors
✓ Paper simulator produces realistic fills
✓ Model training completes in downtime
✓ Validation gates working
✓ Model promotion requires explicit approval
✓ Live system respects approved model pointer only
✓ No access to swing artifacts from crypto code
✓ Downtime window enforced (no trading 03:00-05:00 UTC)
✓ Audit logs record all promotion/rollback events

**Deployment authorized when all items above are checked.**

---
**Deployment Date:** _______________
**Deployed By:** _______________
**Reviewed By:** _______________
