# Phase I: Paper Trading Deployment Guide

**Last Updated**: January 25, 2026  
**Status**: ✅ Ready for deployment  

---

## Step 1: Install Dependencies

```bash
# Install Alpaca Markets API
pip install alpaca-trade-api

# Verify installation
python -c "import alpaca; print('✓ Alpaca installed')"
```

---

## Step 2: Create Alpaca Account

1. Go to: https://app.alpaca.markets
2. Sign up for free account
3. Go to **Account Settings** → **API Keys**
4. Generate new API key (save securely)
5. Verify you're using **PAPER TRADING** (not live)

---

## Step 3: Set Environment Variables

### macOS/Linux

```bash
# Add to ~/.zshrc or ~/.bash_profile
export APCA_API_BASE_URL="https://paper-api.alpaca.markets"
export APCA_API_KEY_ID="YOUR_KEY_HERE"
export APCA_API_SECRET_KEY="YOUR_SECRET_HERE"

# Then reload:
source ~/.zshrc  # or ~/.bash_profile
```

### Windows (PowerShell)

```powershell
[Environment]::SetEnvironmentVariable("APCA_API_BASE_URL", "https://paper-api.alpaca.markets", "User")
[Environment]::SetEnvironmentVariable("APCA_API_KEY_ID", "YOUR_KEY_HERE", "User")
[Environment]::SetEnvironmentVariable("APCA_API_SECRET_KEY", "YOUR_SECRET_HERE", "User")
```

### Verify

```bash
echo $APCA_API_BASE_URL     # Should show: https://paper-api.alpaca.markets
echo $APCA_API_KEY_ID       # Should show your key
```

---

## Step 4: Configure Trading System

### In main.py

```python
# Set to True to enable paper trading
RUN_PAPER_TRADING = True

# Other modes (set to False)
RUN_BACKTEST = False
RUN_ML_EXPERIMENT = False
RUN_RISK_GOVERNANCE = False
RUN_EXECUTION_REALISM = False
```

### In config/settings.py

```python
# Phase I: Paper Trading
RUN_PAPER_TRADING = True           # ← Already set
PAPER_TRADING_BROKER = "alpaca"    # ← Already set

# Optional: Enable monitoring
RUN_MONITORING = True              # ← Recommended
ENABLE_AUTO_PROTECTION = True      # ← Recommended
```

---

## Step 5: Test Configuration

Before running with real orders, verify everything works:

```bash
# Test Alpaca connection
python -c "
from broker.alpaca_adapter import AlpacaAdapter
try:
    broker = AlpacaAdapter()
    print(f'✓ Connected to Alpaca')
    print(f'✓ Equity: ${broker.account_equity:,.2f}')
    print(f'✓ Buying Power: ${broker.buying_power:,.2f}')
except Exception as e:
    print(f'✗ Error: {e}')
"

# Expected output:
# ✓ Connected to Alpaca
# ✓ Equity: $100,000.00
# ✓ Buying Power: $100,000.00
```

---

## Step 6: Run Paper Trading (First Time)

### Do a test run with smaller position sizes

```python
# In config/settings.py, temporarily reduce risk:
RISK_PER_TRADE = 0.001            # 0.1% instead of 1%
MAX_TRADES_PER_DAY = 2             # 2 instead of 4
```

### Run the system

```bash
python main.py
```

### Expected output

```
============================================================================
PAPER TRADING EXECUTION (Phase I)
============================================================================

Generating signals...
[1/100] Processing AAPL: OK (confidence=5)
[2/100] Processing MSFT: OK (confidence=4)
...

Signals to execute: 20
============================================================================

EXECUTING SIGNAL: AAPL (confidence=5)
✓ Signal: AAPL confidence=5
✓ Risk check: AAPL - APPROVED (position_size=50)
Order submitted: BUY 50 AAPL (conf=5, order_id=ORDER_1)

EXECUTING SIGNAL: MSFT (confidence=4)
...

============================================================================
POLLING ORDER FILLS
============================================================================
Newly filled: 0
(Orders will fill tomorrow at market open)

============================================================================
ACCOUNT STATUS
============================================================================
Equity: $99,500.00
Buying Power: $99,500.00
Open Positions: 0
Pending Orders: 2
```

