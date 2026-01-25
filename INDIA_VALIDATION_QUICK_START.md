# India Validation Quick Start

**Status**: 5-Step Infrastructure Complete ✅  
**Branch**: `india-market-port`  
**Next**: Paper trading with rules-only mode (observation phase)  

---

## What's Now Available

### 1. Configuration Flags
```python
from config.settings import (
    INDIA_RULES_ONLY,               # True = ML disabled, rules-based only
    INDIA_MIN_OBSERVATION_DAYS,     # 20 = minimum baseline period
    INDIA_OBSERVATION_LOG_DIR,      # "logs/india_observations"
    INDIA_ML_VALIDATION_ENABLED,    # False = require explicit --run-india-ml-validation
)
```

### 2. Daily Observation Logging
```python
from monitoring.india_observation_log import IndiaObservationLogger

logger = IndiaObservationLogger()

# At end of each trading day:
logger.record_observation(
    symbols_scanned=["RELIANCE", "INFY", "WIPRO", ...],
    signals_generated=5,
    signals_rejected=2,
    trades_executed=3,
    trades_rejected_risk=0,
    trades_rejected_confidence=2,
    avg_confidence_executed=0.72,
    avg_confidence_rejected=0.31,
    portfolio_heat=0.15,  # 15% of capital at risk
    daily_return=0.0045,  # +0.45%
    max_drawdown=0.02     # 2% max drawdown
)

# Check status:
status = logger.get_observation_status()
# Returns: {total_observation_days, last_observation_date, ready_for_ml_validation}
```

### 3. Baseline Report (After 20 Days)
```python
from reports.india_rules_baseline import IndiaRulesBaseline

reporter = IndiaRulesBaseline()

# After 20+ trading days:
md_path, csv_path = reporter.generate_report(min_days=20)
# Outputs:
#   - Markdown: reports/india_rules_baseline_20240115_160000.md
#   - CSV: reports/india_rules_baseline_20240115_160000.csv
```

### 4. ML Validation Prep (After Baseline + Approval)
```python
from validation.india_ml_validation_prep import IndiaMLValidationPrep

prep = IndiaMLValidationPrep()

# Check if ready (raises error if not):
readiness = prep.check_validation_readiness(min_days=20)

# Prepare model:
model, metrics = prep.prepare_validation_model()
# Saves: validation/india_models/india_model_validation_20240115_160000.pkl
```

---

## Execution Flow

```
1. START RULES-ONLY TRADING (Day 1)
   └─ INDIA_RULES_ONLY = True
   └─ Only rules-based signals (no ML)
   └─ Use MARKET_MODE = "INDIA"

2. DAILY OBSERVATION LOGGING (Days 1-20)
   └─ logger.record_observation(...) at end of each day
   └─ Logs stored in logs/india_observations/
   └─ Tracks: signals, trades, confidence, risk

3. GENERATE BASELINE REPORT (After Day 20)
   └─ reporter.generate_report(min_days=20)
   └─ Review: win rate, returns, drawdown, risk
   └─ Creates audit trail of rules-only performance

4. ML VALIDATION PREP (After Approval)
   └─ Disable rules-only: INDIA_RULES_ONLY = False
   └─ Run: python main.py --run-india-ml-validation
   └─ Train fresh India ML model
   └─ Save timestamped snapshot

5. VALIDATION PHASE (Future)
   └─ Compare ML vs rules performance
   └─ A/B test signals
   └─ Make deployment decision
```

---

## Safety Guards (Automatic)

| Guard | Behavior |
|-------|----------|
| **Rules-Only Default** | ML disabled by default (`INDIA_RULES_ONLY = True`) |
| **Minimum Period** | Can't prepare ML before 20 trading days |
| **Data Quality** | Checks for missing observation logs |
| **Explicit Approval** | Requires `--run-india-ml-validation` CLI flag |
| **Training Samples** | Won't train on < 50 samples |
| **Model Isolation** | Fresh model (not copied from US) |

---

## Configuration for Paper Trading

In `config/settings.py`:

```python
# Switch to India
MARKET_MODE = "INDIA"

# Keep rules-only mode enabled
INDIA_RULES_ONLY = True

# Set baseline period
INDIA_MIN_OBSERVATION_DAYS = 20

# Disable ML validation until ready
INDIA_ML_VALIDATION_ENABLED = False

# Keep US unchanged
# (US_MODE not affected, MARKET_MODE is the selector)
```

---

## Testing

### Verify Config
```bash
python -c "from config.settings import INDIA_RULES_ONLY; print(f'Rules-only mode: {INDIA_RULES_ONLY}')"
```

### Test Observation Logging
```bash
python -c "
from monitoring.india_observation_log import IndiaObservationLogger
logger = IndiaObservationLogger()
logger.record_observation(symbols_scanned=['RELIANCE'], signals_generated=1, 
  signals_rejected=0, trades_executed=1, trades_rejected_risk=0, 
  trades_rejected_confidence=0, avg_confidence_executed=0.8, 
  avg_confidence_rejected=0.0, portfolio_heat=0.1, daily_return=0.001, 
  max_drawdown=0.01)
status = logger.get_observation_status()
print(f'Observation days: {status[\"total_observation_days\"]}')
"
```

### Test Baseline Report (After 20 Days)
```bash
python -c "
from reports.india_rules_baseline import IndiaRulesBaseline
reporter = IndiaRulesBaseline()
try:
    reporter.generate_report(min_days=20)
    print('Report generated successfully')
except ValueError as e:
    print(f'Not ready: {e}')
"
```

---

## Files Created

| File | Size | Purpose |
|------|------|---------|
| monitoring/india_observation_log.py | 230 lines | Daily observation tracking (JSONL) |
| reports/india_rules_baseline.py | 250 lines | Baseline report generation |
| validation/india_ml_validation_prep.py | 300 lines | ML readiness checks + training |
| config/settings.py | +7 lines modified | 3 new config flags |
| INDIA_VALIDATION_STEPS.md | 400 lines | Comprehensive documentation |

---

## Key Points

✅ **Rules-only first**: ML disabled by default  
✅ **Observation-focused**: Track all signals and trades  
✅ **Safety-gated**: Can't deploy ML without 20 days baseline  
✅ **Audit trail**: Every decision logged and timestamped  
✅ **Isolated**: All work on india-market-port branch (main unchanged)  
✅ **Ready to deploy**: Infrastructure complete, can start paper trading now  

---

## Documentation

- **Full guide**: See `INDIA_VALIDATION_STEPS.md` (comprehensive 5-step breakdown)
- **Quick reference**: This file
- **Code comments**: Each module has detailed docstrings

---

## Next Action

**Start India rules-only paper trading**:
1. Set `MARKET_MODE = "INDIA"` in config/settings.py
2. Confirm `INDIA_RULES_ONLY = True`
3. Initialize paper trading with NIFTY 50 universe
4. Call `logger.record_observation(...)` at end of each day
5. After 20 days: generate baseline report
6. After approval: prepare ML model

**No US changes** - this infrastructure is completely isolated to india-market-port branch.
