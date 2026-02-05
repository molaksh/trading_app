# Crypto Kraken Global Trading System

## Overview

This document describes the crypto trading infrastructure for **24/7 crypto markets** on Kraken, with **enforced daily downtime** for ML training and model promotion.

**Key differentiators from swing trading:**
- 24/7 trading with configurable daily downtime window (default 03:00-05:00 UTC)
- ML training/validation runs ONLY during downtime
- Paper container generates training data; live container uses only APPROVED models
- Strict artifact isolation: NO cross-contamination with swing artifacts
- Explicit promotion gate for model deployment to live

---

## Architecture

```
Market Data
    ↓
Feature Builder → Regime Engine → Strategy Layer Selector
    ↓
Signal Generators (6 strategies, max 2 active)
    ↓
Global Risk Manager
    ↓
Execution Engine (REUSED from swing)
    ↓
Kraken Broker Adapter (live) / Paper Simulator (paper)
```

---

## Directory Structure

```
trading_app/
├── crypto/
│   ├── __init__.py
│   ├── artifacts/          # Artifact management (models, ledgers)
│   ├── scheduling/         # Downtime scheduler
│   ├── universe/           # Crypto universe config
│   ├── regime/             # Market regime detector
│   ├── strategies/         # 6 strategy implementations
│   └── ml_pipeline/        # (future) ML training/validation
├── broker/
│   ├── kraken/
│   │   ├── __init__.py    # KrakenAdapter (LIVE)
│   │   └── paper.py       # PaperKrakenSimulator
│   └── (swing adapters)
├── config/
│   ├── crypto/
│   │   ├── paper.kraken.crypto.global.yaml
│   │   └── live.kraken.crypto.global.yaml
│   └── (swing configs)
├── tools/
│   ├── crypto/
│   │   ├── validate_model.py     # Validate candidate
│   │   ├── promote_model.py      # Promote to approved
│   │   └── rollback_model.py     # Rollback to prev
│   └── (swing tools)
├── tests/
│   ├── crypto/
│   │   ├── test_downtime_scheduler.py
│   │   ├── test_model_approval_gates.py
│   │   ├── test_artifact_isolation.py
│   │   └── test_paper_simulator.py
│   └── (swing tests)
└── run_paper_kraken_crypto.sh    # Docker run script (paper)
    run_live_kraken_crypto.sh     # Docker run script (live)
```

---

## Artifact Storage (Isolated from Swing)

All crypto artifacts are stored under **crypto-specific roots** with no overlap with swing:

```
/data/artifacts/crypto/kraken_global/
├── models/
│   ├── candidates/          # Training output (Paper container)
│   │   └── model_<id>/
│   │       ├── model.pkl
│   │       ├── metadata.json
│   │       ├── metrics.json
│   │       └── sha256.txt
│   ├── validations/         # Validation results
│   │   └── model_<id>.json
│   ├── approvals.jsonl      # Audit log (append-only)
│   ├── registry.jsonl       # Model registry (append-only)
│   ├── approved_model.json  # LIVE reads this pointer
│   └── approved_model.prev.json  # Previous pointer (for rollback)

/data/logs/crypto/kraken_global/
├── observations.jsonl       # Market observations
├── trades.jsonl            # Executed trades
├── approvals.jsonl         # Model approval events
└── registry.jsonl          # Model lifecycle events

/data/datasets/crypto/kraken_global/
├── training/               # Training data snapshots
│   └── dataset_<date>.jsonl

/data/ledger/crypto/kraken_global/
├── positions/
│   └── positions.json
└── trades/
    └── trades.jsonl
```

**Guardrails:**
- Crypto code asserts on startup that paths do NOT contain "swing" substring
- Swing code asserts paths do NOT contain "kraken_global" substring
- Separate Docker containers ensure runtime isolation

---

## Running Crypto Containers

### Paper Container (Simulation + Training)

```bash
# Start paper container (generates training data, trains models)
docker run -d \
  --name paper-kraken-crypto-global \
  --env CONFIG=config/crypto/paper.kraken.crypto.global.yaml \
  --env MODE=trading \
  --volume /data:/data \
  trading-app:latest

# Watch logs
docker logs -f paper-kraken-crypto-global

# During downtime (03:00-05:00 UTC), you'll see:
# - Trading paused
# - ML training running
# - Model candidates saved to /data/artifacts/crypto/kraken_global/models/candidates/
```