### Check log files

```bash
# View today's trades
cat logs/trades_2026-01-25.jsonl | python -m json.tool | head -50

# Count events
cat logs/trades_2026-01-25.jsonl | jq '.event' | sort | uniq -c
```

---

## Step 7: Restore Normal Risk Settings

After first test run succeeds:

```python
# In config/settings.py
RISK_PER_TRADE = 0.01              # Back to 1%
MAX_TRADES_PER_DAY = 4             # Back to 4
```

---

## Step 8: Daily Operation

### Before market close (4 PM ET)

```bash
# Run the system
python main.py

# Should take 2-5 minutes
# Orders submitted for next day's market open
# Check logs: logs/trades_*.jsonl
```

### After market open (10 AM ET)

```bash
# Run again to poll fills
python main.py

# Will check order status
# Log any fills
# Update monitoring
```

### Before market close (3:50 PM ET)

- Review open positions
- Consider closing positions for end-of-day
- Check monitoring alerts

---

## Monitoring Daily

### Check execution

```bash
# Count orders submitted today
cat logs/trades_$(date +%Y-%m-%d).jsonl | grep "order_submitted" | wc -l

# Count orders filled
cat logs/trades_$(date +%Y-%m-%d).jsonl | grep "order_filled" | wc -l

# Count rejections
cat logs/errors_$(date +%Y-%m-%d).jsonl | grep "order_rejected" | wc -l
```

### Check account

```bash
python -c "
from broker.alpaca_adapter import AlpacaAdapter
broker = AlpacaAdapter()
positions = broker.get_positions()
print(f'Open positions: {len(positions)}')
for sym, pos in positions.items():
    print(f'  {sym}: {pos.quantity} @ ${pos.avg_entry_price:.2f} (PnL: {pos.unrealized_pnl_pct:+.2%})')
"
```

### Check monitoring

```bash
# View monitoring alerts
cat logs/errors_$(date +%Y-%m-%d).jsonl | grep "monitoring_alert"

# Check auto-protection status
cat logs/errors_$(date +%Y-%m-%d).jsonl | grep "auto_protection"
```

---

## Troubleshooting

### Orders Not Submitting

**Symptom**: "Orders Submitted: 0"

**Check**:
1. Risk manager approvals
   ```bash
   cat logs/errors_*.jsonl | grep "risk_check"
   ```

2. Buying power
   ```bash
   python -c "
   from broker.alpaca_adapter import AlpacaAdapter
   broker = AlpacaAdapter()
   print(f'Buying Power: ${broker.buying_power:,.2f}')
   "
   ```

3. Risk limits
   - Is `RISK_PER_TRADE` reasonable?
   - Is `MAX_PORTFOLIO_HEAT` reasonable?
   - Check account equity

### Orders Submitted But Not Filling

**Symptom**: Orders pending for days

**Possible causes**:
1. **Market holiday** - Check Alpaca calendar
2. **Symbol not trading** - Check stock status
3. **Order time issue** - Check time_in_force is "opg"

**Check**:
```bash
python -c "
from broker.alpaca_adapter import AlpacaAdapter
broker = AlpacaAdapter()
# Check market hours
from datetime import datetime, timedelta
tomorrow = datetime.now() + timedelta(days=1)
hours = broker.get_market_hours(tomorrow)
print(f'Market hours: {hours[0]} to {hours[1]}')

# Check if market is open
print(f'Market open now: {broker.is_market_open()}')
"
```

### API Errors

**Symptom**: "Failed to initialize broker: [error]"

**Check**:
1. Environment variables set
   ```bash
   echo $APCA_API_KEY_ID
   echo $APCA_API_SECRET_KEY
   echo $APCA_API_BASE_URL
   ```

2. Credentials valid
   - Log into Alpaca dashboard
   - Verify API key exists
   - Check permissions

3. Paper trading URL
   ```bash
   # Should be:
   echo $APCA_API_BASE_URL
   # https://paper-api.alpaca.markets
   
   # NOT:
   # https://api.alpaca.markets (live)
   ```

### Monitoring Alert Spam

