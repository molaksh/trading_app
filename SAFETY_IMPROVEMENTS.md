# Safety Improvements: Institution-Grade Risk Management

## Overview

Four surgical, high-impact safety enhancements were applied to the `RiskManager` to harden the risk engine to institution-grade standards. All improvements follow fail-safe design principles and maintain backward compatibility.

**Status**: ✅ Complete | All 44 tests passing | Deployed to main

---

## Safety Improvement 1: Fail-Closed Confidence Handling

### Problem
Invalid confidence scores defaulted to a 1.0 multiplier (neutral sizing), which is unsafe. A misconfigured or corrupted confidence value would still produce a full-sized position.

### Solution
Changed default multiplier for invalid confidence from **1.0 to 0.0** (fail-closed).

### Implementation
**File**: `risk/risk_manager.py` - `_get_confidence_multiplier()` method

```python
def _get_confidence_multiplier(self, confidence: int) -> float:
    # If ML sizing is disabled, use neutral 1.0 multiplier
    if not ENABLE_ML_SIZING:
        return 1.0
    
    # Validate confidence is in valid range
    if confidence < 1 or confidence > 5:
        logger.warning(
            f"Invalid confidence level: {confidence} (must be 1-5), "
            f"using 0.0 (fail-closed, zero position size)"
        )
        # Fail-closed: invalid confidence results in zero position size
        return 0.0
    
    # Valid confidence: use configured multiplier
    multiplier = CONFIDENCE_RISK_MULTIPLIER.get(confidence, 0.0)
    if multiplier == 0.0:
        logger.warning(
            f"Confidence {confidence} not found in multiplier map, "
            f"using 0.0 (fail-closed)"
        )
    
    return multiplier
```

### Behavior Change
- **Before**: Invalid confidence → multiplier = 1.0 → full-sized position
- **After**: Invalid confidence → multiplier = 0.0 → zero position size (REJECTED)
- **Logging**: Warning logged for all invalid confidence values for visibility

### Impact
- **Safety**: Failures default to the safest option (no trade)
- **Risk**: Eliminates positions from corrupted ML signals
- **Transparency**: Explicit logging ensures operators know when confidence fails

### Example
```
Invalid confidence score 99:
  - Old: 1% risk position opened (UNSAFE)
  - New: Trade rejected, zero position (SAFE) ✓
  - Log: "Invalid confidence level: 99 (must be 1-5), using 0.0 (fail-closed, zero position size)"
```

---

## Safety Improvement 2: Risk-Based Per-Symbol Exposure

### Problem
Per-symbol exposure was calculated as **notional value** (position_size × entry_price), not risk. This allowed large positions at low risk to exceed limits while small positions at high risk were constrained.

### Solution
Changed to **risk-amount-based** calculation: `proposed_symbol_risk = current_symbol_risk + new_risk_amount`

### Implementation
**File**: `risk/risk_manager.py` - `evaluate_trade()` method, Check 6

```python
# Check 6: Per-symbol exposure limit (RISK-based, not notional)
# Get current risk amount for symbol (sum of all open positions' risk)
current_symbol_risk = sum(
    pos.risk_amount
    for pos in self.portfolio.open_positions.get(symbol, [])
) if symbol in self.portfolio.open_positions else 0.0

proposed_symbol_risk = current_symbol_risk + risk_amount
max_symbol_risk = MAX_RISK_PER_SYMBOL * self.portfolio.current_equity

if proposed_symbol_risk > max_symbol_risk:
    proposed_symbol_risk_pct = proposed_symbol_risk / self.portfolio.current_equity
    reason = (
        f"Per-symbol risk exposure limit exceeded "
        f"({proposed_symbol_risk_pct:.2%} > {MAX_RISK_PER_SYMBOL:.2%})"
    )
    self._record_rejection("per_symbol_exposure", reason)
    return TradeDecision(False, 0.0, 0.0, reason)
```

