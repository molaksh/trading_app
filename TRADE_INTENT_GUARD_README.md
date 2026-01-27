# Trade Intent Guard - PDT-Safe Behavior Layer

**Status:** Production-ready  
**Purpose:** Prevent accidental day trading, strategy drift, and regulatory violations  
**Applies to:** All accounts (cash and margin)

---

## Overview

The Trade Intent Guard is a **behavioral layer** that sits between your exit logic and order execution. It ensures your swing trading system maintains **intent** (holding trades for multiple days) while never blocking risk-reducing exits.

### Key Principles

1. **Behavioral PDT applies to ALL accounts** - No same-day discretionary exits
2. **Regulatory PDT applies to MARGIN < $25k** - Hard limit of 3 day trades in 5 days
3. **Risk exits ALWAYS override** - STOP_LOSS and RISK_MANAGER never blocked
4. **Deterministic and auditable** - Every decision logged with reasoning
5. **Safe by default** - Manual overrides disabled; must be explicitly enabled

---

## Rule Priority Order

When evaluating an exit request, rules are applied in this order:

### 1️⃣ **MAX HOLD PERIOD** (ALL ACCOUNTS)
- **Default:** 20 days maximum
- **Behavior:** Force exit, no discretion
- **Rationale:** Prevent zombie positions

```python
if holding_days > 20:
    → FORCE EXIT (allowed=True, reason=MAX_HOLD_EXCEEDED)
```

### 2️⃣ **RISK-REDUCING EXITS** (ALL ACCOUNTS)
- **Types:** `STOP_LOSS`, `RISK_MANAGER`
- **Behavior:** Always allowed, overrides all other rules
- **Rationale:** Risk management cannot be blocked

```python
if exit_reason in [STOP_LOSS, RISK_MANAGER]:
    → ALLOW (overrides all other rules)
```

### 3️⃣ **BEHAVIORAL PDT** (ALL ACCOUNTS)
- **Rule:** No same-day discretionary exits
- **Applies to:** Non-risk exits on entry date
- **Rationale:** Prevents accidental day trading intent

```python
if holding_days == 0 and exit_reason not in [STOP_LOSS, RISK_MANAGER]:
    → BLOCK (reason=SAME_DAY_DISCRETIONARY)
```

### 4️⃣ **MINIMUM HOLD PERIOD** (ACCOUNTS < $25k)
- **Default:** 2 days minimum
- **Applies to:** Discretionary exits only
- **Rationale:** Prevents rapid in-and-out trading for small accounts

```python
if account_equity < 25000 and holding_days < 2:
    and exit_reason not in [STOP_LOSS, RISK_MANAGER]:
    → BLOCK (reason=MIN_HOLD_NOT_MET)
```

### 5️⃣ **REGULATORY PDT LIMITS** (MARGIN < $25k ONLY)
- **Window:** 5 calendar days
- **Soft limit:** 2 day trades (prevents reaching 3)
- **Hard limit:** 3 day trades (regulatory requirement)
- **Applies to:** Day trades (entry_date == exit_date) only
- **Rationale:** SEC requirement for PDT accounts

```python
if account_type == "MARGIN" and account_equity < 25000:
    if is_day_trade(trade, exit_date):
        if day_trade_count_5d >= 3:
            → BLOCK (reason=PDT_LIMIT_REACHED)
        elif day_trade_count_5d == 2:
            → BLOCK (reason=PDT_LIMIT_AT_RISK)
```

### 6️⃣ **MANUAL OVERRIDE** (DISABLED BY DEFAULT)
- **Default:** Blocked
- **Enable with:** `TradeIntentGuard(allow_manual_override=True)`
- **Rationale:** Explicit control to prevent accidental misuse

```python
if exit_reason == MANUAL_OVERRIDE:
    if not ALLOW_MANUAL_OVERRIDE:
        → BLOCK (reason=MANUAL_OVERRIDE_DISABLED)
```

---

## Configuration

### Default Constants

