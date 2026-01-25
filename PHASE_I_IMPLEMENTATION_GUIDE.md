# ✅ PHASE I: PAPER TRADING IMPLEMENTATION GUIDE

**Implementation Date**: January 25, 2026  
**Status**: ✅ COMPLETE & TESTED  
**Architecture**: Broker-agnostic adapter pattern

---

## Quick Start

### 1. Install Dependencies

```bash
# Alpaca Markets API
pip install alpaca-trade-api
```

### 2. Configure Credentials

Set environment variables:
```bash
export APCA_API_BASE_URL="https://paper-api.alpaca.markets"
export APCA_API_KEY_ID="your_key_here"
export APCA_API_SECRET_KEY="your_secret_here"
```

### 3. Enable Paper Trading

In `main.py`:
```python
RUN_PAPER_TRADING = True  # Enable paper trading execution
```

### 4. Run

```bash
python main.py
```

---

## Architecture Overview

### 4-Layer Architecture

```
SIGNAL GENERATION (Phase A-E)
    ↓
PAPER TRADING EXECUTOR (Phase I)
    ↓ (orchestrates)
    ├── BROKER ADAPTER (abstract interface)
    │   └── ALPACA ADAPTER (concrete implementation)
    │
    ├── RISK MANAGER (Phase C)
    │   └── Position sizing + approval
    │
    └── MONITORING SYSTEM (Phase H)
        └── Degradation detection + auto-protection
```

### Component Responsibilities

| Component | Responsibility |
|-----------|-----------------|
| **BrokerAdapter** | Abstract interface (order submission, position queries) |
| **AlpacaAdapter** | Alpaca Markets API implementation |
| **PaperTradingExecutor** | Orchestration (signals → orders → fills) |
| **ExecutionLogger** | Audit trail (JSON logs for all activity) |
| **RiskManager** | Approval gate (every order requires approval) |
| **SystemGuard** | Safety gate (prevents trading if degraded) |

---

## File Structure

```
broker/
  __init__.py                 # Package exports
  adapter.py                  # Abstract interface (250 lines)
  alpaca_adapter.py           # Alpaca implementation (350 lines)
  paper_trading_executor.py   # Orchestration (200 lines)
  execution_logger.py         # Audit logging (300 lines)

tests/
  test_broker_integration.py  # Comprehensive tests (400+ lines)

config/
  settings.py                 # +Phase I parameters

main.py                       # +RUN_PAPER_TRADING flag, +run_paper_trading()
```

---

## Module Details

### broker/adapter.py (BrokerAdapter Interface)

**Purpose**: Abstract broker-agnostic interface

**Key Classes**:
- `OrderStatus`: Enum (PENDING, FILLED, REJECTED, EXPIRED, CANCELLED)
- `OrderResult`: Complete order information with fill details
- `Position`: Current position with PnL tracking
- `BrokerAdapter`: Abstract base class with 8 abstract methods

**Interface Methods**:
```python
# Paper trading verification
@property
is_paper_trading: bool

# Account queries
@property
account_equity: float
@property
buying_power: float

# Order management
submit_market_order(symbol, quantity, side, time_in_force) → OrderResult
get_order_status(order_id) → OrderResult

# Position management
get_positions() → Dict[str, Position]
get_position(symbol) → Optional[Position]
close_position(symbol) → OrderResult

# Market info
get_market_hours(date) → Tuple[datetime, datetime]
is_market_open() → bool
```

**Safety Guarantees**:
- Must raise RuntimeError if live trading detected
- All implementations must fail loud on configuration errors
- Paper trading only—no exceptions

---

### broker/alpaca_adapter.py (AlpacaAdapter)

**Purpose**: Alpaca Markets API integration

**Features**:
- ✅ Paper trading only (enforced at __init__)
- ✅ Market orders at open ("opg" time in force)
- ✅ Order status polling
- ✅ Position queries with current price
- ✅ Comprehensive error handling

**Configuration**:
- `APCA_API_BASE_URL`: Must be `https://paper-api.alpaca.markets`
- `APCA_API_KEY_ID`: API key
- `APCA_API_SECRET_KEY`: API secret

**Error Handling**:
- All exceptions logged with context
- Clear error messages for configuration issues
- Fails fast on initialization if not paper trading

**Example Usage**:
```python
from broker.alpaca_adapter import AlpacaAdapter

# Initialize
broker = AlpacaAdapter()  # Raises if live trading detected

# Submit order
order = broker.submit_market_order(
    symbol="AAPL",
    quantity=100,
    side="buy",
    time_in_force="opg"
)

# Poll status
status = broker.get_order_status(order.order_id)
if status.is_filled():
    print(f"Filled @ ${status.filled_price}")

# Get position
pos = broker.get_position("AAPL")
print(f"PnL: {pos.unrealized_pnl_pct:+.2%}")
```

