# Exit Logic Implementation - Swing Trading System

## Overview

This implementation provides a **rules-based exit system** for swing trading with strict separation between:
1. **Swing Strategy Exits** (EOD only, normal trading logic)
2. **Emergency Risk Exits** (intraday, capital protection only)

## Design Principles

### Core Constraints
- ✅ **Swing Trading System** (NOT day trading)
- ✅ Entries allowed intraday
- ✅ Normal exits MUST NOT trigger intraday
- ✅ Emergency exits MAY trigger intraday (rare, capital protection)
- ✅ No same-day entry and exit via strategy logic
- ✅ Complete audit trail with exit classification

## Architecture

```
ExitEvaluator (Master Coordinator)
│
├── SwingExitEvaluator (Layer 1: Strategy)
│   ├── Max Holding Period
│   ├── Profit Target
│   └── Trend Invalidation
│
└── EmergencyExitEvaluator (Layer 2: Risk Protection)
    ├── Catastrophic Loss (% of portfolio)
    ├── Extreme ATR Move (volatility-based)
    └── Same-Day Protection (catastrophic only)
```

## Layer 1: Swing Strategy Exits

### Characteristics
- **Evaluation**: End-of-day data only
- **Execution**: Next market open
- **Classification**: `SWING_EXIT`
- **Urgency**: `eod`
- **Purpose**: Normal trading strategy

### Exit Rules

#### 1. Maximum Holding Period
```python
if holding_days >= max_holding_days:
    # Exit at next open
    # Default: 20 days
```

#### 2. Profit Target
```python
if return_pct >= profit_target_pct:
    # Exit at next open
    # Default: 10%
```

#### 3. Trend Invalidation
```python
if close < SMA_200:
    # Trend broken, exit at next open
```

### Configuration
```python
swing_config = {
    "max_holding_days": 20,
    "profit_target_pct": 0.10,  # 10%
    "use_trend_invalidation": True,
}
```

## Layer 2: Emergency Risk Exits

### Characteristics
- **Evaluation**: Continuous during market hours
- **Execution**: Immediate (intraday allowed)
- **Classification**: `EMERGENCY_EXIT`
- **Urgency**: `immediate`
- **Purpose**: Capital preservation ONLY

### Exit Rules

#### 1. Catastrophic Position Loss
```python
loss_pct_of_portfolio = position_loss / portfolio_equity
if loss_pct_of_portfolio >= max_position_loss_pct:
    # Emergency exit immediately
    # Default: 3% of portfolio
```

#### 2. Extreme Adverse Move (ATR-based)
```python
price_move = entry_price - current_price
threshold = atr_multiplier * atr
if price_move >= threshold:
    # Emergency exit immediately
    # Default: 4× ATR
```

#### 3. Same-Day Protection
```python
if holding_days == 0:
    # Only exit if catastrophic (>2× threshold)
    # Prevents day trading behavior
```

### Configuration
```python
emergency_config = {
    "max_position_loss_pct": 0.03,  # 3% of portfolio
    "atr_multiplier": 4.0,           # 4× ATR
    "enable_volatility_check": True,
}
```

## Usage

### Basic Setup

```python
from strategy.exit_evaluator import ExitEvaluator

# Initialize with default configs
exit_evaluator = ExitEvaluator()

# Or with custom configs
exit_evaluator = ExitEvaluator(
    swing_config={
        "max_holding_days": 15,
        "profit_target_pct": 0.08,
    },
    emergency_config={
        "max_position_loss_pct": 0.025,
        "atr_multiplier": 5.0,
    }
)
```

### Evaluate EOD Swing Exits

```python
# Call ONLY with end-of-day data
exit_signal = exit_evaluator.evaluate_eod(
    symbol="AAPL",
    entry_date=date(2026, 1, 10),
    entry_price=150.0,
    current_price=165.0,  # EOD close
    confidence=4,
    eod_data=eod_series,  # Optional: for trend checks
    evaluation_date=date.today(),
)

if exit_signal:
    # exit_signal.exit_type == ExitType.SWING_EXIT
    # exit_signal.urgency == 'eod'
    # Execute at next market open
    pass
```

### Evaluate Emergency Exits

```python
# Call continuously during market hours
exit_signal = exit_evaluator.evaluate_emergency(
    symbol="AAPL",
    entry_date=date(2026, 1, 10),
    entry_price=150.0,
    current_price=140.0,  # Current intraday price
    position_size=100,
    portfolio_equity=100000.0,
    confidence=4,
    atr=3.0,  # Optional: for ATR checks
    evaluation_date=date.today(),
)

if exit_signal:
    # exit_signal.exit_type == ExitType.EMERGENCY_EXIT
    # exit_signal.urgency == 'immediate'
    # Execute immediately
    pass
```