```python
MIN_EQUITY_THRESHOLD = 25000.0      # Account size for PDT rules
MIN_HOLD_DAYS = 2                   # Minimum hold before discretionary exit
MAX_HOLD_DAYS = 20                  # Maximum hold (force exit)
PDT_SOFT_LIMIT = 2                  # Warn at 2 day trades
PDT_HARD_LIMIT = 3                  # Block at 3 day trades
PDT_WINDOW_DAYS = 5                 # Rolling day trade window
ALLOW_MANUAL_OVERRIDE = False        # Manual overrides disabled by default
```

### Customize

```python
from risk.trade_intent_guard import TradeIntentGuard

# Create with manual override enabled
guard = TradeIntentGuard(allow_manual_override=True)

# Adjust constants (if needed)
guard.MIN_HOLD_DAYS = 3
guard.MAX_HOLD_DAYS = 30
```

---

## Usage

### Basic Flow

```python
from risk.trade_intent_guard import (
    TradeIntentGuard,
    ExitReason,
    create_trade,
    create_account_context,
)

# Initialize guard
guard = TradeIntentGuard(allow_manual_override=False)

# Create trade record
trade = create_trade(
    symbol="AAPL",
    entry_date=date(2026, 1, 27),
    entry_price=150.0,
    quantity=100,
    confidence=4,
)

# Get account context from broker
account = create_account_context(
    account_equity=10000.0,
    account_type="MARGIN",  # or "CASH"
    day_trade_count_5d=2,  # From broker's rolling counter
)

# Check if exit is allowed
decision = guard.can_exit_trade(
    trade=trade,
    exit_date=date(2026, 1, 29),
    exit_reason=ExitReason.STRATEGY_SIGNAL,
    account_context=account,
)

# Use decision
if decision.allowed:
    # Submit exit order
    logger.info(f"Exit approved: {trade.symbol}")
else:
    # Log and skip
    logger.warning(f"Exit blocked: {decision.block_reason}")
```

### Integration with Executor

```python
from broker.paper_trading_executor import PaperTradingExecutor
from risk.trade_intent_guard import TradeIntentGuard

class GuardedExecutor(PaperTradingExecutor):
    """Executor with intent guard."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.intent_guard = TradeIntentGuard(allow_manual_override=False)
    
    def evaluate_exit(self, position, exit_reason):
        """Evaluate exit with guard."""
        
        # Get account context
        account = create_account_context(
            account_equity=self.broker.get_account()['equity'],
            account_type=self.broker.get_account()['account_type'],
            day_trade_count_5d=self.broker.get_day_trade_count_5d(),
        )
        
        # Check guard
        decision = self.intent_guard.can_exit_trade(
            trade=position.trade,
            exit_date=date.today(),
            exit_reason=exit_reason,
            account_context=account,
        )
        
        # Log decision
        self.intent_guard.log_exit_decision(decision, position.trade, exit_reason)
        
        # Honor decision
        if decision.allowed:
            # Proceed with exit
            return True
        else:
            # Block exit
            logger.warning(f"Exit blocked: {decision.block_reason}")
            return False
```

---

## Exit Reason Classification

### `STOP_LOSS` - Risk-Reducing ✅
- Loss exceeds stop-loss threshold
- Always allowed (overrides all rules)
- **Example:** Position down 5%, stop at -3%

### `RISK_MANAGER` - Risk-Reducing ✅
- Risk manager says position too risky
- Always allowed (overrides all rules)
- **Example:** Portfolio heat exceeded

### `TIME_EXPIRY` - Discretionary ⚠️
- Max holding period reached
- Subject to PDT rules
- **Example:** Day 20 of 20-day hold

### `STRATEGY_SIGNAL` - Discretionary ⚠️
- Profit target hit, trend broken, etc.
- Subject to PDT rules
- **Example:** Position up 10%

### `MANUAL_OVERRIDE` - Discretionary ⚠️
- Manual intervention (normally disabled)
- Blocked unless explicitly enabled
- **Example:** User force-closes position

---

## Decision Output

### ExitDecision Structure