### Live Container (Trading + Validation)

```bash
# Start live container (trades with approved model only)
docker run -d \
  --name live-kraken-crypto-global \
  --env CONFIG=config/crypto/live.kraken.crypto.global.yaml \
  --env MODE=trading \
  --env KRAKEN_API_KEY=<key> \
  --env KRAKEN_API_SECRET=<secret> \
  --volume /data:/data \
  trading-app:latest

# Watch logs
docker logs -f live-kraken-crypto-global

# During downtime (03:00-05:00 UTC), you'll see:
# - Trading paused
# - Validation/backtesting of approved model
# - Optional shadow-mode evaluation of candidates
# - NO training (live never trains)
```

---

## Downtime Scheduling

**Default window:** 03:00-05:00 UTC (2 hours)  
**Configurable:** Set `DOWNTIME_START_UTC` and `DOWNTIME_END_UTC` in config

### Trading Hours (05:00-03:00 UTC next day)
- **What happens:** Trading loop runs continuously
- **ML:** DISABLED (read-only inference if model available)
- **Strategy:** Active strategies generate signals based on regime
- **Execution:** Orders submitted to Kraken (live) or simulator (paper)
- **Risk Manager:** All checks enforced

### Downtime Hours (03:00-05:00 UTC)
- **Trading:** PAUSED (no new orders)
- **Paper:** ML training runs on collected trades
  - Generates candidate models
  - Saves to `candidates/model_<id>/`
  - Metrics stored in `metrics.json`
  - Training must finish before downtime ends
- **Live:** ML validation/backtest runs
  - Validates approved model performance
  - Optional: shadow-mode evaluation of candidates
  - No trading (orders rejected if submitted)
- **If training overruns:** Aborts, keeps last approved model, resumes trading safely

---

## ML Model Lifecycle

### State Machine

```
Training Output (Paper)
  ↓
Candidates/ (requires validation)
  ↓
Validate Candidate (checks integrity, OOS metrics)
  ↓
PASS → Promote to Approved
↓
FAIL → Discard (keep previous approved)
```

### File Locations

1. **After training:**
   ```
   /data/artifacts/crypto/kraken_global/models/candidates/model_abc123/
   ├── model.pkl              # Serialized model weights
   ├── metadata.json          # Feature schema version, training dates
   ├── metrics.json           # OOS Sharpe, Max DD, turnover, etc.
   └── sha256.txt            # Integrity hashes
   ```

2. **After validation:**
   ```
   /data/artifacts/crypto/kraken_global/models/validations/model_abc123.json
   {
       "model_id": "model_abc123",
       "passed": true,
       "checks": {
           "integrity": true,
           "oos_sharpe": 0.75,
           "max_drawdown": 0.12,
           "tail_loss": 0.03,
           "annual_turnover": 1.5
       },
       "failures": []
   }
   ```

3. **After promotion:**
   ```
   /data/artifacts/crypto/kraken_global/models/approved_model.json
   {
       "model_id": "model_abc123",
       "status": "approved",
       "promoted_at": "2026-02-05T10:30:00",
       "promoted_by": "live_kraken_crypto_global",
       "candidate_path": "/data/artifacts/crypto/kraken_global/models/candidates/model_abc123"
   }
   ```

### Audit Trail

Every promotion/rollback is logged to `approvals.jsonl`:
```jsonl
{"timestamp": "...", "model_id": "model_abc123", "action": "promote", "env": "live", "reason": "..."}
{"timestamp": "...", "model_id": "model_abc123", "action": "rollback", "env": "live", "to_model": "model_xyz789"}
```

---

## Model Approval Workflow

### 1. Train Model (Paper Container, During Downtime)

Paper container executes at ~04:00 UTC:
- Collects trades from past 24h
- Builds features
- Trains ML model
- Computes OOS metrics
- Saves to `candidates/model_<id>/`

```bash
# Example output in logs:
# 2026-02-05 04:15:30 | INFO | ml_pipeline | Training model_20260205_abc123...
# 2026-02-05 04:25:00 | INFO | ml_pipeline | ✓ Model saved: model_20260205_abc123
# 2026-02-05 04:25:01 | INFO | ml_pipeline | Metrics: Sharpe=0.75, DD=12%, turnover=1.5x
```

### 2. Validate Candidate

Human operator (or automated gate) validates:

