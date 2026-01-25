# India Rules-Only Paper Trading - Startup Documentation

**Status**: ✅ OPERATIONAL  
**Date**: January 2026  
**Mode**: INDIA_RULES_ONLY = True (ML disabled)  
**Universe**: NIFTY 50 (50 stocks)  
**Capital**: $100,000  

---

## System Status

✅ **All startup checks passed**

```
[1] Configuration: MARKET_MODE = INDIA, INDIA_RULES_ONLY = True
[2] Universe: NIFTY 50 loaded (50 symbols)
[3] Observation Log: Writable (logs/india_observations)
[4] RiskManager: Initialized with India conservative parameters
[5] ML Status: DISABLED (using rules-only confidence)
[6] Feature Engine: IndiaFeatureNormalizer ready
[7] Data Loader: NSE + Yahoo Finance fallback ready
```

---

## How It Works

### Daily Execution Flow

```
START
  ↓
[STARTUP VERIFICATION]
  - Observation log writable? ✓
  - RiskManager initialized? ✓
  - ML disabled? ✓
  ↓
[SCAN UNIVERSE]
  - Load NIFTY 50 symbols
  - Get 1 year of price history
  - Calculate technical indicators
  ↓
[GENERATE SIGNALS]
  - Score each symbol (0-5 confidence)
  - Filter minimum confidence = 3
  - Take top 20 candidates
  ↓
[EXECUTE WITH RISK LIMITS]
  - Check position sizing limit
  - Verify margin availability
  - Apply execution realism (slippage, fills)
  ↓
[LOG DAILY OBSERVATION]
  - Record: signals generated, trades attempted, approved, rejected
  - Track: confidence distribution, portfolio heat, daily return
  - Store: JSONL format (immutable append-only)
  ↓
[PRINT EXECUTION SUMMARY]
  - Signals generated
  - Trades attempted
  - Trades approved
  - Rejections by reason (risk vs confidence)
  ↓
END
```

### Key Safety Features

| Feature | Implementation |
|---------|-----------------|
| **ML Disabled** | INDIA_RULES_ONLY = True (default, cannot be overridden in daily run) |
| **Risk Limits** | RiskManager enforces position sizing based on confidence |
| **Audit Trail** | All signals and trades logged to JSONL (immutable) |
| **Observation Log** | Daily metrics captured for baseline establishment |
| **Safety Default** | Rules-only mode only (no ML even if 20 days of data exists) |
| **Execution Realism** | Slippage, fills, and market impact modeled |

---

## Running India Rules-Only Paper Trading

### Prerequisites

```bash
# Validate startup (recommended before each run)
python3 validate_india_startup.py

# Output should show all 7 checks passing
```

### Start Trading

```bash
# Run daily execution loop
python3 main.py

# Or use background execution (recommended for production)
nohup python3 main.py > logs/india_trading.log 2>&1 &
```

### What Gets Output

**Startup Banner**:
```
========...========
[INDIA] Phase I — Rules-Only Observation Mode
Status: INDIA_RULES_ONLY = True
Status: INDIA_ML_VALIDATION_ENABLED = False
```

**Verification**:
```
[INDIA] Performing startup verification...
✓ Observation log writable
  Directory: logs/india_observations
  Observation days recorded: N
✓ RiskManager initialized with India parameters
  Starting capital: $100,000
✓ ML disabled (INDIA_RULES_ONLY = True)
```

**Daily Execution**:
```
[INDIA] Scanning 50 symbols...
  RELIANCE: confidence=4
  INFY: confidence=4
  HDFCBANK: confidence=3
  ...
[INDIA] Signals generated: 25 total, 8 executable

EXECUTING SIGNALS
  RELIANCE: EXECUTED (confidence=4, order=12345)
  INFY: REJECTED (risk) - max position size
  HDFCBANK: EXECUTED (confidence=3, order=12346)
  ...
```

**Shutdown Summary**:
```
[INDIA] EXECUTION SUMMARY
Signals Generated: 25
Trades Attempted: 8
Trades Approved: 6
Trades Rejected (Risk): 1
Trades Rejected (Confidence): 1
Total Rejected: 2

✓ Rules-only observation day complete
```

**Observation Log**:
```json
{
  "timestamp": "2026-01-25T16:00:00",
  "date": "2026-01-25",
  "market_mode": "INDIA",
  "validation_phase": "RULES_ONLY_MODE",
  "symbols_scanned_count": 50,
  "signals_generated": 25,
  "signals_rejected": 17,
  "trades_executed": 6,
  "trades_rejected_risk": 1,
  "trades_rejected_confidence": 1,
  "avg_confidence_executed": 0.75,
  "avg_confidence_rejected": 0.31,
  "portfolio_heat_pct": 12.0,
  "daily_return_pct": 0.45,
  "max_drawdown_pct": 2.0,
  "notes": "Rules-only observation day (INDIA_RULES_ONLY=True)"
}
```

---

## Configuration

**Location**: `config/settings.py`

```python
# Market mode
MARKET_MODE = "INDIA"            # Switch to India

# Rules-only mode
INDIA_RULES_ONLY = True          # ML disabled
INDIA_ML_VALIDATION_ENABLED = False  # Requires explicit --run-india-ml-validation

# Observation tracking
INDIA_MIN_OBSERVATION_DAYS = 20  # Minimum before ML validation allowed
INDIA_OBSERVATION_LOG_DIR = "logs/india_observations"

# Capital
START_CAPITAL = 100000           # $100k starting equity
```

---

## File Locations

