# Offline ML System for Swing Trading

## Overview

This offline ML system **enhances, not replaces**, your rule-based swing trading strategy. It runs **after market close only** to:

1. **Build training datasets** from completed trades
2. **Train risk-filter models** to predict "bad" trades
3. **Evaluate** offline before deployment
4. **Manage model versions** safely with explicit promotion

## Core Design Principles

### ✅ Safety First

- **No online learning** - training only after market close
- **No hindsight bias** - features frozen at decision time
- **No price prediction** - ML is advisory, rules are authoritative
- **Read-only trading** - ML cannot override decisions, only block/size trades

### 🎯 ML's Role

- **BLOCKS** trades predicted to be high-risk (bad expectancy, high MAE)
- **SIZES** position risk proportionally (future enhancement)
- **NEVER CREATES** signals or overrides exits

## Architecture

```
┌─────────────────────────────────────────┐
│     TRADING SESSION (READ-ONLY ML)      │
├─────────────────────────────────────────┤
│ • Load active model at startup          │
│ • Use ML to filter high-risk trades     │
│ • Model locked for entire session       │
│ • Falls back to rules-only if ML fails  │
└─────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────┐
│    AFTER MARKET CLOSE (TRAINING)        │
├─────────────────────────────────────────┤
│ 1. DatasetBuilder: closed trades        │
│ 2. OfflineTrainer: train new model      │
│ 3. OfflineEvaluator: benchmark results  │
│ 4. ModelRegistry: register candidate    │
│ 5. Manual promotion (safety)            │
└─────────────────────────────────────────┘
```

## Components

### 1. DatasetBuilder (`ml/dataset_builder.py`)

Constructs training data from completed trades.

**Immutable Design:**
- Append-only dataset (no overwrites)
- Tracks processed trade IDs to prevent duplicates
- One row per closed trade

**Training Row:**
```python
TradeDataRow(
    symbol="AAPL",
    decision_timestamp="2026-01-27T15:30:00",
    rule_confidence=4,
    rule_features={...},  # Features at decision time
    position_size=100,
    entry_price=150.00,
    exit_price=151.50,
    holding_days=5,
    realized_pnl_pct=0.01,
    mae_pct=-0.02,  # Max adverse excursion
    mfe_pct=0.03,   # Max favorable excursion
)
```

**Usage:**
```python
builder = DatasetBuilder(dataset_dir, trade_ledger)
rows_added, rows_total = builder.build_from_ledger()
```

### 2. OfflineTrainer (`ml/offline_trainer.py`)

Trains logistic regression model to predict "bad" trades.

**Target Label:**
```
is_bad = 1 if (realized_pnl_pct < 0 OR abs(mae_pct) > 0.03) else 0
```

**Model:**
- Binary classifier (logistic regression)
- Features: rule_features at entry time (no lookahead)
- Output: Probability [0-1] that trade is "bad"

**Safety Requirements:**
- Minimum 20 closed trades before training
- Train/test split: 80/20 (deterministic)
- Feature scaling with StandardScaler
- Coefficients logged for interpretability

**Usage:**
```python
trainer = OfflineTrainer(model_dir, dataset_builder)
metrics = trainer.train(mae_threshold=0.03, force=False)
print(f"Test accuracy: {metrics['test_accuracy']:.2%}")
```

### 3. OfflineEvaluator (`ml/offline_evaluator.py`)

Compares rules-only vs rules+ML performance.

**Metrics:**
- Trade count
- Win rate
- Expectancy (average PnL)
- Max drawdown
- Bad trades avoided
- Filtering impact

**Example Output:**
```
Metric                 Rules-Only       Rules+ML
─────────────────────────────────────────────────
Trade Count            50               40
Bad Trades             15               8
Win Rate               70.0%            80.0%
Expectancy             +0.015           +0.025
Max Drawdown           -0.08            -0.05
```

### 4. ModelRegistry (`ml/model_registry.py`)

Manages model versions with explicit promotion.

**States:**
- **Candidate**: Newly trained, awaiting review
- **Active**: In use during trading
- **Locked**: Cannot be changed during trading session

