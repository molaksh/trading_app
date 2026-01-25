# Phase F: Complete Reference Index

## 📚 Documentation Files

### Quick Navigation
1. **RISK_QUICKSTART.md** - START HERE
   - 30-second setup
   - Key parameters
   - Position size formula
   - Common scenarios

2. **RISK_GOVERNANCE_README.md** - COMPREHENSIVE
   - Full architecture
   - Component descriptions
   - Trade approval flow
   - Testing guide
   - Troubleshooting

3. **PHASE_F_SUMMARY.md** - DELIVERY
   - Executive summary
   - All deliverables
   - Technical architecture
   - Usage examples

4. **PHASE_F_DELIVERY_CHECKLIST.md** - VALIDATION
   - Implementation status
   - Feature checklist
   - Test results
   - Deployment readiness

---

## 🔧 Core Implementation Files

### Risk Modules (1000+ lines)

**risk/portfolio_state.py** (356 lines)
- OpenPosition class
- PortfolioState class
- Portfolio metrics calculation
- See: RISK_GOVERNANCE_README.md#Portfolio State Tracking

**risk/risk_manager.py** (275 lines)
- TradeDecision dataclass
- RiskManager class
- 6 sequential validation checks
- See: RISK_GOVERNANCE_README.md#Risk Manager

**backtest/risk_backtest.py** (300+ lines)
- RiskGovernedBacktest class
- Risk-aware backtest integration
- See: RISK_GOVERNANCE_README.md#Risk-Governed Backtest

### Configuration (Updated)

**config/settings.py** (Added 7 parameters)
- RISK_PER_TRADE = 0.01
- MAX_RISK_PER_SYMBOL = 0.02
- MAX_PORTFOLIO_HEAT = 0.08
- MAX_TRADES_PER_DAY = 4
- MAX_CONSECUTIVE_LOSSES = 3
- DAILY_LOSS_LIMIT = 0.02
- CONFIDENCE_RISK_MULTIPLIER dict
- See: RISK_GOVERNANCE_README.md#Risk Parameters

**main.py** (Updated)
- RUN_RISK_GOVERNANCE flag
- Execution block with comparison metrics
- See: RISK_GOVERNANCE_README.md#Integration with Backtest

---

## 🧪 Test Files (44 Tests, All Passing ✅)

### test_risk_portfolio_state.py (18 tests)
- Test classes:
  - TestOpenPosition (3 tests)
  - TestPortfolioState (15 tests)

Key tests:
- Position creation and lifecycle
- Portfolio initialization
- Open/close trade mechanics
- Consecutive loss tracking
- Daily metrics
- Portfolio heat calculation
- Symbol exposure
- Summary generation

Run: `python3 -m unittest test_risk_portfolio_state -v`

### test_risk_manager.py (18 tests)
- Test classes:
  - TestTradeDecision (2 tests)
  - TestRiskManager (14 tests)
  - TestRiskConstraints (2 tests)

Key tests:
- Trade approval logic
- Consecutive loss rejection
- Daily loss rejection
- Daily trade limit
- Per-symbol exposure rejection
- Portfolio heat rejection
- Confidence-based position sizing
- Decision logging
- Summary statistics

Run: `python3 -m unittest test_risk_manager -v`

### test_risk_backtest.py (8 tests)
- Test classes:
  - TestRiskGovernedBacktest (4 tests)
  - TestRiskGovernedBacktestFunction (3 tests)
  - TestRiskConstraintApplication (1 test)

Key tests:
- Backtest initialization
- Risk enforcement toggle
- Run completion
- Summary generation
- Comparison capability

Run: `python3 -m unittest test_risk_backtest -v`

### Run All Tests
```bash
python3 -m unittest test_risk_portfolio_state test_risk_manager test_risk_backtest -v
# Expected: Ran 44 tests in X.XXs - OK
```

---

## 📊 Risk Parameters Guide

### Configuration Location
File: `config/settings.py`

### Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| RISK_PER_TRADE | 0.01 | 1% of equity per trade |
| MAX_RISK_PER_SYMBOL | 0.02 | 2% max per symbol |
| MAX_PORTFOLIO_HEAT | 0.08 | 8% max portfolio risk |
| MAX_TRADES_PER_DAY | 4 | 4 max entries/day |
| MAX_CONSECUTIVE_LOSSES | 3 | Stop after 3 losses |
| DAILY_LOSS_LIMIT | 0.02 | 2% max daily loss |