**Symptom**: Many alerts in errors log

**Possible causes**:
1. Confidence thresholds too loose
2. Performance monitoring too strict
3. Feature drift threshold too low

**Fix**:
```python
# In config/settings.py
CONFIDENCE_INFLATION_THRESHOLD = 0.35    # Loosen from 0.30
WIN_RATE_ALERT_THRESHOLD = 0.35          # Loosen from 0.40
FEATURE_DRIFT_ZSCORE_THRESHOLD = 3.5     # Loosen from 3.0
```

---

## Safety Reminders

### Paper Trading Only

✅ **Always verify**:
```bash
echo $APCA_API_BASE_URL
# Must show: https://paper-api.alpaca.markets
# NOT: https://api.alpaca.markets
```

### Risk Limits

✅ **Always start small**:
```python
# First few days
RISK_PER_TRADE = 0.001              # 0.1% instead of 1%
MAX_TRADES_PER_DAY = 2               # 2 instead of 4

# After one week
RISK_PER_TRADE = 0.005              # 0.5%
MAX_TRADES_PER_DAY = 3               # 3

# After two weeks
RISK_PER_TRADE = 0.01               # 1% (normal)
MAX_TRADES_PER_DAY = 4               # 4 (normal)
```

### Monitoring

✅ **Keep enabled**:
```python
RUN_MONITORING = True              # Recommended
ENABLE_AUTO_PROTECTION = True      # Recommended
```

---

## Daily Checklist

### Before trading (4 PM ET)

- [ ] Environment variables set
- [ ] `RUN_PAPER_TRADING = True`
- [ ] Risk limits reasonable
- [ ] Monitoring enabled
- [ ] No critical errors in logs

### After trading (6 PM ET)

- [ ] Orders submitted successfully
- [ ] No rejections
- [ ] Logs created: `logs/trades_*.jsonl`
- [ ] No critical errors

### Next day (10 AM ET)

- [ ] Market open
- [ ] Check fills
- [ ] Review position PnL
- [ ] Check alerts

### End of week

- [ ] Review execution logs
- [ ] Calculate fill rate
- [ ] Compare to backtest
- [ ] Fine-tune settings

---

## Performance Tracking

### Track win rate

```bash
# Create simple script
python -c "
import json

filled_count = 0
total_pnl = 0

with open('logs/trades_2026-01-*.jsonl') as f:
    for line in f:
        event = json.loads(line)
        if event.get('event') == 'position_closed':
            filled_count += 1
            total_pnl += event.get('pnl_pct', 0)

print(f'Positions closed: {filled_count}')
if filled_count > 0:
    print(f'Avg return: {total_pnl/filled_count:+.2%}')
"
```

### Compare to backtest

```python
# Compare win rates:
# Backtest win rate: ~55% (from Phase G)
# Paper trading win rate: ?

# Track daily and weekly
# Expected to be slightly lower than backtest (due to slippage)
# Should be within 2-3% of backtest
```

---

## Moving to Live Trading (Phase II)

After 4-8 weeks of successful paper trading:

1. **Verify performance** - Win rate matches expectations
2. **Reduce position sizes** - Use 5-10% of account per trade
3. **Enable monitoring** - Keep close eye on equity
4. **Start small** - Small positions first
5. **Scale gradually** - Increase over weeks

Same interface:
```python
# Just change credentials to live account
export APCA_API_BASE_URL="https://api.alpaca.markets"  # Live
```

---

## Help & Support

### Documentation

- [Quick Start](./PHASE_I_README.md)
- [Implementation Guide](./PHASE_I_IMPLEMENTATION_GUIDE.md)
- [Sign-Off](./PHASE_I_SIGN_OFF.md)

### Test

```bash
# Run tests
python -m pytest test_broker_integration.py -v
```

### Debug

```bash
# Enable debug logging
python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from broker.alpaca_adapter import AlpacaAdapter
broker = AlpacaAdapter()
"
```

---

## Summary

✅ **You're ready to paper trade!**

1. Install dependencies
2. Set environment variables
3. Enable in main.py
4. Run: `python main.py`
5. Monitor logs
6. Track performance
7. Scale gradually

Good luck! 🚀