### Configuration
**File**: `config/settings.py`
```python
MAX_RISK_PER_SYMBOL = 0.02      # Max 2% risk concentration per symbol
```

### Behavior Change
**Example Scenario** (100k equity, MAX_RISK_PER_SYMBOL = 2%):

| Scenario | Old Logic (Notional) | New Logic (Risk-Based) |
|----------|----------------------|------------------------|
| 1000 shares @ $150 | OK (15k notional = 15%) | Check: actual risk % |
| 10 shares @ $150 | OK (1.5k notional = 1.5%) | Check: actual risk % |
| Current 1% risk + New 1.25% risk | Both OK separately | **REJECTED** (2.25% > 2%) ✓ |

### Impact
- **Risk Accuracy**: Per-symbol limits now bound actual risk exposure, not position value
- **Concentration Control**: Prevents excessive risk concentration regardless of position size
- **Conservative**: More alignment with risk management philosophy
- **Enforcement**: Ensures risk limits are meaningful and enforced

### Test Coverage
```python
def test_rejection_per_symbol_exposure(self):
    # Setup: 1% risk in AAPL
    self.portfolio.open_trade(symbol="AAPL", risk_amount=1000.0)
    
    # Try: Add 1.25% risk (confidence=5 → 125% × 1% = 1.25%)
    decision = self.risk_manager.evaluate_trade(
        symbol="AAPL", confidence=5, ...
    )
    
    # Result: REJECTED (2.25% > 2% limit) ✓
    self.assertFalse(decision.approved)
```

---

## Safety Improvement 3: ML Sizing Toggle (ENABLE_ML_SIZING)

### Problem
No way to disable confidence-based sizing in production without code changes. Emergency situations require toggling ML adjustments without redeployment.

### Solution
Added `ENABLE_ML_SIZING` configuration flag to toggle ML-based position sizing on/off.

### Implementation

**File**: `config/settings.py`
```python
# ML-based confidence sizing control
# When disabled: confidence multiplier always uses 1.0 (neutral sizing)
# When enabled: confidence multiplier respected from CONFIDENCE_RISK_MULTIPLIER
ENABLE_ML_SIZING = True          # Set to False to disable confidence-based scaling
```

**File**: `risk/risk_manager.py` - `_get_confidence_multiplier()` method
```python
def _get_confidence_multiplier(self, confidence: int) -> float:
    # If ML sizing is disabled, use neutral 1.0 multiplier
    if not ENABLE_ML_SIZING:
        return 1.0  # Neutral sizing, ignore confidence
    
    # ML sizing enabled: use confidence-based multiplier
    # ... rest of confidence logic ...
```

### Configuration Options

| Setting | Behavior | Use Case |
|---------|----------|----------|
| `ENABLE_ML_SIZING = True` | Confidence adjusts position size (1-5 scores) | Normal trading with ML guidance |
| `ENABLE_ML_SIZING = False` | All trades use 1.0 multiplier (neutral) | Conservative/safe mode, ML disabled |

### Behavior Change
**With ENABLE_ML_SIZING = True** (default):
- Confidence 1 → 0.25× risk (25% of base)
- Confidence 5 → 1.25× risk (125% of base)

**With ENABLE_ML_SIZING = False**:
- All confidence levels → 1.0× risk (100% of base, neutral)
- ML adjustments ignored

### Impact
- **Flexibility**: Toggle ML-based sizing without code changes
- **Emergency Response**: Quickly switch to neutral sizing if ML is unreliable
- **Backward Compatible**: Defaults to True (existing behavior unchanged)
- **Configuration-Driven**: Controlled via settings.py, no hardcoding

### Example Emergency Response
```python
# In settings.py or config loading:
ENABLE_ML_SIZING = False  # Disable ML sizing due to signal degradation

# All trades now use neutral 1.0 multiplier
# Risk remains: 1% per trade regardless of confidence score
```

---

## Safety Improvement 4: Entry Price Sanity Hardening

