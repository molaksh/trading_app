# Phase I: Paper Trading - Quick Start

## What Is Phase I?

Phase I connects your trading system to **Alpaca Markets** for **paper trading** (simulated money, real broker).

You can now:
- ✅ Submit real orders to broker
- ✅ Track fills and positions
- ✅ Validate signal quality with real market
- ✅ Monitor degradation (Phase H)
- ✅ Maintain complete audit trail

## 60-Second Setup

### 1. Install

```bash
pip install alpaca-trade-api
```

### 2. Configure

```bash
export APCA_API_BASE_URL="https://paper-api.alpaca.markets"
export APCA_API_KEY_ID="your_key_here"
export APCA_API_SECRET_KEY="your_secret_here"
```

### 3. Enable

In `main.py`:
```python
RUN_PAPER_TRADING = True
```

### 4. Run

```bash
python main.py
```

## What Happens?

```
python main.py
↓
1. Generate signals (Phase A-E logic unchanged)
2. For each signal:
   - Check risk manager approval
   - Check auto-protection status
   - Submit order to Alpaca
   - Log to JSON audit trail
3. Poll fills next day
4. Track positions and P&L
5. Monitor degradation (Phase H)
```

## Output

Logs in `logs/`:
- `trades_2026-01-25.jsonl` - All events (JSON, machine-readable)
- `errors_2026-01-25.jsonl` - Errors and alerts

Console output:
```
============================================================================
PAPER TRADING EXECUTION (Phase I)
============================================================================

Signals to execute: 20

EXECUTING SIGNAL: AAPL (confidence=5)
✓ Risk check: AAPL - APPROVED
Order submitted: BUY 100 AAPL @ next open (order_id=ORDER_1)

...

============================================================================
EXECUTION SUMMARY
============================================================================
Signals Processed: 20
Orders Submitted: 18
Rejections: 2
```

## Safety

✅ **Paper trading only**
- Alpaca adapter checks at startup
- Raises error if live trading URL detected
- Zero tolerance for misconfiguration

✅ **Risk controls enforced**
- RiskManager approves every trade
- Daily limits (4 trades/day)
- Position sizing limits
- Portfolio heat limits

✅ **Monitoring integrated**
- Detects degradation (Phase H)
- Auto-protection blocks trades if degraded
- All decisions logged

## Key Files

| File | Purpose |
|------|---------|
| `broker/adapter.py` | Abstract interface (250 lines) |
| `broker/alpaca_adapter.py` | Alpaca implementation (350 lines) |
| `broker/paper_trading_executor.py` | Orchestration (200 lines) |
| `broker/execution_logger.py` | Logging (300 lines) |
| `test_broker_integration.py` | Tests (400+ lines) |
| `PHASE_I_IMPLEMENTATION_GUIDE.md` | Detailed docs |
| `PHASE_I_SIGN_OFF.md` | Sign-off & verification |

## Testing

```bash
# Run all tests
python -m pytest test_broker_integration.py -v

# Run specific test
python -m pytest test_broker_integration.py::TestPaperTradingExecutor -v

# Run with coverage
python -m pytest test_broker_integration.py --cov=broker
```

## Troubleshooting

### "Live trading detected!"

Check environment variable:
```bash
echo $APCA_API_BASE_URL
# Should be: https://paper-api.alpaca.markets
# NOT: https://api.alpaca.markets
```

### "Failed to initialize broker: Invalid API credentials"

Verify credentials in Alpaca dashboard and set environment variables.

### "All orders rejected"

Check:
- RiskManager approvals (check logs)
- Account has $100k+ (minimum)
- Risk limits not too strict

## What Changed?

| Component | Status |
|-----------|--------|
| Signal generation | ✅ Unchanged |
| Risk management | ✅ Unchanged |
| ML models | ✅ Unchanged |
| Backtest logic | ✅ Unchanged |
| **Execution medium** | ✅ **Simulator → Real Broker** |

## What's Next?

### Week 1
- Validate orders execute
- Check fill prices
- Verify monitoring works
- Test auto-protection

### Week 2-4
- Monitor win rate
- Track execution slippage
- Analyze alert frequencies
- Fine-tune thresholds

### Week 5+
- Prepare for live trading (Phase II)
- Reduce position sizes
- Monitor equity curve closely

## Documentation

For detailed info, see:
- [Phase I Implementation Guide](./PHASE_I_IMPLEMENTATION_GUIDE.md) - Complete technical docs
- [Phase I Sign-Off](./PHASE_I_SIGN_OFF.md) - Safety verification & approval
- [Broker Adapter Interface](./broker/adapter.py) - API documentation
- [Test Suite](./test_broker_integration.py) - Usage examples

## Questions?

See [PHASE_I_IMPLEMENTATION_GUIDE.md](./PHASE_I_IMPLEMENTATION_GUIDE.md#troubleshooting) for detailed troubleshooting.

---

**Status**: ✅ Ready for paper trading  
**Date**: January 25, 2026  
**Confidence**: HIGH 🟢

