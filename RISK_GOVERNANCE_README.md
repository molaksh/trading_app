# Phase F: Risk & Portfolio Governance - Implementation Guide

## Overview

Phase F implements comprehensive risk management and portfolio governance for the trading system. This layer sits between signal generation and execution, enforcing strict risk limits while maintaining transparency and explainability.

**Key Principle**: Risk governance is **transparent, enforced, and non-invasive**. It does NOT modify signal generation or feature logic—it only controls trade approval and position sizing.

---

## Architecture

### Core Components

#### 1. **Portfolio State** (`risk/portfolio_state.py`)
Tracks real-time portfolio metrics for risk calculations.

**OpenPosition Class**
- Individual position tracking (symbol, entry date/price, position size, risk, confidence)
- Unrealized P&L tracking
- Price updates

**PortfolioState Class**
- Maintains all open positions
- Tracks portfolio equity, available capital
- Records closed trades with P&L
- Calculates portfolio-wide metrics:
  - Portfolio heat (total risk as % of equity)
  - Per-symbol exposure
  - Consecutive losses
  - Daily P&L tracking

#### 2. **Risk Manager** (`risk/risk_manager.py`)
Trade approval engine with sequential validation checks.

**TradeDecision Dataclass**
- `approved`: Boolean approval status
- `position_size`: Number of shares (0 if rejected)
- `risk_amount`: Dollar risk amount
- `reason`: Explicit explanation for approval/rejection

**RiskManager Class**
Sequential trade evaluation (6 checks):

1. **Consecutive Loss Kill Switch** - Stops trading after N consecutive losses
2. **Daily Loss Kill Switch** - Stops trading if daily loss exceeds limit
3. **Daily Trade Limit** - Caps entries per day
4. **Per-Symbol Exposure** - Limits exposure to single symbol
5. **Portfolio Heat** - Limits total portfolio risk
6. **Position Size Validation** - Confidence-based sizing multiplier

#### 3. **Risk-Governed Backtest** (`backtest/risk_backtest.py`)
Integrates risk management into backtest loop.

**RiskGovernedBacktest Class**
- Wraps standard backtest
- Calls risk manager before each entry
- Tracks rejections and max portfolio heat
- Provides risk-aware metrics

---

## Risk Parameters (`config/settings.py`)

```python
# Core Risk Parameters
RISK_PER_TRADE = 0.01              # 1% of equity per trade
MAX_RISK_PER_SYMBOL = 0.02         # 2% maximum per symbol
MAX_PORTFOLIO_HEAT = 0.08          # 8% maximum portfolio heat

# Daily Constraints
MAX_TRADES_PER_DAY = 4             # 4 entries per day max
MAX_CONSECUTIVE_LOSSES = 3         # Stop after 3 losses
DAILY_LOSS_LIMIT = 0.02            # 2% daily loss limit

# Confidence-Based Multipliers
CONFIDENCE_RISK_MULTIPLIER = {
    1: 0.25,  # Very low confidence: 0.25x position size
    2: 0.50,  # Low confidence: 0.50x position size
    3: 0.75,  # Medium confidence: 0.75x position size (default)
    4: 1.00,  # High confidence: 1.0x position size
    5: 1.25   # Very high confidence: 1.25x position size
}
```

### Parameter Rationale

- **RISK_PER_TRADE = 1%**: Standard Kelly Criterion fraction for controlled growth
- **MAX_PORTFOLIO_HEAT = 8%**: Allows diversification while limiting downside
- **MAX_CONSECUTIVE_LOSSES = 3**: Kill switch prevents emotional spiral
- **DAILY_LOSS_LIMIT = 2%**: Caps daily catastrophic loss
- **CONFIDENCE_RISK_MULTIPLIER**: Rewards model confidence while capping position size

---

## Trade Approval Flow

### Example: Evaluating Trade for AAPL at $150

```python
portfolio = PortfolioState(initial_equity=100000)
risk_manager = RiskManager(portfolio)

# Evaluate entry signal
decision = risk_manager.evaluate_trade(
    symbol="AAPL",
    entry_price=150.0,
    confidence=4,  # High confidence (1-5 scale)
    current_prices={"AAPL": 150.0}
)

if decision.approved:
    # Execute: Buy decision.position_size shares
    portfolio.open_trade(
        symbol="AAPL",
        entry_date=now,
        entry_price=150.0,
        position_size=decision.position_size,
        risk_amount=decision.risk_amount,
        confidence=4
    )
else:
    # Reject trade
    print(f"Trade rejected: {decision.reason}")
```

