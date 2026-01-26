# TRADE LEDGER SYSTEM

Complete trade lifecycle accounting for swing trading system.

## Overview

The Trade Ledger maintains a clean, queryable history of **completed trades** (BUY → SELL).

This is **separate from event logging**:
- **Events** = Raw signals, orders, fills (logged to `execution_log.jsonl`)
- **Trades** = Synthesized complete lifecycles with performance metrics (logged to `trade_ledger.json`)

## Architecture

```
Entry Fill
    ↓
Stored in pending_entries (executor)
    ↓
Exit Signal Generated
    ↓
Exit Order Submitted
    ↓
Exit Fill Confirmed
    ↓
Trade Finalized & Logged to Ledger
    ↓
Cleared from pending_entries
```

## Core Data Structure: Trade

Each trade records:

### Identity
- **trade_id**: UUID (unique identifier)
- **symbol**: Ticker symbol

### Entry (BUY)
- **entry_order_id**: Broker order ID
- **entry_timestamp**: Fill timestamp (ISO format)
- **entry_price**: Fill price per share
- **entry_quantity**: Fill quantity

### Exit (SELL)
- **exit_order_id**: Broker order ID
- **exit_timestamp**: Fill timestamp (ISO format)
- **exit_price**: Fill price per share
- **exit_quantity**: Fill quantity

### Classification
- **exit_type**: `"SWING_EXIT"` or `"EMERGENCY_EXIT"`
- **exit_reason**: Human-readable reason (e.g., "Profit target reached (10%)", "Position loss exceeds 3%")

### Performance Metrics
- **holding_days**: Days between entry and exit
- **gross_pnl**: Exit value - Entry value (before fees)
- **gross_pnl_pct**: Percentage gain/loss (before fees)
- **fees**: Total fees (entry + exit)
- **net_pnl**: Gross P&L - Fees
- **net_pnl_pct**: Percentage gain/loss (after fees)

### Risk Context (at entry)
- **confidence**: Signal confidence (0-5.0)
- **risk_amount**: Risk amount at entry
- **position_size**: Entry value (entry_price × entry_quantity)

## Usage

### 1. Trade Ledger Automatically Tracks Trades

When executor processes a trade:

```python
# In PaperTradingExecutor

# Entry fill → store in pending_entries
self.pending_entries[symbol] = (
    order_id,
    fill_timestamp,
    fill_price,
    quantity,
    confidence,
    risk_amount,
)

# Exit fill → create Trade object and finalize
self._finalize_trade(
    symbol=symbol,
    exit_order_id=order_id,
    exit_timestamp=timestamp,
    exit_price=price,
    exit_quantity=qty,
    exit_type="SWING_EXIT",  # or "EMERGENCY_EXIT"
    exit_reason="Profit target reached (10%)",
)

# Internally:
# 1. Creates Trade object from entry + exit fills
# 2. Calculates all metrics
# 3. Adds to ledger
# 4. Persists to logs/trade_ledger.json
# 5. Clears from pending_entries
```

### 2. Query Trades

**Basic queries:**

```python
from broker.trade_ledger import TradeLedger

ledger = TradeLedger()

# All trades
all_trades = ledger.get_trades()

# By symbol
aapl_trades = ledger.get_trades(symbol="AAPL")

# By exit type
swing_trades = ledger.get_trades(exit_type="SWING_EXIT")
emergency_trades = ledger.get_trades(exit_type="EMERGENCY_EXIT")

# By profitability
winners = ledger.get_trades(min_pnl_pct=0.0)
losers = ledger.get_trades(max_pnl_pct=-0.0)

# By date range
recent = ledger.get_trades(start_date="2026-01-20T00:00:00")

# Combined filters
query = ledger.get_trades(
    symbol="AAPL",
    exit_type="SWING_EXIT",
    min_pnl_pct=5.0,
)
```

**Summary statistics:**

```python
stats = ledger.get_summary_stats()

# Returns:
{
    "total_trades": 10,
    "winners": 6,
    "losers": 4,
    "win_rate_pct": 60.0,
    "avg_net_pnl": 125.50,
    "avg_net_pnl_pct": 1.25,
    "total_net_pnl": 1255.00,
    "avg_holding_days": 5.2,
    "swing_exits": 8,
    "emergency_exits": 2,
}
```

### 3. Export Trades

**To CSV:**

```python
ledger.export_to_csv("trades.csv")
# Columns: trade_id, symbol, entry_order_id, entry_price, ...
```

**To JSON:**

```python
ledger.export_to_json("trades.json", pretty=True)
```

### 4. Command-Line Tool

Query trades from terminal:

