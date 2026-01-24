# Quick Start: Running ML Validation Experiment

## Option 1: Validate ML Training Only (Fast - 1 minute)
Best for checking if ML training works without running full backtest.

```bash
python3 ml_validate.py
```

**Output:**
- ✓ Model trains successfully
- ✓ Confidence scores generated
- ✓ Accuracy metrics printed
- ✓ Ready for backtest

**When to use:** Quick sanity check before full experiment

---

## Option 2: Train ML Model + Compare to Rules (Full - 10+ minutes)
Runs complete experiment with backtest comparison.

### Step 1: Enable ML Experiment in main.py
```python
# Edit main.py, find these lines:
RUN_BACKTEST = False
BUILD_DATASET = False
RUN_ML_EXPERIMENT = False

# Change to:
RUN_ML_EXPERIMENT = True  # ← Enable this
```

### Step 2: Run the experiment
```bash
python3 main.py
```

### Step 3: Read the comparison table
Should print something like:
```
================================================================================
BACKTEST COMPARISON: RULE-BASED vs ML-DERIVED CONFIDENCE
================================================================================

Metric                      Rules              ML             Δ
---
Number of Trades            150                145           -3.3%
Win Rate                    58.0%              60.7%         +4.7%
Avg Return per Trade        +1.23%             +1.45%        +17.9%
Total Return                +184.5%            +210.3%       +14.0%
...
```

**Interpretation:**
- If ML win rate > rules: ML picks better entry points
- If ML avg return > rules: ML more capital efficient
- Profit factor > 2.0 is strong

---

## Option 3: Run Unit Tests Only (Fast - 1 second)
Verify all ML components work correctly.

```bash
python3 test_ml_pipeline.py
```

**Output:**
```
Ran 11 tests in 0.058s
OK
```

**When to use:** Verify after code changes

---

## Important Notes

### ⚠️ yfinance may fail
The backtest will try to download 5 years of historical data for 43 symbols. If network is unavailable:
- Backtest generates 0 trades
- Comparison table shows empty results
- This is expected in isolated environments

### ✅ Training always works
The ML model training uses your existing dataset file (`data/ml_dataset_*.csv`), so it doesn't require network access.

### 📊 What gets compared?
1. **Rules-based:** Uses existing `rule_scorer` logic
2. **ML-based:** Uses trained LogisticRegression model

Both run on identical historical backtest (same symbols, same dates, same holding period).

---

## Troubleshooting

### Error: "No ML dataset found"
**Solution:** Generate dataset first
```bash
# Edit main.py
BUILD_DATASET = True

# Run
python3 main.py

# Then set BUILD_DATASET = False
```

### Error: "No module named sklearn"
**Solution:** Install scikit-learn
```bash
pip install scikit-learn==1.3.2
```

### Backtest takes forever (>30 minutes)
**Normal behavior:** Backtest downloads 5 years of data for 43 symbols.
- Use Option 1 (ml_validate.py) to skip backtest
- Or run in background: `python3 main.py &`

### Model accuracy seems low (45%)
**Normal:** The dataset has synthetic data and limited features.
- This is expected for baseline LogisticRegression
- Real improvement comes from better features, not higher accuracy

---

## Expected Results

### Model Training Metrics
```
Train Accuracy:    ~60%
Test Accuracy:     ~45%
Test Precision:    ~28%
Test Recall:       ~59%

Prediction distribution:
- Confidence 1: ~60% (low confidence)
- Confidence 2-3: ~20%
- Confidence 4-5: ~15% (high confidence)
```

### Backtest Comparison
Typically shows one of three outcomes:

1. **ML Wins** (rare)
   - Higher win rate
   - Higher avg return
   - Verdict: Consider deployment

2. **Rules Win** (common)
   - Rules more conservative
   - Better calibrated
   - Verdict: Keep rules logic

3. **Neutral** (common)
   - Similar metrics
   - Different tradeoffs
   - Verdict: More data needed

---

## Files Generated

After running experiment:
```
data/ml_dataset_*.csv       # Feature + label dataset
ml/train_model.py           # Training code
ml/predict.py               # Confidence mapping
ml/evaluate.py              # Backtest comparison
test_ml_pipeline.py         # Unit tests
ml_validate.py              # Quick validation
ml_demo.py                  # Full demo
```

---

## Next Steps

### If ML Improves Performance
```python
# Consider deploying ML model
# In scoring/rule_scorer.py or backtest/simple_backtest.py:
from ml.train_model import train_and_evaluate
from ml.predict import predict_confidence_scores
# Use ML predictions instead of rules
```

### If You Want to Iterate
1. Adjust probability thresholds in `ml/predict.py`
2. Retrain and compare
3. Repeat until satisfied

### For Production
1. Add cross-validation
2. Test on larger dataset
3. Add feature engineering
4. Implement hyperparameter search
5. Create monitoring dashboard

---

## Command Reference

```bash
# Quick validation (1 min)
python3 ml_validate.py

# Full experiment (10+ min)
python3 main.py  # with RUN_ML_EXPERIMENT = True

# Unit tests (1 sec)
python3 test_ml_pipeline.py

# Run demo (10+ min)
python3 ml_demo.py

# Build dataset first
python3 main.py  # with BUILD_DATASET = True

# Check latest dataset
ls -lh data/ml_dataset_*.csv
```

---

## Architecture Overview

```
main.py (entry point)
  │
  ├─ RUN_ML_EXPERIMENT = True
  │   │
  │   ├─ ml/train_model.py
  │   │   └─ LogisticRegression trained on 70% data
  │   │
  │   └─ ml/evaluate.py
  │       ├─ backtest.simple_backtest.py (rules)
  │       ├─ ml/predict.py + backtest with ML scores
  │       └─ comparison table printed
  │
  └─ Regular screener (default)
```

---

## Summary

| Option | Time | Use Case |
|--------|------|----------|
| ml_validate.py | 1 min | Quick check, no backtest |
| main.py (ML=True) | 10+ min | Full experiment |
| test_ml_pipeline.py | 1 sec | Unit tests |
| ml_demo.py | 10+ min | Full demo |

**Recommended:** Start with `ml_validate.py` to ensure ML training works, then run full experiment if interested.