### Position Size Calculation

**Formula:**
```
1. Get confidence multiplier from CONFIDENCE_RISK_MULTIPLIER[confidence]
2. Base risk = equity × RISK_PER_TRADE × multiplier
3. Position size = base_risk / entry_price
```

**Example (confidence=4, equity=$100k):**
- Multiplier = 1.0 (high confidence)
- Base risk = $100,000 × 0.01 × 1.0 = $1,000
- Position size = $1,000 / $150 = 6.67 shares (6-7 with rounding)

### Rejection Checks (Priority Order)

1. **Kill Switch 1: Consecutive Losses**
   ```
   IF consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
       REJECT - "Max consecutive losses exceeded"
   ```

2. **Kill Switch 2: Daily Loss**
   ```
   IF daily_pnl / equity <= -DAILY_LOSS_LIMIT:
       REJECT - "Daily loss limit exceeded"
   ```

3. **Daily Trade Cap**
   ```
   IF daily_trades_opened >= MAX_TRADES_PER_DAY:
       REJECT - "Max trades per day reached"
   ```

4. **Per-Symbol Exposure**
   ```
   proposed_exposure = symbol_pnl_value / equity
   IF proposed_exposure > MAX_RISK_PER_SYMBOL:
       REJECT - "Symbol exposure limit exceeded"
   ```

5. **Portfolio Heat Limit**
   ```
   proposed_heat = (total_risk + new_risk) / equity
   IF proposed_heat > MAX_PORTFOLIO_HEAT:
       REJECT - "Portfolio heat limit exceeded"
   ```

6. **Position Size Validation**
   ```
   IF position_size <= 0 OR risk_amount <= 0:
       REJECT - "Invalid position size calculated"
   ```

---

## Integration with Backtest

### Running Risk-Governed Backtest

```python
from backtest.risk_backtest import run_risk_governed_backtest

# Run WITH risk enforcement (recommended)
trades = run_risk_governed_backtest(SYMBOLS, enforce_risk=True)

# Run WITHOUT risk enforcement (research mode)
trades = run_risk_governed_backtest(SYMBOLS, enforce_risk=False)
```

### Backtest Output Metrics

```python
metrics = {
    'trades': 45,                    # Total trades executed
    'rejected_trades': 12,           # Trades rejected by risk manager
    'final_equity': 105250.0,        # Final account value
    'cumulative_return': 0.0525,     # 5.25% return
    'win_rate': 0.62,                # 62% winning trades
    'max_portfolio_heat': 0.075,     # Peak 7.5% portfolio heat
    'consecutive_losses': 0,         # Current streak
    'approval_rate': 0.79            # 79% of signals approved
}
```

### Comparison Analysis

Run backtests with and without risk enforcement to quantify impact:

```python
trades_with_risk = run_risk_governed_backtest(SYMBOLS, enforce_risk=True)
trades_no_risk = run_risk_governed_backtest(SYMBOLS, enforce_risk=False)

# Compare metrics
with_risk_return = sum(t.return_pct for t in trades_with_risk) / len(trades_with_risk)
no_risk_return = sum(t.return_pct for t in trades_no_risk) / len(trades_no_risk)

print(f"With Risk Limits: {with_risk_return:.2%}")
print(f"Without Limits: {no_risk_return:.2%}")
print(f"Risk Premium: {abs(with_risk_return - no_risk_return):.2%}")
```

---

## Portfolio State Tracking

### Daily Lifecycle

```python
# Start of day
portfolio.daily_pnl = 0.0
portfolio.daily_trades_opened = 0
portfolio.daily_start_equity = portfolio.current_equity

# During day
# - Trade 1: Entry @ 9:30 AM
portfolio.open_trade(...)
# - Trade 1: Exit @ 10:15 AM (profit +$500)
portfolio.close_trade(...)
# portfolio.daily_pnl = +$500
# portfolio.consecutive_losses = 0

# - Trade 2: Entry @ 11:00 AM
portfolio.open_trade(...)
# - Trade 2: Exit @ 2:00 PM (loss -$200)
portfolio.close_trade(...)
# portfolio.daily_pnl = +$300
# portfolio.consecutive_losses = 1

# End of day summary
portfolio.get_summary()
# {
#     'current_equity': 100300.0,
#     'daily_pnl': 300.0,
#     'daily_trades_opened': 2,
#     'total_trades_closed': 2,
#     'consecutive_losses': 1,
#     'win_rate': 50.0
# }
```