### Confidence Multipliers
```python
CONFIDENCE_RISK_MULTIPLIER = {
    1: 0.25,  # Very low confidence
    2: 0.50,  # Low confidence
    3: 0.75,  # Medium confidence (default)
    4: 1.00,  # High confidence
    5: 1.25   # Very high confidence
}
```

### Preset Profiles

**Conservative**
```python
RISK_PER_TRADE = 0.005
MAX_PORTFOLIO_HEAT = 0.05
MAX_CONSECUTIVE_LOSSES = 2
DAILY_LOSS_LIMIT = 0.01
```

**Moderate (Default)**
```python
RISK_PER_TRADE = 0.01
MAX_PORTFOLIO_HEAT = 0.08
MAX_CONSECUTIVE_LOSSES = 3
DAILY_LOSS_LIMIT = 0.02
```

**Aggressive**
```python
RISK_PER_TRADE = 0.02
MAX_PORTFOLIO_HEAT = 0.15
MAX_CONSECUTIVE_LOSSES = 5
DAILY_LOSS_LIMIT = 0.05
```

---

## 🎯 How-To Guides

### 1. Evaluate Single Trade

```python
from risk.portfolio_state import PortfolioState
from risk.risk_manager import RiskManager

portfolio = PortfolioState(initial_equity=100000)
risk_manager = RiskManager(portfolio)

decision = risk_manager.evaluate_trade(
    symbol="AAPL",
    entry_price=150.0,
    confidence=4,
    current_prices={"AAPL": 150.0}
)

if decision.approved:
    print(f"Buy {decision.position_size} shares")
else:
    print(f"Rejected: {decision.reason}")
```

### 2. Execute Trade

```python
import pandas as pd

if decision.approved:
    portfolio.open_trade(
        symbol="AAPL",
        entry_date=pd.Timestamp.now(),
        entry_price=150.0,
        position_size=decision.position_size,
        risk_amount=decision.risk_amount,
        confidence=4
    )
```

### 3. Close Trade

```python
portfolio.close_trade(
    symbol="AAPL",
    exit_date=pd.Timestamp.now(),
    exit_price=155.0
)
```

### 4. Get Portfolio Summary

```python
summary = portfolio.get_summary()
print(f"Equity: ${summary['current_equity']:,.2f}")
print(f"Daily P&L: ${summary['daily_pnl']:,.2f}")
print(f"Win Rate: {summary['win_rate']:.1f}%")
```

### 5. Run Risk-Governed Backtest

```python
from backtest.risk_backtest import run_risk_governed_backtest

trades = run_risk_governed_backtest(
    symbols=["AAPL", "MSFT"],
    enforce_risk=True
)

print(f"Executed: {len(trades)} trades")
```

### 6. Compare Risk Impact

```python
trades_with_risk = run_risk_governed_backtest(
    symbols=["AAPL", "MSFT"],
    enforce_risk=True
)

trades_no_risk = run_risk_governed_backtest(
    symbols=["AAPL", "MSFT"],
    enforce_risk=False
)

print(f"With limits: {len(trades_with_risk)} trades")
print(f"No limits: {len(trades_no_risk)} trades")
```

---

## 🔍 Trade Rejection Scenarios

### Kill Switch 1: Consecutive Losses
**Trigger:** consecutive_losses >= MAX_CONSECUTIVE_LOSSES
**Message:** "Max consecutive losses exceeded (3/3)"
**Reset:** On winning trade

### Kill Switch 2: Daily Loss
**Trigger:** daily_pnl <= -DAILY_LOSS_LIMIT × equity
**Message:** "Daily loss limit exceeded (-2.5% > -2.0%)"
**Reset:** Next trading day

### Daily Trade Limit
**Trigger:** daily_trades_opened >= MAX_TRADES_PER_DAY
**Message:** "Max trades per day reached (4/4)"
**Reset:** Next trading day

### Per-Symbol Exposure
**Trigger:** symbol_exposure > MAX_RISK_PER_SYMBOL
**Message:** "Symbol exposure limit exceeded (2.5% > 2.0%)"
**Prevents:** Over-concentration in single symbol

### Portfolio Heat
**Trigger:** portfolio_heat > MAX_PORTFOLIO_HEAT
**Message:** "Portfolio heat limit exceeded (8.5% > 8.0%)"
**Prevents:** Excessive total leverage

### Position Size Validation
**Trigger:** position_size <= 0 or risk_amount <= 0
**Message:** "Invalid position size calculated"
**Prevents:** Algorithmic errors

---

## 📈 Portfolio Metrics