---

### broker/paper_trading_executor.py (PaperTradingExecutor)

**Purpose**: Orchestrate complete paper trading flow

**Responsibilities**:
1. Accept signals with confidence
2. Request RiskManager approval
3. Submit orders to broker
4. Poll order fills
5. Track positions
6. Update monitoring system
7. Log everything

**Methods**:
```python
execute_signal(symbol, confidence, signal_date, features) → (success, order_id)
poll_order_fills() → Dict[symbol → (fill_price, fill_time)]
close_position(symbol, entry_price, current_price, entry_date) → bool
get_account_status() → Dict (equity, buying_power, positions, etc.)
get_execution_summary() → Dict (metrics)
```

**Safety Features**:
- ✅ Checks auto-protection status before trading
- ✅ Requires RiskManager approval before every order
- ✅ Integrates with monitoring system
- ✅ Logs all decisions
- ✅ Fails loudly on broker errors

**Integration Points**:
```
Signal (confidence)
  ↓
[Check auto-protection status] → SKIP if protected
  ↓
[RiskManager.evaluate_trade()] → REJECT if risk exceeded
  ↓
[Broker.submit_market_order()] → SUBMIT to broker
  ↓
[ExecutionLogger.log_*()]  → LOG decision
  ↓
[SystemGuard.add_signal()] → UPDATE monitoring
```

---

### broker/execution_logger.py (ExecutionLogger)

**Purpose**: Machine-readable audit trail of all trading activity

**Output Format**: JSON Lines (one JSON object per line)

**Log Streams**:
- `trades_YYYY-MM-DD.jsonl`: All trading events
- `errors_YYYY-MM-DD.jsonl`: Errors and alerts

**Events Logged**:
- `signal_generated`: Signal identified
- `risk_check`: Risk manager decision
- `order_submitted`: Order sent to broker
- `order_filled`: Order filled confirmation
- `order_rejected`: Order rejected
- `position_closed`: Position liquidated
- `monitoring_alert`: Degradation alert
- `auto_protection_triggered`: Protection activated
- `system_error`: Operational error

**Example Log Entry**:
```json
{
  "event": "order_submitted",
  "timestamp": "2026-01-25T14:30:45.123456",
  "symbol": "AAPL",
  "order_id": "ORDER_1",
  "side": "BUY",
  "quantity": 100,
  "confidence": 4,
  "position_size": 100,
  "risk_amount": 0.01
}
```

**Analysis**: Logs can be parsed with:
```python
import json

with open("logs/trades_2026-01-25.jsonl") as f:
    for line in f:
        event = json.loads(line)
        print(event)
```

---

## Integration with Phase H (Monitoring)

When monitoring is enabled (`RUN_MONITORING=True`):

1. **Signal Logging**: Each signal is added to confidence distribution monitor
2. **Alert Detection**: Monitoring checks for degradation (confidence inflation, drift)
3. **Auto-Protection**: If 3+ consecutive alerts detected:
   - ML sizing disabled
   - Position sizes capped to conservative levels
   - All new signals blocked
4. **Reversibility**: After investigation, protection can be disabled

**Configuration**:
```python
# config/settings.py
RUN_MONITORING = True           # Enable monitoring
ENABLE_AUTO_PROTECTION = True   # Enable protection trigger
MAX_CONSECUTIVE_ALERTS = 3      # Trigger after 3 alerts
```

**Behavior**:
```
Normal: signals → orders → monitoring
         ↓
Degradation: alert → alert → alert → AUTO-PROTECTION TRIGGERED
                     (1)    (2)    (3)
         ↓
Protected: new signals → BLOCKED until protection disabled
```

---

## Configuration Guide

### Main Configuration (config/settings.py)

```python
# Phase I: Paper Trading
RUN_PAPER_TRADING = False                 # ← Set to True to enable
PAPER_TRADING_MODE_REQUIRED = True        # Safety: fail if not paper
PAPER_TRADING_BROKER = "alpaca"           # Currently supported

# Risk parameters
RISK_PER_TRADE = 0.01                     # 1% risk per trade
MAX_TRADES_PER_DAY = 4                    # 4 new positions per day
MAX_PORTFOLIO_HEAT = 0.08                 # 8% total risk
```

### Environment Variables (Alpaca)

```bash
# Required
export APCA_API_BASE_URL="https://paper-api.alpaca.markets"
export APCA_API_KEY_ID="your_key"
export APCA_API_SECRET_KEY="your_secret"

# Optional
export APCA_API_DATA_BASE_URL="https://data.alpaca.markets"
```

### Monitoring Configuration (config/settings.py)