### Key Metrics

**Portfolio Heat**
```
heat = sum(open_position.risk_amount for all positions) / current_equity
```
- 0.01 = 1% portfolio at risk (conservative)
- 0.05 = 5% portfolio at risk (moderate)
- 0.08 = 8% portfolio at risk (aggressive, hit limit)

**Per-Symbol Exposure**
```
exposure = position_value / current_equity
```
- Single symbol contribution to total portfolio
- Prevents over-concentration

**Win Rate**
```
win_rate = (profitable_trades / total_trades) × 100%
```
- 50% = random walk
- 60%+ = edge-based system

---

## Risk Governance Decision Logic

### Approval Reason Format

```python
# Approved trade
"APPROVED (Conf=4, Risk=$1000.00, Size=7, Heat=0.75%)"

# Rejected trades
"Max consecutive losses exceeded (3/3)"
"Daily loss limit exceeded (-2.5% > -2.0%)"
"Max trades per day reached (4/4)"
"Symbol exposure limit exceeded (2.5% > 2.0%)"
"Portfolio heat limit exceeded (8.5% > 8.0%)"
```

### Logging Example

```python
import logging

logger = logging.getLogger(__name__)

# Trade approved
logger.info(f"APPROVED trade: {decision.reason}")

# Trade rejected
logger.warning(f"REJECTED trade: {decision.reason}")

# End of day summary
portfolio.log_summary()
# Output:
# [INFO] Portfolio Summary:
# [INFO]   Equity: $100,300
# [INFO]   Daily P&L: $300
# [INFO]   Win Rate: 50.0%
# [INFO]   Consecutive Losses: 1
```

---

## Testing

### Test Coverage

**test_risk_portfolio_state.py** (18 tests)
- OpenPosition creation and price updates
- Portfolio initialization
- Open/close trade mechanics
- Consecutive loss tracking
- Daily metrics calculation
- Portfolio heat calculation
- Symbol exposure calculation
- Summary generation

**test_risk_manager.py** (18 tests)
- Basic trade approval
- All 6 rejection scenarios
- Confidence-based position sizing
- Decision logging
- Summary statistics

**test_risk_backtest.py** (8 tests)
- Backtest initialization
- Risk-governed execution
- Comparison with unrestricted backtest
- Metrics generation

### Running Tests

```bash
# Run all risk tests
python3 -m unittest test_risk_portfolio_state test_risk_manager test_risk_backtest -v

# Run specific test module
python3 -m unittest test_risk_manager -v

# Run specific test class
python3 -m unittest test_risk_manager.TestRiskManager -v

# Run specific test
python3 -m unittest test_risk_manager.TestRiskManager.test_confidence_affects_position_size -v
```

**Expected Output:**
```
Ran 44 tests in X.XXs
OK
```

---

## Quick Start

### 1. Enable Risk Governance in main.py

```python
# In main.py, set flag to True
RUN_RISK_GOVERNANCE = True  # Changed from False
```

### 2. Run Risk-Governed Backtest

```bash
python3 main.py
```

### 3. Interpret Results

The output will show:
- Trades with risk limits (governance enforced)
- Trades without limits (research mode)
- Comparison metrics

Example:
```
==============================
RISK GOVERNANCE IMPACT
==============================

Metric                         With Risk Limits    No Limits
----------------------------------------------------------------------
Trade Count                    43                  55
Win Rate                       62.8%               58.2%
Avg Return                     0.45%               0.32%
```

### 4. Adjust Parameters

Edit `config/settings.py` to tune risk parameters:

```python
RISK_PER_TRADE = 0.015          # Increase to 1.5%
MAX_PORTFOLIO_HEAT = 0.10       # Increase to 10%
MAX_CONSECUTIVE_LOSSES = 5      # More lenient
DAILY_LOSS_LIMIT = 0.03         # Allow 3% daily loss
```

---

## Advanced Usage

### Custom Risk Profile

**Conservative (Low Risk)**
```python
RISK_PER_TRADE = 0.005           # 0.5% per trade
MAX_PORTFOLIO_HEAT = 0.05        # 5% total
MAX_CONSECUTIVE_LOSSES = 2       # Strict
DAILY_LOSS_LIMIT = 0.01          # 1% limit
```

