# QUICK REFERENCE: Policy System

## For Users: How to Use New Indicators

```python
from features.feature_engine import compute_features

# Original behavior (9 features)
features = compute_features(df)

# With new indicators (9 + 6 extended features)
features = compute_features(df, include_extended=True)

# Features available:
# Original: SMA20, SMA200, distance_to_sma, sma_slope, ATR, ATR%, volume_ratio, pullback_depth
# Extended: RSI, MACD, MACD_signal, MACD_hist, EMA12, EMA26, BB_upper, BB_middle, BB_lower, BB_width, ADX, OBV
```

## For Developers: How to Add a New Mode

### Example: Adding US Day Trading

1. **Create DayTradeHoldPolicy** (replace stub in `policies/hold_policy.py`)

```python
class DayTradeHoldPolicy(HoldPolicy):
    def min_hold_days(self) -> int:
        return 0  # Can exit same day
    
    def max_hold_days(self) -> int:
        return 1  # Must exit by end of day
    
    def allows_same_day_exit(self) -> bool:
        return True  # Required for day trading
```

2. **Register the scope** (update `policies/policy_factory.py`)

```python
SUPPORTED_SCOPES = {
    ("swing", "us", "equity"): True,
    ("daytrade", "us", "equity"): True,  # ← Add this line
    # ... rest of scopes
}
```

3. **Test it**

```python
from policies.policy_factory import create_policies_for_scope

# This now works!
policies = create_policies_for_scope("daytrade", "us")
assert isinstance(policies.hold_policy, DayTradeHoldPolicy)
```

## For Operators: How to Check What's Supported

```python
from policies.policy_factory import is_scope_supported, get_supported_scopes

# Check single scope
if is_scope_supported("swing", "us", "equity"):
    print("✅ US Swing is supported")

# Check what's available
for scope in get_supported_scopes():
    print(f"✅ {scope['mode']}/{scope['market']}/{scope['instrument']}")
```

## For Architects: Policy Interfaces

### HoldPolicy
- `min_hold_days()` → int (minimum holding period in days)
- `max_hold_days()` → int (maximum holding period in days)
- `allows_same_day_exit()` → bool (can exit on entry day)
- `validate_hold_period(holding_days, is_risk_reducing)` → (bool, str)

### ExitPolicy
- `evaluation_frequency()` → str ('eod', 'intraday', 'continuous')
- `get_exit_urgency(exit_type)` → str ('immediate', 'urgent', 'eod', 'optional')
- `get_execution_window()` → (int, int) (min_minutes, max_minutes after open)
- `supports_intraday_evaluation()` → bool

### EntryTimingPolicy
- `entry_frequency()` → str ('once_per_day', 'multiple_intraday', 'continuous')
- `get_entry_window_minutes_before_close()` → int
- `supports_intraday_entry()` → bool

### MarketHoursPolicy
- `get_timezone()` → str ('America/New_York', 'Asia/Kolkata', etc.)
- `get_market_open_time()` → time
- `get_market_close_time()` → time
- `is_24x7_market()` → bool
- `has_market_close()` → bool

## Files to Know

### Core Policy Files
- `policies/base.py` - Interface definitions
- `policies/hold_policy.py` - Hold-related policies
- `policies/exit_policy.py` - Exit-related policies
- `policies/entry_timing_policy.py` - Entry timing policies
- `policies/market_hours_policy.py` - Market hours policies
- `policies/policy_factory.py` - Factory and registry

### Integration Files
- `runtime_config.py` - Policy-driven runtime setup
- `risk/trade_intent_guard.py` - Uses HoldPolicy (line ~50)
- `features/feature_engine.py` - Extended indicators (include_extended param)
- `startup/validator.py` - Policy support validation (phase 0)

### Documentation
- `EXECUTIVE_SUMMARY.md` - High-level overview
- `FUTURE_PROOFING_REFACTOR_SUMMARY.md` - Detailed technical docs
- `DEPLOYMENT_CHECKLIST.md` - Verification results

### Testing
- `verify_refactor.py` - Comprehensive verification suite
- `tests/test_trade_intent_guard.py` - Updated with SwingHoldPolicy

## Common Tasks

### Check if scope is supported
```python
from policies.policy_factory import is_scope_supported
is_scope_supported("swing", "us", "equity")  # True
is_scope_supported("daytrade", "us", "equity")  # False
```