| Component | Location |
|-----------|----------|
| **Main Script** | main.py |
| **Startup Validator** | validate_india_startup.py |
| **Config** | config/settings.py |
| **Universe** | universe/india_universe.py |
| **Feature Engine** | features/india_feature_engine.py |
| **Data Loader** | data/india_data_loader.py |
| **Observation Log** | monitoring/india_observation_log.py |
| **Baseline Reporter** | reports/india_rules_baseline.py |
| **ML Validation Prep** | validation/india_ml_validation_prep.py |
| **Risk Manager** | risk/risk_manager.py |
| **Execution Logger** | broker/execution_logger.py |
| **Logs Directory** | logs/ (auto-created) |
| **Observations** | logs/india_observations/ (auto-created) |

---

## Baseline Establishment Timeline

| Milestone | Status | Timeline |
|-----------|--------|----------|
| **Day 1-20** | Rules-only trading | In progress |
| **Observations** | Daily JSONL logs | Auto-recorded |
| **After 20 Days** | Generate baseline report | Run: `reporter.generate_report(min_days=20)` |
| **Review Baseline** | Confirm performance acceptable | Human review required |
| **ML Validation** | (If approved) Train fresh India model | Future: `--run-india-ml-validation` |

---

## Monitoring & Observation

### Daily Observation Record

Each trading day captures:
- Date/time
- Symbols scanned (50 NIFTY stocks)
- Signals generated
- Signals rejected (why: risk vs confidence)
- Trades executed
- Trades rejected (why: risk vs confidence)
- Average confidence (executed vs rejected)
- Portfolio heat (% capital at risk)
- Daily return %
- Max intraday drawdown
- Notes

### Accessing Observations

```python
from monitoring.india_observation_log import IndiaObservationLogger

logger = IndiaObservationLogger()

# Check status
status = logger.get_observation_status()
print(f"Days recorded: {status['total_observation_days']}")
print(f"Ready for ML: {status['ready_for_ml_validation']}")

# Get recent observations
recent = logger.get_recent_observations(days=5)
for obs in recent:
    print(f"{obs['date']}: {obs['trades_executed']} trades, "
          f"{obs['daily_return_pct']}% return")
```

### After 20 Days: Generate Baseline Report

```python
from reports.india_rules_baseline import IndiaRulesBaseline

reporter = IndiaRulesBaseline()
md_path, csv_path = reporter.generate_report(min_days=20)
# Outputs:
#   - reports/india_rules_baseline_20260225_160000.md (metrics)
#   - reports/india_rules_baseline_20260225_160000.csv (data)
```

---

## Safety & Risk Management

### Risk Limits

- **Position Size**: Based on confidence (higher confidence = larger position)
- **Portfolio Heat**: Max 20% of capital at risk simultaneously
- **Margin**: Respects available margin before each trade
- **Slippage**: 2 bps modeled for execution realism
- **Stops**: 2% stop loss assumed for heat calculation

### Execution Realism

- **Fill Rates**: 95% fill rate assumed
- **Slippage**: 2-5 bps depending on symbol liquidity
- **Market Impact**: Small for NIFTY stocks (high liquidity)
- **Timing**: Orders filled in queue order (FIFO)

### Audit Trail

- **Immutable**: JSONL format (append-only, cannot be edited)
- **Complete**: Every signal, every trade, every rejection logged
- **Timestamped**: All records include timestamp
- **Searchable**: JSON format easy to query and analyze

---

## Troubleshooting

### "Configuration check failed: MARKET_MODE should be INDIA"

**Fix**: Set `MARKET_MODE = "INDIA"` in config/settings.py

```python
# config/settings.py, line 13
MARKET_MODE = "INDIA"  # Change from "US" to "INDIA"
```

### "Observation log initialization failed"

**Fix**: Ensure logs directory is writable

```bash
mkdir -p logs/india_observations
chmod 755 logs
```

### "RiskManager initialization failed"

**Fix**: Check that risk/ module exists and has proper imports

```bash
python3 -c "from risk.risk_manager import RiskManager; print('✓ OK')"
```

### "Failed to load India universe"

**Fix**: Verify universe/india_universe.py exists and is properly formatted

```bash
python3 -c "from universe.india_universe import NIFTY_50; print(len(NIFTY_50))"
```

### "No signals generated"

**Possible causes**:
- Market data not available (holiday/market closed)
- All symbols failed data loading
- All symbols have low confidence scores
- Universe has insufficient history

**Solution**: Check logs for details

```bash
tail -50 logs/india_trading.log
```

---

## Next Steps After 20 Days

### 1. Generate Baseline Report

```python
from reports.india_rules_baseline import IndiaRulesBaseline
reporter = IndiaRulesBaseline()
md_path, csv_path = reporter.generate_report(min_days=20)
```

### 2. Review Performance Metrics

Key metrics to check:
- Win rate (should be > 50%)
- Average daily return
- Max drawdown
- Portfolio heat distribution
- Rejection reasons

### 3. Approve or Adjust Rules

- If performance good: Proceed to ML validation
- If performance needs improvement: Adjust signal rules first

### 4. ML Validation (If Approved)

```python
from validation.india_ml_validation_prep import IndiaMLValidationPrep
prep = IndiaMLValidationPrep()
readiness = prep.check_validation_readiness(min_days=20)
model, metrics = prep.prepare_validation_model()
```

---

## Summary

✅ **India rules-only paper trading is now operational**

- MARKET_MODE = INDIA
- INDIA_RULES_ONLY = True (ML disabled)
- Configuration verified
- Universe ready (NIFTY 50)
- Observation logging ready
- Risk management active
- Daily execution loop ready

**To start**: Run `python3 main.py`

**To validate**: Run `python3 validate_india_startup.py`

**All safety guards active** - ready for production operation