```python
@dataclass
class ExitDecision:
    allowed: bool                   # True = can exit, False = blocked
    reason: str                     # BlockReason enum value
    block_reason: Optional[str]     # Human-readable explanation if blocked
    day_trade_count_5d: int         # For audit
    account_equity: float           # For audit
    account_type: str               # For audit
    holding_days: int               # For audit
```

### Example: Allowed

```python
ExitDecision(
    allowed=True,
    reason='allowed',
    block_reason=None,
    holding_days=5,
    account_equity=10000.0,
    account_type='MARGIN',
    day_trade_count_5d=1,
)
```

### Example: Blocked

```python
ExitDecision(
    allowed=False,
    reason='same_day_discretionary',
    block_reason='Cannot exit same day as entry (strategy_signal not allowed)',
    holding_days=0,
    account_equity=10000.0,
    account_type='MARGIN',
    day_trade_count_5d=0,
)
```

---

## Scenarios & Examples

### Scenario 1: Small Account Day Trading Attempt

**Setup:**
- Account: $10k margin
- Entry: Jan 27 @ $150
- Exit attempt: Jan 27 @ $152 (same day)
- Reason: STRATEGY_SIGNAL (profit target hit)
- Day trades in past 5 days: 0

**Decision:**
```
❌ BLOCKED: same_day_discretionary
  "Cannot exit same day as entry (strategy_signal not allowed)"
```

**Why?** Behavioral PDT rule prevents discretionary same-day exits.

---

### Scenario 2: Risk Manager Override

**Setup:**
- Account: $10k margin
- Entry: Jan 27 @ $150
- Exit attempt: Jan 27 @ $130 (same day, -13%)
- Reason: RISK_MANAGER (position too risky)
- Day trades in past 5 days: 2

**Decision:**
```
✅ ALLOWED
```

**Why?** RISK_MANAGER is risk-reducing and overrides all rules.

---

### Scenario 3: PDT Soft Limit

**Setup:**
- Account: $10k margin
- Entry: Jan 26 @ $100
- Exit attempt: Jan 27 @ $103 (next day, day trade)
- Reason: STRATEGY_SIGNAL (profit target)
- Day trades in past 5 days: 2

**Decision:**
```
❌ BLOCKED: pdt_limit_at_risk
  "Would trigger PDT limit (2 → 3)"
```

**Why?** Margin < $25k and this would be 3rd day trade (hard limit = 3).

---

### Scenario 4: Minimum Hold Requirement

**Setup:**
- Account: $10k margin
- Entry: Jan 26 @ $150
- Exit attempt: Jan 27 @ $155 (1 day later)
- Reason: STRATEGY_SIGNAL (profit target +3%)
- Day trades in past 5 days: 0

**Decision:**
```
❌ BLOCKED: min_hold_not_met
  "Must hold for 2 days (1 days held)"
```

**Why?** Small account requires 2-day minimum before discretionary exit.

---

### Scenario 5: Max Hold Force Exit

**Setup:**
- Account: $10k margin
- Entry: Jan 7 @ $100
- Exit attempt: Jan 28 @ $105 (21 days later)
- Reason: TIME_EXPIRY (max hold reached)
- Day trades in past 5 days: 1

**Decision:**
```
✅ ALLOWED: max_hold_exceeded
```

**Why?** Max 20-day hold exceeded; force exit regardless of other rules.

---

### Scenario 6: Large Account Swing Trading

**Setup:**
- Account: $50k margin
- Entry: Jan 22 @ $200
- Exit attempt: Jan 27 @ $215 (5 days later)
- Reason: STRATEGY_SIGNAL (profit target +7.5%)
- Day trades in past 5 days: 0

**Decision:**
```
✅ ALLOWED
```

**Why?** Large account, 5 days held, no PDT restrictions apply.

---

## Logging & Audit

### Decision Log Format

Every exit decision logs:

```
================================================================================
EXIT DECISION LOG
================================================================================
Symbol: AAPL
Allowed: False
Reason: same_day_discretionary
Block Reason: Cannot exit same day as entry (strategy_signal not allowed)
Holding Days: 0
Account Type: MARGIN
Account Equity: $10,000.00
Day Trade Count (5d): 0
Exit Reason: strategy_signal
================================================================================
```

### Accessing Logs

```python
# Create structured audit record
audit_record = {
    "symbol": decision.symbol,
    "allowed": decision.allowed,
    "reason": decision.reason,
    "block_reason": decision.block_reason,
    "holding_days": decision.holding_days,
    "account_equity": decision.account_equity,
    "account_type": decision.account_type,
    "day_trade_count_5d": decision.day_trade_count_5d,
    "timestamp": datetime.now(),
}

# Save to JSON for compliance
import json
with open("exit_decisions.jsonl", "a") as f:
    f.write(json.dumps(audit_record) + "\n")
```

---

## Unit Tests

```bash
pytest tests/test_trade_intent_guard.py -v
```

### Test Coverage

- ✅ Max hold period (force exit)
- ✅ Risk-reducing exits (override all)
- ✅ Behavioral PDT (same-day blocking)
- ✅ Minimum hold period (small accounts)
- ✅ Regulatory PDT soft/hard limits
- ✅ Manual override enable/disable
- ✅ Edge cases (threshold boundaries)
- ✅ Integration scenarios (real-world)

---

## Integration Checklist

- [ ] Add `trade_intent_guard.py` to risk module
- [ ] Import in executor (e.g., `PaperTradingExecutor`)
- [ ] Create guard instance: `self.intent_guard = TradeIntentGuard()`
- [ ] Before submitting exit order, call: `decision = guard.can_exit_trade(...)`
- [ ] Check `decision.allowed` before proceeding
- [ ] Log `decision` for audit trail
- [ ] Test with unit tests: `pytest tests/test_trade_intent_guard.py`
- [ ] Monitor logs for "EXIT DECISION LOG" entries
- [ ] Adjust config if needed (e.g., `MIN_HOLD_DAYS`)

---

## FAQ

**Q: Will the guard block me from exiting a losing position?**  
A: No. STOP_LOSS exits always bypass all rules, so you can always cut losses.

**Q: What if I want to take profits quickly?**  
A: For accounts < $25k, you must wait 2 days minimum. For accounts > $25k, you can exit anytime (except same-day discretionary).

**Q: Can I manually override the guard?**  
A: Only if you explicitly enable it: `TradeIntentGuard(allow_manual_override=True)`. Default is disabled for safety.

**Q: How does the guard know my day trade count?**  
A: You pass it in `account_context.day_trade_count_5d`, which comes from your broker's API.

**Q: Does the guard work with cash accounts?**  
A: Yes, but only behavioral rules apply. Regulatory PDT rules only apply to margin accounts < $25k.

**Q: What happens if I exceed the max hold period?**  
A: The guard returns `allowed=True` with reason `max_hold_exceeded`. You MUST exit.

---

## Production Deployment

### Safe Defaults

```python
# Recommended for production
guard = TradeIntentGuard(allow_manual_override=False)

# Guard will:
# ✅ Allow risk exits (STOP_LOSS, RISK_MANAGER)
# ✅ Block same-day discretionary exits
# ✅ Enforce minimum holds for small accounts
# ✅ Respect regulatory PDT limits
# ✅ Force exit after 20 days
```

### Monitoring

```python
# Log all exit decisions to file
with open("logs/exit_decisions.jsonl", "a") as f:
    f.write(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "symbol": trade.symbol,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "block_reason": decision.block_reason,
    }) + "\n")

# Alert on blocks
if not decision.allowed:
    logger.warning(f"Exit blocked for {trade.symbol}: {decision.block_reason}")
    # Optionally: send email, Slack message, etc.
```

---

## Version History

- **v1.0** (Jan 27, 2026) - Initial implementation
  - All rules implemented and tested
  - Production-ready

---

**Author:** Trading System  
**Last Updated:** January 27, 2026  
**Status:** Production-Ready ✅