```bash
# All trades sorted by P&L
python query_trades.py --all --sort pnl

# Specific symbol
python query_trades.py --symbol AAPL

# Profitable trades only
python query_trades.py --min-pnl 0

# Emergency exits
python query_trades.py --exit-type EMERGENCY_EXIT

# Statistics
python query_trades.py --stats

# Export to CSV/JSON
python query_trades.py --export-csv trades.csv
python query_trades.py --export-json trades.json

# Complex query
python query_trades.py \
  --symbol AAPL \
  --exit-type SWING_EXIT \
  --min-pnl 5.0 \
  --sort pnl \
  --limit 10
```

## Design Principles

### 1. Append-Only Ledger
- Trades are **never modified** after creation
- Only new trades are appended
- Ensures audit trail integrity

### 2. Separate from Events
- Event logging (signals, orders, fills) is independent
- Trade accounting is synthesized from fills
- Strategy logic does NOT depend on trade logging

### 3. Failure-Safe
- Logging failures do NOT block execution
- Try/except wraps all ledger operations
- System continues even if ledger write fails

### 4. Persistence
- Ledger persists to `logs/trade_ledger.json`
- Survives process restarts
- Automatically loaded on initialization

### 5. Reconstruct After Restart
If system restarts between entry and exit:
- Pending entries are lost (in-memory state)
- Entry fills can be reconstructed from execution logs
- Trade finalization can be manually reconstructed if needed

## Example Workflow

```
DAY 1 (4 PM - EOD):
├─ Signal generated: BUY AAPL (confidence=4.5)
├─ Order approved by RiskManager
├─ Order submitted to Alpaca
└─ Order ID: orde_001, Risk: $90

DAY 2 (9:30 AM - Market Open):
├─ Order fills @ $180.00 × 50 shares
├─ Fill logged to execution_log
├─ Stored in pending_entries:
│  └─ AAPL → (orde_001, timestamp, $180.00, 50, 4.5, $90)
└─ Poll continues monitoring position

DAY 3 (4 PM - EOD):
├─ Exit signal evaluated
├─ Profit target reached (5%) → SWING_EXIT
├─ Close order submitted: orde_002
└─ Close order fills @ $189.00 × 50 shares

DAY 3 (After Close):
├─ Exit fill logged to execution_log
├─ Trade finalized:
│  ├─ entry: $180.00 × 50 = $9,000
│  ├─ exit: $189.00 × 50 = $9,450
│  ├─ gross P&L: $450 (+5%)
│  ├─ net P&L: $450 (fees: $0)
│  └─ holding: 2 days
├─ Trade added to ledger
├─ Persisted to trade_ledger.json
└─ Cleared from pending_entries

LATER:
├─ Query: python query_trades.py --symbol AAPL
└─ Output: AAPL +5.00% (SWING_EXIT) held 2 days
```

## File Locations

- **Ledger file**: `logs/trade_ledger.json`
- **Query tool**: `query_trades.py`
- **Demo**: `demo_trade_ledger.py`
- **Execution events**: `logs/execution_log.jsonl` (separate from trades)

## Integration Points

### PaperTradingExecutor

```python
executor = PaperTradingExecutor(
    broker=broker,
    risk_manager=risk_manager,
    trade_ledger=ledger,  # Integrated
    exit_evaluator=exit_eval,
)

# On entry fill
executor.pending_entries  # Tracks entry

# On exit fill
executor._finalize_trade()  # Creates and logs Trade
```

### Example: Complete Trade Lifecycle

```python
# Trade creation from fills
trade = create_trade_from_fills(
    symbol="AAPL",
    entry_order_id="orde_001",
    entry_fill_timestamp="2026-01-10T09:30:00",
    entry_fill_price=180.00,
    entry_fill_quantity=50,
    exit_order_id="orde_002",
    exit_fill_timestamp="2026-01-13T16:00:00",
    exit_fill_price=189.00,
    exit_fill_quantity=50,
    exit_type="SWING_EXIT",
    exit_reason="Profit target reached (10%)",
    confidence=4.5,
    risk_amount=90.0,
)

# Add to ledger
ledger.add_trade(trade)

# Access trade
print(trade.net_pnl_pct)  # +5.0
print(trade.holding_days)  # 3
```

## Troubleshooting

### No trades in ledger?
- Check if any complete trades have executed (entry + exit fills)
- For now, use `demo_trade_ledger.py` to test functionality

### Trade not appearing after exit?
- Verify exit order filled successfully
- Check execution logs for fill confirmation
- Inspect pending_entries for stuck entries

### Ledger file missing?
- First run auto-creates `logs/trade_ledger.json`
- If deleted, system will create new ledger on next trade

### Queries returning no results?
- Check ledger with `query_trades.py --all --stats`
- Verify date/time formats if using date filters (ISO format)
- Use less restrictive filters to debug

## Future Enhancements

- [ ] Partial fills handling (scaling in/out)
- [ ] Multi-leg trades (multiple entries/exits)
- [ ] Performance analytics per symbol
- [ ] Monthly/weekly performance reports
- [ ] Risk metrics (Sharpe ratio, max drawdown)
- [ ] Monte Carlo analysis of past trades