### Real-Time Metrics
```python
portfolio.get_summary()
# Returns:
{
    'current_equity': float,           # Current account value
    'available_capital': float,        # Available for new trades
    'open_positions': int,             # Number of open positions
    'open_symbols': List[str],         # List of symbols with positions
    'daily_pnl': float,                # Today's profit/loss
    'daily_loss_pct': float,           # Daily loss percentage
    'cumulative_return': float,        # Total return percentage
    'consecutive_losses': int,         # Current loss streak
    'total_trades_closed': int,        # Total closed trades
    'win_rate': float                  # Percentage of winning trades
}
```

### Portfolio Heat
```python
heat = portfolio.get_portfolio_heat(current_prices)
# Returns: float between 0.0 and 1.0
# 0.01 = 1% portfolio at risk (conservative)
# 0.05 = 5% portfolio at risk (moderate)
# 0.08 = 8% portfolio at risk (aggressive)
```

### Per-Symbol Exposure
```python
exposure = portfolio.get_symbol_exposure("AAPL")
# Returns: float (position value as % of equity)
# 0.015 = 1.5% of portfolio in AAPL
```

---

## 🚀 Quick Start Commands

```bash
# Run all risk tests
python3 -m unittest test_risk_manager test_risk_portfolio_state test_risk_backtest -v

# Run specific test module
python3 -m unittest test_risk_manager -v

# Run specific test class
python3 -m unittest test_risk_manager.TestRiskManager -v

# Run specific test
python3 -m unittest test_risk_manager.TestRiskManager.test_approval_basic_trade -v

# Run risk-governed backtest
RUN_RISK_GOVERNANCE=True python3 main.py

# Enable debug logging
python3 -c "import logging; logging.basicConfig(level=logging.DEBUG); ..."
```

---

## 🐛 Troubleshooting

### All Trades Rejected?
**Cause:** Kill switch active (consecutive losses or daily loss limit)
**Solution:** Wait for day reset, reduce MAX_CONSECUTIVE_LOSSES, or check daily_pnl

### Portfolio Heat Too High?
**Cause:** Total portfolio risk exceeds limit
**Solution:** Close positions or increase MAX_PORTFOLIO_HEAT, reduce RISK_PER_TRADE

### Position Sizes Keep Shrinking?
**Cause:** Consecutive losses reducing position multiplier
**Solution:** Reset kill switches or close losing positions

### No Trades Executing?
**Cause:** All signals rejected by risk manager
**Solution:** Check reason in decision.reason, loosen constraints, or review signals

---

## 📚 Additional Resources

### Architecture
- RISK_GOVERNANCE_README.md - Complete architecture documentation
- PHASE_F_SUMMARY.md - Implementation details and design decisions

### Examples
- RISK_QUICKSTART.md - Quick start guide with examples
- test_risk_*.py - Unit tests with usage patterns

### Reference
- config/settings.py - Risk parameter definitions
- risk/portfolio_state.py - PortfolioState API
- risk/risk_manager.py - RiskManager API
- backtest/risk_backtest.py - Backtest wrapper API

---

## 📊 Statistics

| Metric | Value |
|--------|-------|
| Core Modules | 2 (portfolio_state, risk_manager) |
| Integration Modules | 1 (risk_backtest) |
| Test Files | 3 |
| Test Cases | 44 |
| Tests Passing | 44/44 ✅ |
| Documentation Files | 4 |
| Lines of Code | 1000+ |
| Lines of Tests | 870+ |
| Lines of Docs | 1200+ |
| Total Deliverable | 3200+ |

---

## ✅ Validation Checklist

- ✅ All 44 tests passing
- ✅ Risk parameters configured
- ✅ Portfolio state tracking complete
- ✅ Risk manager approval logic working
- ✅ Backtest integration tested
- ✅ Main.py execution logic implemented
- ✅ Documentation complete
- ✅ No changes to signal generation
- ✅ No changes to feature logic
- ✅ Backward compatible
- ✅ Production ready

---

## 🎯 Success Criteria Met

✅ **Risk Management**: Strict limits on position size, daily trades, and consecutive losses
✅ **Portfolio Tracking**: Real-time equity, heat, and exposure calculations
✅ **Decision Explainability**: Detailed rejection reasons for all decisions
✅ **Backtest Integration**: Seamless integration with existing backtest loop
✅ **Testing**: 44 comprehensive unit tests, all passing
✅ **Documentation**: 1200+ lines covering all aspects
✅ **Production Ready**: Kill switches, clear logging, configurable parameters

---

**Phase F Complete and Ready for Production** ✅