```bash
python tools/crypto/validate_model.py \
  --model-id model_20260205_abc123 \
  --min-oos-sharpe 0.5 \
  --max-drawdown 0.15 \
  --max-tail-loss 0.05 \
  --max-turnover 2.0
```

**Output:** `validations/model_20260205_abc123.json` with PASS/FAIL

**Gates (fail if any unmet):**
- OOS Sharpe ≥ 0.5
- Max Drawdown ≤ 15%
- Tail Loss (99th pct) ≤ 5%
- Annual Turnover ≤ 2.0x

### 3. Promote to Approved (Explicit Gate)

**Requires:**
- Validation PASS
- Explicit confirmation flag
- Manual approval (future: may add governance)

```bash
python tools/crypto/promote_model.py \
  --model-id model_20260205_abc123 \
  --env live_kraken_crypto_global \
  --reason "OOS Sharpe improved 20%, DD reduced to 12%" \
  --confirm yes-promote
```

**What happens:**
- Atomically updates `approved_model.json` pointer
- Backs up current approved to `approved_model.prev.json`
- Appends approval record to `approvals.jsonl`

**Live container detects change immediately** (on next loop):
- Reloads `approved_model.json`
- Verifies SHA256 + schema
- Resumes trading with new model

### 4. Rollback (If Issues)

```bash
python tools/crypto/rollback_model.py \
  --env live_kraken_crypto_global \
  --confirm yes-rollback
```

- Restores `approved_model.prev.json` → `approved_model.json`
- Logs rollback event
- Live container resumes with previous model

---

## Risk Management

Same risk checks as swing, applied to crypto:

| Check | Threshold | Action |
|-------|-----------|--------|
| Consecutive Losses | 3 | KILL SWITCH (no new orders) |
| Daily Loss | -2% | KILL SWITCH |
| Daily Trade Count | 20 | SKIP new orders |
| Portfolio Heat | 8% | REJECT trade |
| Per-Symbol Risk | 5% | REJECT trade |
| Per-Trade Risk | 2% × confidence mult | Position sized |
| Entry Price | > 0 and < equity | Sanity check |

---

## Paper Simulator

Paper container uses `PaperKrakenSimulator`:

```python
simulator = PaperKrakenSimulator(
    starting_balance_usd=10_000.0,
    maker_fee=0.0016,
    taker_fee=0.0026,
    slippage_bps=5.0,
    enable_funding_costs=False,  # Perp funding
    seed=None,  # Randomness control
)

# Simulate fill
order = simulator.submit_market_order(
    symbol='XXBTZUSD',
    quantity=0.1,
    side='buy',
    mid_price=45000.0,
)
```

**Features:**
- Realistic slippage + fees
- Deterministic testing (seed option)
- Builds training dataset from fills
- Balances/positions tracked

---

## Universe Configuration

Crypto universe is configurable:

```yaml
# config/crypto/paper.kraken.crypto.global.yaml
CRYPTO_UNIVERSE = ["BTC", "ETH", "SOL"]  # Add/remove as needed
UNIVERSE_MIN_VOLUME_USD = 1000000        # Liquidity filter
UNIVERSE_MAX_SPREAD_BPS = 50             # Spread filter
```

**Canonical symbols:** BTC, ETH, SOL, XRP, ADA, DOT, LINK, DOGE, MATIC, AVAX

**Kraken pairs (auto-mapped):**
- BTC → XXBTZUSD
- ETH → XETHZUSD
- SOL → SOLZUSD
- etc.

---

## Strategies (6 Types)

Implemented (with placeholders):

1. **Trend Follower** (RISK_ON only)
   - Long-term trend following
   - Max position count: 5
   - Time horizon: days/weeks

2. **Volatility Swing** (RISK_ON, NEUTRAL)
   - Swing trading with vol scaling
   - Re-entries on dips

3. **Mean Reversion** (NEUTRAL only)
   - Reversal to moving averages
   - Low volatility environments

4. **Defensive Hedge** (RISK_OFF, PANIC only)
   - Protective shorts
   - Small positions, time-limited

5. **Stable Allocator** (PANIC)
   - Derisking, move to stables
   - Reduce or flatten portfolio

6. **Recovery Re-Entry** (PANIC → NEUTRAL)
   - Re-entry after panic bottoms
   - Dip buying

**Selection:** Max 2 concurrent strategies; regime engine selects active set.

---

## Startup Verification

Both containers print startup banner and verify:

