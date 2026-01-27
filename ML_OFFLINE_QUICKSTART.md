# Offline ML System - Quick Start Guide

## What Just Got Deployed

Your trading app now includes a **complete offline ML system** that:

✅ **Enhances** your rule-based swing trading (never replaces it)  
✅ **Blocks bad trades** by predicting risk  
✅ **Trains only after market close** (zero impact during trading)  
✅ **Uses decision-time features** (no hindsight bias)  
✅ **Requires explicit promotion** (manual safety gates)  

## How It Works Today

### During Market Hours (9:30 AM - 4:00 PM ET)

1. **Your trading rules** generate signals
2. **ML risk filter** checks each signal:
   - Probability model predicts if trade will be "bad" (negative PnL or high MAE)
   - If probability > 0.5 (50%): **BLOCKED** (logged, not executed)
   - If probability ≤ 0.5: **ALLOWED** (rules still decide via risk manager)
3. **Rules and risk management** handle position sizing and exits
4. **ML model is frozen** - no updates, read-only

### After Market Close (4:00 PM - Next Day 9:30 AM)

1. **Dataset builder** collects all closed trades from today
2. **ML trainer** trains a new logistic regression model:
   - Target: "Is this trade bad?" (binary classifier)
   - Features: Your existing rule features at entry time
   - Min 20 closed trades required before training
3. **Offline evaluator** compares:
   - Rules-only performance
   - Rules + ML filtering performance
4. **New model registered** as "candidate"
   - Stored in `logs/{market}/{env}/ml_models/`
   - NOT automatically activated
5. **Manual promotion required** (you decide)

## Current Status

```
✓ ML trainer initialized
✓ Scheduler running (60-sec ticks)
✓ Offline cycle scheduled (once per day after close)
✓ Executor ML checks active (risk filter enabled)
✓ Model registry ready
```

**Active Model:** None (system is bootstrapping)

## First Steps

### 1. Let It Train (Day 1-2)

The system needs **20 closed trades** to train. During this bootstrap:

- ML filter **disabled** (no model available)
- System runs **rules-only**
- Dataset accumulates trades
- On day 2+: First candidate model trains

Monitor progress:
```bash
docker logs -f trading-us-paper-scheduler | grep -E "(Dataset|Training|Offline ML)"
```

### 2. Review First Candidate (After 20 Trades)

Check the evaluation report:
```bash
docker logs trading-us-paper-scheduler | grep -A 20 "OFFLINE EVALUATION"
```

Output looks like:
```
Metric                 Rules-Only       Rules+ML
─────────────────────────────────────────────────
Trade Count            20               18
Bad Trades             6                3
Win Rate               70.0%            83.3%
Expectancy             +0.012           +0.025
Max Drawdown           -0.08            -0.04
```

If better than rules-only: proceed to step 3.

### 3. Promote the Model (Manual)

Once you have a good candidate:

```python
from ml.model_registry import ModelRegistry
from pathlib import Path

registry = ModelRegistry(Path("logs/us/paper/ml_models"))

# List candidates
candidates = registry.list_candidates()
# {'20260127_173000': {'metrics': {...}}}

# Promote
model_id = "20260127_173000"  # Replace with actual ID
registry.promote_candidate(model_id, reason="Better expectancy + lower drawdown")
```

**On next startup:** ML model auto-loads and filters trades.

## What the Model Does

### ✅ Trade Is Approved by ML

Signal: AAPL, confidence=4, features={sma_20: 0.02, vol_ratio: 1.35, ...}

```
ML Risk Score: 0.32 (threshold: 0.50)
ML RISK FILTER: AAPL approved (low risk)
→ Risk manager evaluates
→ If approved: ORDER SUBMITTED
```

### ❌ Trade Is Blocked by ML

Signal: TSLA, confidence=3, features={...}

```
ML Risk Score: 0.68 (threshold: 0.50)
ML RISK FILTER: Trade TSLA has high risk probability (68.0%).
Blocking entry (rules still allow).
→ NO ORDER SUBMITTED
```

## Key Files

| File | Purpose |
|------|---------|
| `ml/dataset_builder.py` | Build training data from closed trades |
| `ml/offline_trainer.py` | Train logistic regression model |
| `ml/offline_evaluator.py` | Compare rules-only vs rules+ML |
| `ml/model_registry.py` | Manage model versions, promotion |
| `ml/ml_orchestrator.py` | Orchestrate entire workflow |
| `ML_OFFLINE_SYSTEM.md` | Complete documentation |
| `logs/{market}/{env}/ml_datasets/` | Training data (append-only) |
| `logs/{market}/{env}/ml_models/` | Model artifacts & registry |

## Monitoring

### Check System Health

```bash
docker logs -f trading-us-paper-scheduler | grep -E "(Model|ML|Dataset|Training)"
```

### View Dataset Stats

```bash
python3 -c "
from ml.dataset_builder import DatasetBuilder
from pathlib import Path
builder = DatasetBuilder(Path('logs/us/paper/ml_datasets'), None)
stats = builder.get_stats()
print(f'Dataset: {stats[\"rows\"]} trades, {stats[\"avg_pnl_pct\"]:.2%} avg PnL')
"
```

### List Candidates

```bash
python3 -c "
from ml.model_registry import ModelRegistry
from pathlib import Path
registry = ModelRegistry(Path('logs/us/paper/ml_models'))
print(registry.get_registry_summary())
"
```

## Safety Guarantees

### 🛡️ No Training During Trading
- Offline trainer only runs after market close
- Scheduler checks market clock before training

### 🛡️ No Hindsight Bias
- Features extracted at trade entry time
- No future price movements used
- Dataset immutable (append-only)

### 🛡️ Model Frozen During Trading
- Active model locked at startup
- No weight updates during session
- Read-only inference only

### 🛡️ Graceful Degradation
- If ML fails to load: falls back to rules-only
- Model version managed separately from trading logic

## Configurable

These can be tuned (in code):

```python
# Risk threshold (default 0.5)
executor = PaperTradingExecutor(..., ml_risk_threshold=0.6)

# MAE threshold for "bad" label (default 3%)
trainer.train(mae_threshold=0.05)

# Min dataset size (default 20)
trainer.train(force=False)  # Skip if < 20 trades
```

## Troubleshooting

### "ML Risk Filter: Disabled"

No active model yet. Normal during bootstrap. Check when you have 20+ closed trades.

### "Failed to load model"

Model file corrupted or missing. Fallback to rules-only automatic.

### "Training failed: ..."

Usually too few closed trades. System will retry tomorrow.

### "ML unavailable, using rules-only"

Safe fallback if ML system has an issue. Trade normally continues.

## Next Steps

1. **Let the system run** for 1-2 trading days
2. **Review first evaluation report** after 20 closed trades
3. **Promote the model** if metrics improve
4. **Monitor performance** in production

After that, the system will:
- Train a new model daily
- Compare to baseline automatically
- Require manual approval to update

---

For full documentation, see: [ML_OFFLINE_SYSTEM.md](ML_OFFLINE_SYSTEM.md)