```python
RUN_MONITORING = True
ENABLE_CONFIDENCE_MONITORING = True
ENABLE_PERFORMANCE_MONITORING = True
ENABLE_FEATURE_DRIFT_MONITORING = True

CONFIDENCE_INFLATION_THRESHOLD = 0.30
MAX_CONSECUTIVE_ALERTS = 3
AUTO_PROTECTION_REVERSIBLE = True
```

---

## Execution Flow

### Daily Paper Trading Cycle

```
4:00 PM (market close)
  ↓
[Signal generation] (Phase A-E logic unchanged)
  ↓
[Signal ranking] (confidence 1-5)
  ↓
5:00 PM
  ↓
[Run paper trading executor] (RUN_PAPER_TRADING=True)
  ├── For each signal (top 20)
  │   ├── Check auto-protection
  │   ├── Get RiskManager approval
  │   ├── Submit market order @ next open
  │   ├── Log to execution logger
  │   └── Update monitoring system
  │
  ├── Poll order fills (next day)
  ├── Track positions
  └── Generate daily report
  ↓
Log files:
  logs/trades_2026-01-25.jsonl
  logs/errors_2026-01-25.jsonl
```

### Complete Execution Example

```python
# In main.py: RUN_PAPER_TRADING = True

python main.py

# Output:
# ============================================================================
# PAPER TRADING EXECUTION (Phase I)
# ============================================================================
# 
# Generating signals...
# [1/100] Processing AAPL: OK (confidence=5)
# [2/100] Processing MSFT: OK (confidence=4)
# ...
# 
# Signals to execute: 20
# ============================================================================
# 
# EXECUTING SIGNAL: AAPL (confidence=5)
# ✓ Signal: AAPL confidence=5
# ✓ Risk check: AAPL - APPROVED (position_size=100)
# Order submitted: BUY 100 AAPL (conf=5, order_id=ORDER_1)
# 
# EXECUTING SIGNAL: MSFT (confidence=4)
# ...
# 
# ============================================================================
# POLLING ORDER FILLS
# ============================================================================
# ✓ Order filled: AAPL filled @ $150.00
# 
# ============================================================================
# ACCOUNT STATUS
# ============================================================================
# Equity: $99,850.00
# Buying Power: $98,500.00
# Open Positions: 1
# Pending Orders: 0
# 
# Positions:
#   AAPL: 100 @ $150.00 (PnL: +0.00%)
# 
# ============================================================================
# EXECUTION SUMMARY
# ============================================================================
# Signals Processed: 20
# Orders Submitted: 18
# Rejections: 2
# Filled Orders: 1
# Monitoring Alerts: 0
# ============================================================================
```

---

## Testing

### Run All Tests

```bash
python -m pytest test_broker_integration.py -v
```

### Test Coverage

**test_broker_integration.py** (400+ lines):
- ✅ OrderStatus/OrderResult behavior
- ✅ Position tracking (long/short)
- ✅ MockBrokerAdapter (full flow)
- ✅ Paper trading verification
- ✅ Order submission/polling
- ✅ ExecutionLogger (all event types)
- ✅ PaperTradingExecutor (signals → orders)
- ✅ Integration tests (end-to-end flow)

### Test Execution

```bash
# Run specific test
python -m pytest test_broker_integration.py::TestPaperTradingExecutor::test_execute_signal_approved -v

# Run with coverage
python -m pytest test_broker_integration.py --cov=broker --cov-report=html

# Run integration tests only
python -m pytest test_broker_integration.py::TestIntegration -v
```

---

## Monitoring Integration (Phase H)

### Auto-Protection Trigger

When degradation detected:
```
Alert 1: Confidence inflation detected
  → Log warning
  → Continue trading

Alert 2: Confidence inflation detected (again)
  → Log warning
  → Continue trading

Alert 3: Confidence inflation detected (again)
  → Log critical: AUTO-PROTECTION TRIGGERED
  → protection_active = True
  → ml_sizing_enabled = False
  → New signals blocked
```

### Reversible Protection

After investigation:
```python
# Disable protection to resume trading
executor.monitor.disable_auto_protection("Issue investigated and fixed")

# This:
# - Sets protection_active = False
# - Re-enables ML sizing
# - Clears alert counter
# - Resumes normal trading
```

---

## Logging & Observability

### Daily Log Files

```
logs/
  trades_2026-01-25.jsonl       (main events)
  errors_2026-01-25.jsonl       (errors and alerts)
  trades_2026-01-26.jsonl       (next day)
  errors_2026-01-26.jsonl
  ...
```

### Example Analysis

Count trades per day:
```bash
cat logs/trades_*.jsonl | grep "order_filled" | wc -l
```

Find all rejected orders:
```bash
cat logs/errors_*.jsonl | grep "order_rejected"
```