**Moderate (Balanced)**
```python
RISK_PER_TRADE = 0.01            # 1% per trade (default)
MAX_PORTFOLIO_HEAT = 0.08        # 8% total
MAX_CONSECUTIVE_LOSSES = 3       # Medium
DAILY_LOSS_LIMIT = 0.02          # 2% limit
```

**Aggressive (High Growth)**
```python
RISK_PER_TRADE = 0.02            # 2% per trade
MAX_PORTFOLIO_HEAT = 0.15        # 15% total
MAX_CONSECUTIVE_LOSSES = 5       # Lenient
DAILY_LOSS_LIMIT = 0.05          # 5% limit
```

### Programmatic Access

```python
from risk.portfolio_state import PortfolioState
from risk.risk_manager import RiskManager

# Create fresh portfolio
portfolio = PortfolioState(initial_equity=250000)
risk_manager = RiskManager(portfolio)

# Evaluate signals
decision = risk_manager.evaluate_trade(
    symbol="AAPL",
    entry_price=150.0,
    confidence=4,
    current_prices={"AAPL": 150.0, "MSFT": 300.0}
)

# Execute if approved
if decision.approved:
    portfolio.open_trade(
        symbol="AAPL",
        entry_date=pd.Timestamp.now(),
        entry_price=150.0,
        position_size=decision.position_size,
        risk_amount=decision.risk_amount,
        confidence=4
    )

# Get metrics
summary = portfolio.get_summary()
print(f"Current Equity: ${summary['current_equity']:,.2f}")
print(f"Daily P&L: ${summary['daily_pnl']:,.2f}")
```

---

## Monitoring & Debugging

### Check Portfolio State

```python
portfolio.get_summary()
# {
#     'current_equity': 100500.0,
#     'available_capital': 100500.0,
#     'open_positions': 2,
#     'open_symbols': ['AAPL', 'MSFT'],
#     'daily_pnl': 500.0,
#     'daily_loss_pct': 0.005,
#     'cumulative_return': 0.005,
#     'consecutive_losses': 0,
#     'total_trades_closed': 3,
#     'win_rate': 66.7
# }
```

### Check Risk Manager Status

```python
risk_manager.get_summary()
# {
#     'approvals': 45,
#     'rejections': 10,
#     'total_decisions': 55,
#     'approval_rate': 0.818,
#     'rejection_breakdown': {
#         'consecutive_losses': 2,
#         'daily_loss_limit': 1,
#         'daily_trades': 3,
#         'symbol_exposure': 2,
#         'portfolio_heat': 2
#     }
# }
```

### Enable Debug Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)

# Now see all trade decisions
# [DEBUG] Opened position: Position(AAPL, 2024-01-01, size=7, conf=4)
# [DEBUG] Closed position: AAPL @ 152.50, PnL=$175.00
```

---

## Key Design Decisions

### 1. Why Sequential Checks?
Kill switches (consecutive losses, daily loss) are checked FIRST to prevent catastrophic losses before calculating position size.

### 2. Why Confidence-Based Sizing?
High-confidence signals (from ML/backtest) deserve larger positions. Limits overconfidence while rewarding edge.

### 3. Why Portfolio Heat?
Prevents scenario where multiple small positions create large aggregate risk. Forward-looking calculation includes proposed new trade.

### 4. Why FIFO Closing?
First-in-first-out ensures consistent position lifecycle and simplifies tax accounting.

### 5. Why Separate enforce_risk Flag?
Allows research mode (no limits) for comparison analysis while supporting production mode (strict limits).

---

## Troubleshooting

**Q: All trades are being rejected after 3 losses?**
A: Kill switch activated. Consecutive losses hit limit. Wait or reduce MAX_CONSECUTIVE_LOSSES in settings.

**Q: Portfolio heat exceeds limit immediately?**
A: Increase MAX_PORTFOLIO_HEAT or reduce RISK_PER_TRADE. Heat accumulates as positions grow.

**Q: No daily trades after 4 entries?**
A: Daily trade limit enforced. Reduce MAX_TRADES_PER_DAY or wait for next day.

**Q: Position sizes keep shrinking?**
A: Consecutive losses reduce confidence. Reset daily counters or close losing positions.

---

## References

- Kelly Criterion: Optimal fraction = (p × w - (1-p)) / w
- Value-at-Risk (VaR): Probability of loss exceeding maximum
- Portfolio Heat: Leverage-equivalent metric for risk concentration
- Win Rate: Percentage of profitable trades (>50% indicates edge)

