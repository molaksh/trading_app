# Phase F: Risk Governance - Quick Start

## TL;DR

Risk governance prevents catastrophic losses by enforcing strict limits on:
- **Position sizes** (1% of equity per trade by default)
- **Daily trades** (4 maximum per day)
- **Consecutive losses** (stop after 3 losses)
- **Daily losses** (stop if -2% in a day)
- **Portfolio heat** (8% maximum open risk)
- **Confidence-based sizing** (high confidence → larger positions)

## 30-Second Setup

```python
from risk.portfolio_state import PortfolioState
from risk.risk_manager import RiskManager

# Initialize
portfolio = PortfolioState(initial_equity=100000)
risk_manager = RiskManager(portfolio)

# Evaluate trade signal
decision = risk_manager.evaluate_trade(
    symbol="AAPL",
    entry_price=150.0,
    confidence=4,              # 1-5 scale, affects position size
    current_prices={"AAPL": 150.0}
)

# Execute if approved
if decision.approved:
    portfolio.open_trade(
        symbol="AAPL",
        entry_date=pd.Timestamp.now(),
        entry_price=150.0,
        position_size=decision.position_size,      # Calculated by risk manager
        risk_amount=decision.risk_amount,           # Dollar risk
        confidence=4
    )
else:
    print(f"Rejected: {decision.reason}")
```

## Running Risk-Governed Backtest

```bash
# Enable in main.py
RUN_RISK_GOVERNANCE = True

# Run
python3 main.py
```

Output shows:
1. Backtest WITH risk limits (governance enforced)
2. Backtest WITHOUT limits (research mode)
3. Comparison metrics

## Key Risk Parameters

Edit `config/settings.py`:

```python
RISK_PER_TRADE = 0.01              # 1% per trade
MAX_PORTFOLIO_HEAT = 0.08          # 8% portfolio risk
MAX_TRADES_PER_DAY = 4             # 4 entries/day
MAX_CONSECUTIVE_LOSSES = 3         # Stop after 3 losses
DAILY_LOSS_LIMIT = 0.02            # -2% daily limit

# Confidence multipliers (1-5 scale)
CONFIDENCE_RISK_MULTIPLIER = {
    1: 0.25,  # Low confidence: 25% position
    2: 0.50,  # 50% position
    3: 0.75,  # 75% position (medium)
    4: 1.00,  # 100% position (high)
    5: 1.25   # 125% position (very high)
}
```

## Position Size Formula

```
Position Size = (Equity × RISK_PER_TRADE × Confidence Multiplier) / Entry Price
```

Example (equity=$100k, confidence=4):
```
Position Size = ($100,000 × 0.01 × 1.0) / $150 = 6.67 shares
```

## Trade Rejection Checks (Priority)

1. **Kill Switch: Consecutive Losses** - If losses ≥ 3, STOP trading
2. **Kill Switch: Daily Loss** - If daily loss ≤ -2%, STOP trading
3. **Daily Trade Cap** - If trades ≥ 4 today, REJECT
4. **Per-Symbol Exposure** - If symbol > 2%, REJECT
5. **Portfolio Heat** - If total heat > 8%, REJECT
6. **Position Size** - If calculated size invalid, REJECT

## Approval Decision Example

```python
decision = TradeDecision(
    approved=True,
    position_size=7,
    risk_amount=1050.0,
    reason="APPROVED (Conf=4, Risk=$1050.00, Size=7, Heat=0.75%)"
)
```

## Portfolio Metrics

```python
portfolio.get_summary()
# Returns:
{
    'current_equity': 100500.0,       # Current account value
    'daily_pnl': 500.0,               # Today's P&L
    'cumulative_return': 0.005,       # Total return %
    'open_positions': 2,              # Number open
    'consecutive_losses': 0,          # Loss streak
    'total_trades_closed': 5,         # Total trades
    'win_rate': 60.0                  # Win % 
}
```

## Tests

All 44 unit tests passing:
- 18 portfolio state tests
- 18 risk manager tests
- 8 backtest integration tests

```bash
python3 -m unittest test_risk_manager test_risk_portfolio_state test_risk_backtest -v
```

## Common Scenarios

### Scenario 1: Trade Gets Rejected

```python
decision = risk_manager.evaluate_trade(...)
if not decision.approved:
    print(decision.reason)
    # Output: "Max consecutive losses exceeded (3/3)"
```

**Solution:** Reset kill switch or adjust MAX_CONSECUTIVE_LOSSES

### Scenario 2: Portfolio Heat Too High

```python
if portfolio.get_portfolio_heat(...) > MAX_PORTFOLIO_HEAT:
    print("Portfolio too leveraged, can't add new positions")
```

**Solution:** Close some positions or increase MAX_PORTFOLIO_HEAT

### Scenario 3: Daily Trade Limit Hit

```python
if portfolio.daily_trades_opened >= MAX_TRADES_PER_DAY:
    print("Already opened 4 trades today, maximum reached")
```

**Solution:** Wait for next trading day or reduce MAX_TRADES_PER_DAY

## Risk Profiles

### Conservative
```python
RISK_PER_TRADE = 0.005             # 0.5% per trade
MAX_PORTFOLIO_HEAT = 0.05          # 5% total
MAX_CONSECUTIVE_LOSSES = 2         # Strict
```

### Moderate (Default)
```python
RISK_PER_TRADE = 0.01              # 1% per trade
MAX_PORTFOLIO_HEAT = 0.08          # 8% total
MAX_CONSECUTIVE_LOSSES = 3         # Medium
```

### Aggressive
```python
RISK_PER_TRADE = 0.02              # 2% per trade
MAX_PORTFOLIO_HEAT = 0.15          # 15% total
MAX_CONSECUTIVE_LOSSES = 5         # Lenient
```

## Files

- `risk/portfolio_state.py` - Portfolio state tracking (OpenPosition, PortfolioState)
- `risk/risk_manager.py` - Trade approval engine (RiskManager, TradeDecision)
- `backtest/risk_backtest.py` - Risk-governed backtest wrapper
- `config/settings.py` - Risk parameters
- `test_risk_*.py` - 44 unit tests
- `RISK_GOVERNANCE_README.md` - Full documentation

## Next Steps

1. ✅ Review risk parameters in `config/settings.py`
2. ✅ Run tests: `python3 -m unittest test_risk_manager -v`
3. ✅ Run backtest: `python3 main.py` with `RUN_RISK_GOVERNANCE=True`
4. ✅ Compare metrics with/without risk limits
5. ✅ Adjust parameters for your risk tolerance
6. ✅ Deploy to live trading (with caution!)

## Support

See `RISK_GOVERNANCE_README.md` for:
- Full architecture documentation
- Advanced usage examples
- Troubleshooting guide
- Design rationale