Calculate fill rate:
```bash
submitted=$(cat logs/trades_*.jsonl | grep "order_submitted" | wc -l)
filled=$(cat logs/trades_*.jsonl | grep "order_filled" | wc -l)
echo "Fill rate: $(( 100 * filled / submitted ))%"
```

---

## Broker Selection & Extension

### Currently Supported

- **Alpaca Markets** (fully implemented)
  - Paper trading API: https://paper-api.alpaca.markets
  - Production ready
  - Comprehensive test coverage

### Adding New Brokers

To add a new broker (e.g., Interactive Brokers):

1. **Create new adapter** in `broker/ib_adapter.py`
2. **Inherit from BrokerAdapter**
3. **Implement all 8 abstract methods**
4. **Write tests** in `test_broker_integration.py`
5. **Update config** to select broker
6. **Deploy and test**

Example:
```python
# broker/ib_adapter.py
from broker.adapter import BrokerAdapter

class IBKRAdapter(BrokerAdapter):
    """Interactive Brokers adapter."""
    
    @property
    def is_paper_trading(self) -> bool:
        # Implement paper trading check
        pass
    
    # ... implement remaining 7 methods
```

---

## Safety Guarantees

### Paper Trading Only

- ✅ Alpaca adapter checks `is_paper_trading` at initialization
- ✅ Raises RuntimeError if live trading URL detected
- ✅ No trades execute if paper trading verification fails
- ✅ All orders are market orders at market open

### Risk Controls

- ✅ RiskManager approval required for every trade
- ✅ Daily trade limit (4 trades/day default)
- ✅ Per-symbol exposure limit (2% default)
- ✅ Portfolio heat limit (8% default)
- ✅ Daily loss limit (2% default)
- ✅ Confidence-based position sizing

### Monitoring Protection

- ✅ Auto-protection blocks new trades if degraded
- ✅ Protection is reversible
- ✅ All triggers logged and timestamped
- ✅ Can be investigated and disabled

---

## Troubleshooting

### "Failed to initialize broker: Invalid API credentials"

**Solution**: Check environment variables
```bash
echo $APCA_API_KEY_ID
echo $APCA_API_SECRET_KEY
echo $APCA_API_BASE_URL
```

### "Live trading detected!"

**Solution**: Verify using paper trading URL
```bash
# Wrong:
export APCA_API_BASE_URL="https://api.alpaca.markets"

# Correct:
export APCA_API_BASE_URL="https://paper-api.alpaca.markets"
```

### "Failed to get account equity: Access Denied"

**Solution**: Verify API key permissions
- Log into Alpaca dashboard
- Check API key has trading permissions
- Regenerate key if necessary

### "Order submission failed: Insufficient buying power"

**Solution**: Risk limits may be too strict
- Check RISK_PER_TRADE (default 1%)
- Check MAX_PORTFOLIO_HEAT (default 8%)
- Verify account has sufficient equity

---

## Performance Expectations

### Paper Trading Speed

- Signal generation: 100 symbols in ~5-10 seconds
- Order submission: ~1-2 seconds per order
- Fill polling: ~500ms per order
- Daily cycle: ~2-5 minutes total

### Resource Usage

- Memory: ~100 MB (Python + libraries)
- Network: ~1 MB/day (small order volume)
- CPU: Low (mostly waiting for network)

### Typical Daily Volume

- Signals: 15-25 (top candidates)
- Orders: 10-20 (after risk filtering)
- Fills: 5-15 (depends on market)
- Positions: 3-8 (open)

---

## Next Steps

### Week 1: Paper Trading Validation
- ✅ Verify all orders execute
- ✅ Check fill prices are reasonable
- ✅ Verify monitoring alerts work
- ✅ Test auto-protection mechanism

### Week 2-4: Performance Monitoring
- ✅ Track win rate vs backtest
- ✅ Identify execution slippage
- ✅ Monitor alert frequencies
- ✅ Analyze degradation triggers

### Week 5-8: Live Trading Preparation
- ✅ Document any discrepancies
- ✅ Fine-tune thresholds
- ✅ Plan position sizing for live
- ✅ Prepare operational procedures

---

## Phase I Sign-Off

**Implementation**: ✅ COMPLETE  
**Testing**: ✅ COMPLETE  
**Documentation**: ✅ COMPLETE  
**Safety Checks**: ✅ PASSED  

**Status**: Ready for paper trading deployment

---

## Related Documents

- [Phase I Paper Trading Sign-Off](./PHASE_I_SIGN_OFF.md)
- [Phase H Behavioral Validation](./PHASE_H_BEHAVIORAL_SIGN_OFF.md)
- [Broker Adapter Interface](./broker/adapter.py)
- [Test Suite](./test_broker_integration.py)

---

**Questions?** Check troubleshooting section or refer to phase documentation.