### Create policies for US Swing
```python
from policies.policy_factory import create_policies_for_scope
policies = create_policies_for_scope("swing", "us")
# policies.hold_policy, policies.exit_policy, policies.entry_timing_policy, policies.market_hours_policy
```

### Use extended indicators
```python
from features.feature_engine import compute_features
features = compute_features(price_data, include_extended=True)
# Now has RSI, MACD, EMA, Bollinger Bands, ADX, OBV
```

### Check hold period constraints
```python
hold_policy = SwingHoldPolicy()
min_hold = hold_policy.min_hold_days()  # 2
max_hold = hold_policy.max_hold_days()  # 20
same_day_allowed = hold_policy.allows_same_day_exit()  # False
```

## Error Messages

### "Unsupported Mode/Market Combination"
This means you tried to use a mode/market that isn't implemented yet.

**Solution:** 
1. Check `SUPPORTED_SCOPES` in `policies/policy_factory.py`
2. If you need it, implement the policy stubs
3. Set the scope to True in registry

### "Policy Not Implemented"
A policy stub was called but not fully implemented.

**Solution:**
1. Find the stub in `policies/` folder
2. Replace NotImplementedError with actual implementation
3. Update SUPPORTED_SCOPES registry

### "Module Not Found: policies"
You need to be in the trading_app directory.

**Solution:**
```bash
cd /Users/mohan/Documents/SandBox/test/trading_app
python3 your_script.py
```

---

## Quick Verification

To verify everything works:

```bash
cd /Users/mohan/Documents/SandBox/test/trading_app
python3 verify_refactor.py
# Should output: ✅ ALL VERIFICATION TESTS PASSED
```

To run demo:

```bash
python3 demo_architecture.py
# Should complete successfully with all demos running
```

---

**Status: ✅ Ready to Use**

---

## 2. Graceful Failure Handling - No More Crashes ✅

### Implementation:
```python
# Each symbol wrapped in try/except
try:
    load → compute → score → store
except Exception as e:
    logger.error(f"{symbol}: {type(e).__name__}: {e}")
    failed_symbols.append((symbol, str(e)))
    continue  # Process next symbol
```

### Result:
- One symbol fails = other symbols still process
- Summary shows:
  - ✅ Scored symbols: count
  - ⊘ Skipped symbols: reason breakdown
  - ✗ Failed symbols: error details

### Example:
```
Summary: 43 scanned, 41 scored, 1 skipped, 1 failed

Skipped reasons:
  no_data: 1

Failed symbols (unexpected errors):
  UNKNOWN: SymbolNotFoundError: Symbol not found
```

---

## 3. Configuration Centralization - No Magic Numbers ✅

### All Parameters Moved to config/settings.py:

**NEW - Logging:**
```python
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
```

**NEW - Validation:**
```python
MIN_HISTORY_DAYS = 210
SMA_SLOPE_WINDOW = 5
THRESHOLD_SMA_SLOPE = 0.0
```

**EXISTING:**
- START_CAPITAL, LOOKBACK_DAYS
- SMA_SHORT, SMA_LONG
- ATR_PERIOD, VOLUME_LOOKBACK
- THRESHOLD_PULLBACK, THRESHOLD_VOLUME_RATIO, THRESHOLD_ATR_PCT
- TOP_N_CANDIDATES, PRINT_WIDTH

**Result:** Change 1 file = entire system adapts

---

## 4. Data Validation - Explicit Checks ✅

### Three-Stage Validation Pipeline:

**Stage 1: Data Loading**
```python
✓ Check if data is None/empty
✓ Check if data is Series (too small)
✓ Check if all values NaN
→ Log warning, return None, skip symbol
```

**Stage 2: Feature Computation**
```python
✓ Check if input None/empty
✓ Check if >= MIN_HISTORY_DAYS
✓ Check if output has NaN
→ Log error, return None, skip symbol
```

**Stage 3: Scoring**
```python
✓ Check if input None
✓ Check required columns present
✓ Check for NaN in features
→ Log error, return None, skip symbol
```

**Stage 4: Main Pipeline**
```python
✓ Check if latest_row has NaN
✓ Check if confidence is None
→ Skip symbol with reason, continue
```

---

## 5. Deterministic Output - Same Results Always ✅