### Problem
No validation on entry prices. Invalid prices (negative, zero, or absurdly large) could slip through and cause catastrophic calculation errors downstream.

### Solution
Added two fail-fast validation checks before position sizing calculations:
1. `entry_price <= 0` → REJECT
2. `entry_price > current_equity` → REJECT

### Implementation
**File**: `risk/risk_manager.py` - `evaluate_trade()` method, Check 4

```python
# Safety Check 4: Entry price sanity hardening
# Reject trades where entry_price <= 0 or entry_price > current_equity
if entry_price <= 0:
    reason = f"Invalid entry price: {entry_price} (must be > 0)"
    self._record_rejection("invalid_entry_price", reason)
    return TradeDecision(False, 0.0, 0.0, reason)

if entry_price > self.portfolio.current_equity:
    reason = (
        f"Entry price exceeds account equity: "
        f"${entry_price:.2f} > ${self.portfolio.current_equity:.2f}"
    )
    self._record_rejection("entry_price_exceeds_equity", reason)
    return TradeDecision(False, 0.0, 0.0, reason)
```

### Placement
Inserted as **Check 4** (right after daily trade limit), before position sizing calculations:

1. Consecutive losses kill switch
2. Daily loss kill switch
3. Daily trade limit
4. **Entry price sanity** ← NEW (fail-fast)
5. Position size calculation
6. Per-symbol exposure
7. Portfolio heat

### Behavior
| Entry Price | Result | Reason |
|-------------|--------|--------|
| -150.00 | REJECTED | Price must be > 0 |
| 0.00 | REJECTED | Price must be > 0 |
| 150.00 (equity=100k) | APPROVED | Valid |
| 150,000.00 (equity=100k) | REJECTED | Price > equity |

### Impact
- **Data Quality**: Prevents bad prices from corrupting calculations
- **Fail-Fast**: Rejects invalid prices immediately
- **Clear Logging**: Specific rejection reason for debugging
- **Upstream**: Forces data validation at entry point
- **Robustness**: Protects against broker API errors or data corruption

### Test Coverage
```python
def test_rejection_invalid_entry_price(self):
    # Test negative price
    decision = self.risk_manager.evaluate_trade(
        symbol="AAPL",
        entry_price=-150.0,  # Invalid
        ...
    )
    self.assertFalse(decision.approved)
    self.assertIn("Invalid entry price", decision.reason)
    
    # Test price > equity
    decision = self.risk_manager.evaluate_trade(
        symbol="AAPL",
        entry_price=150_000.0,  # > 100k equity
        ...
    )
    self.assertFalse(decision.approved)
    self.assertIn("exceeds account equity", decision.reason)
```

---

## Testing & Validation

### Test Suite Status
- ✅ **44 tests passing** (all test modules)
- ✅ **No regressions** introduced
- ✅ **API backward compatible** (no signature changes)
- ✅ **Safety improvements validated** (test coverage updated)

### Test Modules
1. `test_risk_manager.py` - 18 tests (all passing)
2. `test_risk_portfolio_state.py` - 18 tests (all passing)
3. `test_risk_backtest.py` - 8 tests (all passing)

### Key Test: Per-Symbol Exposure Risk-Based
```python
def test_rejection_per_symbol_exposure(self):
    """Test rejection when per-symbol risk exposure too high."""
    # Open 1% risk position
    self.portfolio.open_trade(symbol="AAPL", risk_amount=1000.0)
    
    # Try to add 1.25% risk (confidence=5)
    # Total: 2.25% > MAX_RISK_PER_SYMBOL (2%)
    decision = self.risk_manager.evaluate_trade(
        symbol="AAPL",
        entry_price=150.0,
        confidence=5,
        current_prices={"AAPL": 150.0}
    )
    
    # Should be rejected
    self.assertFalse(decision.approved)  # ✓ PASSING
```

---

## Deployment Summary