```
================================================================================
CRYPTO TRADING SYSTEM STARTUP VERIFICATION
================================================================================
✓ Config loaded: paper_kraken_crypto_global
✓ Environment: paper
✓ Artifact root: /data/artifacts/crypto/kraken_global
✓ Artifact isolation verified (no swing paths)
✓ Universe: BTC, ETH, SOL
✓ Downtime window: 03:00-05:00 UTC
✓ Trading scheduled: 05:00-03:00 UTC (active), 03:00-05:00 UTC (training)
✓ ML mode: TRAINING_ENABLED (paper), INFERENCE_ONLY (live)
✓ Approved model: /data/artifacts/crypto/kraken_global/models/approved_model.json
  → Status: NOT FOUND (will use rules-only fallback until promoted)
✓ Kraken connectivity: SIMULATOR (paper) / API READY (live)
✓ All checks passed. Ready for trading.
================================================================================
```

---

## Logging & Monitoring

### Log Locations

```
/data/logs/crypto/kraken_global/
├── observations.jsonl       # Market observations (OHLCV, indicators)
├── trades.jsonl            # Every trade executed (symbol, side, qty, price, fee)
├── approvals.jsonl         # Model promotion/rollback events
└── registry.jsonl          # Model lifecycle (created, trained, validated)
```

### Log Levels

- **INFO:** Trades, model updates, regime changes
- **WARNING:** Risk rejections, model load issues, overruns
- **ERROR:** Execution failures, API errors, reconciliation issues

### Monitoring Hooks

- Every trade logged to execution_logger (reused from swing)
- Model promotions/rollbacks logged to approvals.jsonl
- Training completion logged (with overrun alerts if needed)

---

## Testing

Run crypto test suite:

```bash
# Test downtime scheduling
pytest tests/crypto/test_downtime_scheduler.py -v

# Test model approval gates
pytest tests/crypto/test_model_approval_gates.py -v

# Test artifact isolation
pytest tests/crypto/test_artifact_isolation.py -v

# Test paper simulator
pytest tests/crypto/test_paper_simulator.py -v
```

---

## Troubleshooting

### Downtime not triggering
```bash
# Check scheduler state
docker exec paper-kraken-crypto-global python -c \
  "from crypto.scheduling import create_scheduler; s = create_scheduler(); print(s.get_current_state())"
```

### Model won't promote
```bash
# Check validation result
cat /data/artifacts/crypto/kraken_global/models/validations/model_<id>.json

# If FAILED, check metrics against thresholds in config
```

### Live container stuck on old approved model
```bash
# Check approved pointer
cat /data/artifacts/crypto/kraken_global/models/approved_model.json

# Verify live can read it (check permissions)
ls -la /data/artifacts/crypto/kraken_global/models/
```

### Training overran downtime
```bash
# Check training logs during downtime
docker logs paper-kraken-crypto-global 2>&1 | grep -i "training\|abort"

# Increase downtime window if training consistently overruns
```

---

## Rollout Checklist

- [ ] Pull `feature/crypto-kraken-global` branch
- [ ] Verify artifact roots exist and are empty:
  ```bash
  mkdir -p /data/{artifacts,logs,datasets,ledger}/crypto/kraken_global
  ```
- [ ] Test paper container with `run_paper_kraken_crypto.sh`
  - Wait for downtime (03:00-05:00 UTC) to see training
  - Validate training completes before 05:00
- [ ] Validate first candidate model:
  ```bash
  python tools/crypto/validate_model.py --model-id model_<id>
  ```
- [ ] Promote first model to approved (manual):
  ```bash
  python tools/crypto/promote_model.py --model-id model_<id> --env live_kraken_crypto_global --confirm yes-promote
  ```
- [ ] Start live container with `run_live_kraken_crypto.sh`
  - Verify it loads approved model during startup
  - Monitor first trades
- [ ] Set up alerts for:
  - Training overruns
  - Model load failures
  - High consecutive losses
  - Downtime window changes

---

## Further Development

Future enhancements:

1. **Governance:** Automated approval gates (e.g., approval from multiple signers)
2. **Shadow mode:** Run candidate in shadow mode, compare metrics
3. **Perp funding:** Simulate and optimize perp funding costs
4. **Multi-pair correlation:** Regime based on correlated portfolio moves
5. **Risk parity:** Equal-risk weighting across strategies
6. **Circuit breakers:** Auto-reduce size on volatility spikes