### Two-Key Sorting:
```python
# BEFORE (non-deterministic - ties are random):
sort_values('confidence', ascending=False)

# AFTER (deterministic - always same order):
sort_values(by=['confidence', 'symbol'], ascending=[False, True])
```

### Example Output (Reproducible):
```
Rank  Symbol  Conf
1     BA      5
2     IBM     5       ← Confidence 5, alphabetical order
3     AAPL    4
4     ADBE    4       ← Confidence 4, alphabetical order
5     BAC     4
6     BRK.B   4
```

**Same data** → **Same output** every time ✓

---

## 6. Documentation - Clear Intent ✅

### Module-Level Docstrings:
- `data/price_loader.py` - Data loading with validation
- `features/feature_engine.py` - Technical indicator computation
- `scoring/rule_scorer.py` - Rule-based scoring logic
- `main.py` - Orchestration pipeline
- `demo.py` - Synthetic demonstration

### Function-Level Docstrings:
Each public function includes:
- Description of purpose
- Parameter documentation
- Return value documentation
- Example of typical usage

**Example:**
```python
def score_symbol(features_row: pd.Series) -> Optional[int]:
    """
    Score symbol based on 5 transparent rules.
    
    Rules (each adds 1 to confidence):
    1. Close > SMA200 (long-term uptrend)
    2. SMA20 slope > 0 (short-term momentum)
    3. Pullback < 5% (shallow dip)
    4. Volume ratio > 1.2 (volume surge)
    5. ATR% < 3% (stability)
    
    Returns:
        Confidence 1-5, or None if validation fails
    """
```

---

## Files Modified Summary

| File | Lines Changed | What Changed |
|------|---|---|
| config/settings.py | +20 | Added logging + validation constants |
| data/price_loader.py | ~60 | Logging + validation + type hints |
| features/feature_engine.py | ~80 | Logging + validation + config import |
| scoring/rule_scorer.py | ~50 | Logging + validation + config import |
| main.py | ~180 | Complete rewrite: logging, deterministic sort, errors |
| demo.py | ~160 | Complete rewrite: logging, validation, sorting |

**NEW Documentation Files:**
- HARDENING_SUMMARY.md - Overview of improvements
- BEFORE_AFTER.md - Detailed code comparisons
- COMPLETION_CHECKLIST.md - Requirements verification
- QUICK_REFERENCE.md - This file

---

## Quality Verification ✅

```bash
# Syntax Check
python3 -m py_compile [all modified files]
Result: ✅ All compile successfully

# Runtime Test (Demo)
python3 demo.py
Result: ✅ All 43 symbols processed
        ✅ Deterministic ranking verified
        ✅ Logging output formatted correctly

# Python Version
python3 --version
Result: Python 3.9
        ✅ Type hints compatible (Optional[] not |)
```

---

## Production Readiness ✅

- [x] Logging configured for visibility
- [x] Errors handled gracefully
- [x] Configuration centralized
- [x] Data validated explicitly
- [x] Output deterministic
- [x] Code documented clearly
- [x] Python 3.9 compatible
- [x] No dependencies added
- [x] Same behavior preserved
- [x] Tested end-to-end

**Status: READY FOR PRODUCTION** ✅

---

## How to Use

### Run Production Screener:
```bash
python3 main.py
```

### Run Demo (No Network):
```bash
python3 demo.py
```

### Change Log Level:
Edit `config/settings.py`:
```python
LOG_LEVEL = 'DEBUG'     # Detailed output
LOG_LEVEL = 'INFO'      # Normal (default)
LOG_LEVEL = 'WARNING'   # Minimal
```

### Adjust Thresholds:
Edit `config/settings.py`:
```python
THRESHOLD_PULLBACK = 0.08       # More aggressive pullback
THRESHOLD_VOLUME_RATIO = 1.5    # Stricter volume requirement
MIN_HISTORY_DAYS = 180          # Fewer history days needed
```

---

## Key Takeaways

1. **Logging:** All visibility now through structured logging
2. **Reliability:** Failures don't crash the system
3. **Configuration:** Change parameters in one place
4. **Validation:** Bad data caught early at each stage
5. **Reproducibility:** Same output every run
6. **Readability:** Clear documentation throughout

---

**Status:** ✅ Complete - Ready for Production Use