### Files Modified
1. **config/settings.py**
   - Added: `ENABLE_ML_SIZING = True` flag

2. **risk/risk_manager.py**
   - Import: Added `ENABLE_ML_SIZING` from config
   - Method: `evaluate_trade()` - Added Check 4 (entry price), Modified Check 6 (risk-based exposure)
   - Method: `_get_confidence_multiplier()` - Rewritten with fail-closed behavior and ML toggle

3. **test_risk_manager.py**
   - Fixed: `test_rejection_per_symbol_exposure()` - Updated for risk-based logic

### Commit
```
Phase F Safety Improvements: Institution-Grade Risk Management

Apply 4 high-impact safety enhancements to RiskManager:
- Fail-Closed Confidence Handling
- Risk-Based Per-Symbol Exposure
- ML Sizing Toggle (ENABLE_ML_SIZING)
- Entry Price Sanity Hardening

All 44 tests pass. No changes to public API.
```

### Push Status
✅ Pushed to GitHub: `main` branch at commit `1567d50`

---

## Configuration Reference

### Risk Parameters (settings.py)
```python
# Risk per trade calculation
RISK_PER_TRADE = 0.01                    # 1% risk per trade base

# Confidence multipliers
CONFIDENCE_RISK_MULTIPLIER = {
    1: 0.25,    # 25% of base risk
    2: 0.50,    # 50% of base risk
    3: 0.75,    # 75% of base risk
    4: 1.00,    # 100% of base risk (neutral)
    5: 1.25,    # 125% of base risk
}

# Concentration limits
MAX_RISK_PER_SYMBOL = 0.02               # 2% per symbol
MAX_PORTFOLIO_HEAT = 0.10                # 10% total heat

# Kill switches
MAX_CONSECUTIVE_LOSSES = 3               # Stop after 3 consecutive losses
DAILY_LOSS_LIMIT = 0.05                  # Stop after 5% daily loss
MAX_TRADES_PER_DAY = 10                  # Max trades per day

# Safety toggle
ENABLE_ML_SIZING = True                  # Set to False to disable confidence-based scaling
```

---

## Fail-Safe Design Philosophy

### Principles Applied
1. **Default Safe**: When uncertain, default to zero or rejection
2. **Explicit Logging**: All edge cases logged for visibility
3. **Fast Failure**: Reject before expensive calculations
4. **Audit Trail**: Full rejection reasons recorded
5. **No Silent Failures**: Every edge case produces a decision record

### Example: Invalid Confidence
```
Signal: confidence = -1 (invalid)
  → Multiplier = 0.0 (fail-closed)
  → Position size = 0 (no trade)
  → Logged: "Invalid confidence level: -1 (must be 1-5), using 0.0"
  → Operator knows: ML signal failed, trade rejected, needs investigation
```

---

## Next Steps & Recommendations

### For Operators
1. Monitor logs for invalid confidence warnings
2. If ML signals degrade: Set `ENABLE_ML_SIZING = False`
3. Monitor entry price rejections for data quality issues

### For Developers
1. Consider ML signal validation upstream
2. Add metrics/alerting for invalid confidence rates
3. Add circuit breaker for degraded signals
4. Consider adaptive confidence multipliers based on signal accuracy

### For Testing
1. Verify fail-closed behavior under fault conditions
2. Test ML toggle switching during live trading
3. Validate entry price checks with broker API edge cases
4. Monitor per-symbol concentration under various market conditions

---

## Summary

These four safety improvements harden the risk engine to institution-grade standards while maintaining backward compatibility and existing API contracts. The changes follow fail-safe design principles: when uncertain, the system defaults to conservative, safe behavior with explicit logging.

- **Risk Reduction**: All improvements reduce crash/corruption risk
- **Operational Control**: ML toggle provides emergency response capability
- **Transparency**: Explicit logging for all edge cases
- **Robustness**: All 44 tests passing, no regressions

**Status**: ✅ Complete, Deployed, Ready for Production