### Integration with Executor

```python
from broker.paper_trading_executor import PaperTradingExecutor

executor = PaperTradingExecutor(
    broker=broker,
    risk_manager=risk_manager,
    exit_evaluator=exit_evaluator,
)

# Evaluate EOD exits (after market close)
eod_exits = executor.evaluate_exits_eod(
    eod_data={"AAPL": eod_series},
    evaluation_date=date.today(),
)

# Execute EOD exits (at next market open)
for exit_signal in eod_exits:
    executor.execute_exit(exit_signal)

# Evaluate emergency exits (during market hours)
emergency_exits = executor.evaluate_exits_emergency(
    atr_data={"AAPL": 3.0},
    evaluation_date=date.today(),
)

# Execute emergency exits (immediately)
for exit_signal in emergency_exits:
    executor.execute_exit(exit_signal)
```

## Audit Trail

### Exit Signal Structure

```python
@dataclass
class ExitSignal:
    symbol: str
    exit_type: ExitType  # SWING_EXIT or EMERGENCY_EXIT
    reason: str
    timestamp: datetime
    entry_date: date
    holding_days: int
    confidence: int
    urgency: str  # 'eod' or 'immediate'
```

### Logging

All exits are logged with complete metadata:

```json
{
  "event": "exit_signal",
  "timestamp": "2026-01-26T12:30:00.123456",
  "symbol": "AAPL",
  "exit_type": "SWING_EXIT",
  "reason": "Profit target reached (11.5% >= 10.0%)",
  "entry_date": "2026-01-10",
  "holding_days": 16,
  "confidence": 4,
  "urgency": "eod"
}
```

```json
{
  "event": "position_closed",
  "timestamp": "2026-01-26T12:30:00.123456",
  "symbol": "AAPL",
  "quantity": 100,
  "entry_price": 150.0,
  "exit_price": 167.25,
  "pnl": 1725.0,
  "pnl_pct": 0.115,
  "hold_days": 16,
  "entry_date": "2026-01-10",
  "exit_type": "SWING_EXIT",
  "exit_reason": "Profit target reached (11.5% >= 10.0%)"
}
```

### Analytics Separation

Statistics should treat exit types separately:

```python
swing_exits = [e for e in exits if e.exit_type == ExitType.SWING_EXIT]
emergency_exits = [e for e in exits if e.exit_type == ExitType.EMERGENCY_EXIT]

# Swing exit stats (normal strategy performance)
swing_win_rate = calculate_win_rate(swing_exits)
swing_avg_return = calculate_avg_return(swing_exits)

# Emergency exit stats (risk protection effectiveness)
emergency_count = len(emergency_exits)
emergency_avg_loss = calculate_avg_return(emergency_exits)

# Emergency exits should be RARE (< 5% of total exits)
emergency_rate = emergency_count / (len(swing_exits) + emergency_count)
```

## Testing

Run the demo to verify all scenarios:

```bash
python3 demo_exit_logic.py
```

Expected output shows:
- ✅ Swing exits triggering on EOD conditions
- ✅ Emergency exits triggering on catastrophic conditions
- ✅ Same-day protection preventing day trading
- ✅ Complete audit trail logging

## File Structure

```
trading_app/
├── strategy/
│   └── exit_evaluator.py         # Exit logic implementation
├── broker/
│   ├── paper_trading_executor.py # Integration with executor
│   └── execution_logger.py       # Exit logging
├── demo_exit_logic.py            # Demonstration script
└── EXIT_LOGIC_README.md          # This file
```

## Key Takeaways

1. **Strict Separation**: Swing exits (strategy) vs Emergency exits (risk)
2. **No Day Trading**: Same-day exits only on catastrophic conditions
3. **Complete Audit**: Every exit classified and logged with reason
4. **Capital Preservation**: Emergency exits are RARE, not optimization
5. **Modular Design**: Clean boundaries, testable components

## Next Steps

1. ✅ Exit logic implemented with 2-layer architecture
2. ✅ Executor integration complete
3. ✅ Logging enhanced for exit audit trail
4. ✅ Demo script validates all scenarios
5. 🔲 Integrate EOD exit evaluation into main trading loop
6. 🔲 Add emergency exit monitoring during market hours
7. 🔲 Configure exit parameters based on backtesting
8. 🔲 Create analytics dashboard separating exit types