**Usage:**
```python
registry = ModelRegistry(model_dir)

# Register new model
registry.register_candidate(model_id, metrics)

# List candidates
candidates = registry.list_candidates()

# Promote (manual, explicit)
registry.promote_candidate("20260127_153000", reason="Better expectancy")

# Load active model
active_id = registry.get_active_model()
trainer.load_model(active_id)
```

### 5. OfflineMLOrchestrator (`ml/ml_orchestrator.py`)

Coordinates entire offline ML workflow.

**Offline Cycle (after market close):**
```python
orchestrator.run_offline_ml_cycle(force_train=False)
```

Steps:
1. Build dataset from closed trades
2. Train new model (if dataset >= 20 trades)
3. Evaluate vs baseline
4. Register candidate (no auto-promotion)
5. Log results

**Startup (before trading):**
```python
model_loaded = orchestrator.maybe_load_active_model()
# Falls back to rules-only if load fails
```

## Scheduler Integration

### After-Close ML Training

Scheduled once per calendar day (after market close):

```python
# In scheduler.run_forever()
if self.state.last_run_date("offline_ml") != now.date():
    self._run_offline_ml_cycle(now)
```

## Trading-Time Usage

### ML Risk Filter in Executor

When executing a trade signal, ML checks risk probability:

```python
# In PaperTradingExecutor.execute_signal()
if self.ml_trainer and self.ml_trainer.model is not None:
    ml_risk_score = self.ml_trainer.predict_risk(features)
    
    if ml_risk_score > self.ml_risk_threshold:
        logger.warning(f"ML blocked: risk={ml_risk_score:.1%}")
        return False, None  # Block trade
    else:
        logger.info(f"ML approved: low risk")
```

**Risk Threshold:** Configurable [0-1], default=0.5

## Safety Guarantees

### ✅ No Hindsight Bias

Features stored at **entry time**, not exit time:
- Historical indicators (SMA, ATR, volume)
- No future price moves
- No exit prices in training

### ✅ No Online Learning

Training only runs **after market close**:
- Scheduler checks market clock
- Skips training if market open
- Dataset immutable during trading

### ✅ Model Frozen During Trading

Active model is locked at startup:
- Read-only during session
- No weight updates
- Same model for entire session

### ✅ Deterministic Behavior

- Random seed: 42 (reproducible)
- No stochastic online updates
- Same features always in same order

### ✅ Graceful Degradation

If ML fails, trade with rules-only:
```python
if self.ml_trainer is None or self.ml_trainer.model is None:
    # Fall back to rules-only
    logger.info("ML unavailable, using rules-only")
    proceed_with_risk_check()
```

## Workflow: Day-to-Day

### Morning (Pre-Market)

1. **Scheduler starts container**
2. **Load active ML model** (if exists)
3. **Lock model version** for trading day
4. **Initialize executor** with ML trainer
5. **Ready for trading signals**

### During Trading

1. **Signal generated** by rules
2. **ML risk check** (read-only)
   - If risk_score > threshold: **BLOCK**
   - Otherwise: **ALLOW** (risk manager decides)
3. **Trade executed** (if approved by risk manager)
4. **ML model frozen** - no updates

### After Market Close

1. **Swing exits evaluated** and executed
2. **Dataset built** from closed trades
   - Only trades that exited today
   - Features from decision time
3. **New model trained** (if 20+ closed trades)
4. **Candidate registered** (awaiting promotion)
5. **Evaluation report** logged
6. **Model unlocked** (ready for next day)

## Model Promotion Workflow

### Option A: Manual Review (Recommended)

```python
# After-close evaluation shows improvement
# Log summary + metrics
# Review candidates:
registry = ModelRegistry(model_dir)
candidates = registry.list_candidates()
# {
#   "20260127_153000": {
#     "metrics": {"test_accuracy": 0.75, ...}
#   }
# }

# Manually promote if confident
registry.promote_candidate(
    "20260127_153000",
    reason="10% lower drawdown, better expectancy"
)

# At next startup, new model auto-loads
```

### Option B: Future Auto-Promotion

Add safety criteria:
- Better expectancy than baseline
- Lower max drawdown
- No increase in tail risk (extreme losses)
- Statistical significance test

## Logging & Auditing

All ML operations logged to `logs/{market}/{env}/`:

- **ml_training_dataset.jsonl** - Immutable training data
- **ml_dataset_metadata.json** - Dataset statistics
- **ml_models/{model_id}/metadata.json** - Model config
- **ml_models/model_registry.json** - Promotion history
- Console logs with section headers

### Example Console Output

```
════════════════════════════════════════════════════════════════════════════════
║               OFFLINE ML CYCLE (POST-MARKET-CLOSE)                          ║
════════════════════════════════════════════════════════════════════════════════

================================================================================
DATASET BUILDING
================================================================================
Total trades in ledger: 75
Closed trades: 50
Open trades: 25
Rows added: 5
Dataset total: 245

================================================================================
OFFLINE MODEL TRAINING
================================================================================
Training on 245 closed trades
Bad trades (label=1): 73 / 245 (29.8%)
Features: ['close', 'sma_20', 'dist_200sma', 'vol_ratio', 'atr_pct']
Train: 196 | Test: 49
Train accuracy: 0.763
Test accuracy: 0.714
Top features (by coefficient magnitude):
  vol_ratio: -0.84
  atr_pct: -0.62
  dist_200sma: +0.41

════════════════════════════════════════════════════════════════════════════════
OFFLINE EVALUATION
════════════════════════════════════════════════════════════════════════════════

Metric                 Rules-Only       Rules+ML
─────────────────────────────────────────────────
Trade Count            245              216
Bad Trades             73               48
Win Rate               70.2%            77.8%
Expectancy             +0.018           +0.032
Max Drawdown           -0.087           -0.061

════════════════════════════════════════════════════════════════════════════════
OFFLINE ML CYCLE COMPLETE
════════════════════════════════════════════════════════════════════════════════
New candidate: 20260127_153000
Status: Registered (awaiting manual promotion)
Previous active: None
```

## Configuration

### Environment Variables

None currently (ML enabled by default). Future additions:
- `ML_RISK_THRESHOLD=0.5` - Probability threshold
- `ML_MAE_THRESHOLD=0.03` - MAE definition for "bad"
- `ML_MIN_DATASET_SIZE=20` - Min trades before training
- `ML_AUTO_PROMOTE=false` - Enable auto-promotion (default=false)

### Code Knobs

In executor initialization:
```python
executor = PaperTradingExecutor(
    ...,
    ml_trainer=ml_trainer,
    ml_risk_threshold=0.5,  # Adjust sensitivity
)
```

## Troubleshooting

### Model Not Loading

```
Failed to load model {model_id}: ...
ML unavailable, using rules-only
```

**Action:** Check model directory exists, check logs for errors.

### Dataset Too Small

```
Dataset too small (5 rows). Need >= 20 for training.
Will train once dataset reaches 20 closed trades.
```

**Action:** Let system run for more sessions to accumulate trades.

### Training Failure

```
Training skipped (dataset too small)
```

OR

```
Training failed: ...
```

**Action:**
1. Check dataset has closed trades
2. Verify features in training rows are not empty
3. Check disk space for model artifacts

## Future Enhancements

1. **XGBoost Model** - Better feature interaction capture
2. **Auto-Promotion** - Statistical tests for safety
3. **Position Sizing** - Scale risk by ML confidence
4. **Feature Engineering** - Domain-specific features
5. **Drift Detection** - Alert if data distribution shifts
6. **Ensemble Methods** - Combine multiple models

## References

- Dataset: `ml/dataset_builder.py`
- Training: `ml/offline_trainer.py`
- Evaluation: `ml/offline_evaluator.py`
- Registry: `ml/model_registry.py`
- Orchestrator: `ml/ml_orchestrator.py`
- Scheduler Integration: `execution/scheduler.py`
- Executor Usage: `broker/paper_trading_executor.py`
