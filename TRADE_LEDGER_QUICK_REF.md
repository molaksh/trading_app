# Trade Ledger Quick Reference

## At a Glance

The Trade Ledger transforms **raw execution events** into **completed trades** with full accounting.

### One Trade = Complete Lifecycle
```
BUY → HOLD → SELL = One Trade Record

Contains:
✓ Entry/exit timestamps & prices
✓ Profit/loss (gross and net)
✓ Holding period
✓ Exit classification (swing vs emergency)
✓ Exit reason
✓ Entry confidence & risk amount
```

### Data Model

```python
Trade {
  # Identity
  trade_id: UUID
  symbol: str

  # Entry
  entry_order_id: str
  entry_timestamp: ISO datetime
  entry_price: float
  entry_quantity: float

  # Exit
  exit_order_id: str
  exit_timestamp: ISO datetime
  exit_price: float
  exit_quantity: float

  # Classification
  exit_type: "SWING_EXIT" | "EMERGENCY_EXIT"
  exit_reason: str

  # Metrics
  holding_days: int
  gross_pnl: float
  gross_pnl_pct: float
  net_pnl: float
  net_pnl_pct: float
  fees: float

  # Risk context
  confidence: float (0-5.0)
  risk_amount: float
  position_size: float
}
```

## How It Works

### 1. Entry Fill → Pending Entry
When buy order fills:
```
Order fills @ $180.00
  ↓
Stored in pending_entries (in-memory)
  ↓
Waits for exit signal
```

### 2. Exit Signal → Exit Order
When exit criteria met:
```
Profit target reached
  ↓
Submit close order
  ↓
Order fills @ $189.00
```

### 3. Exit Fill → Completed Trade
When exit order fills:
```
Exit fills @ $189.00
  ↓
Create Trade object with entry + exit
  ↓
Calculate all metrics
  ↓
Add to ledger
  ↓
Persist to trade_ledger.json
```

## Common Queries

```bash
# Show all trades
python query_trades.py --all

# Specific symbol
python query_trades.py --symbol AAPL

# Only swing exits
python query_trades.py --exit-type SWING_EXIT

# Only emergency exits
python query_trades.py --exit-type EMERGENCY_EXIT

# Profitable trades (>0%)
python query_trades.py --min-pnl 0 --all

# Losing trades (<0%)
python query_trades.py --max-pnl 0 --all

# Summary statistics
python query_trades.py --stats

# Export to CSV
python query_trades.py --export-csv trades.csv --all

# Export to JSON
python query_trades.py --export-json trades.json --all

# Complex query: AAPL swing exits >5% profit
python query_trades.py \
  --symbol AAPL \
  --exit-type SWING_EXIT \
  --min-pnl 5.0 \
  --all
```

## In Code

```python
from broker.trade_ledger import TradeLedger

ledger = TradeLedger()

# Query examples
all_trades = ledger.get_trades()
winners = ledger.get_trades(min_pnl_pct=0.0)
swing_exits = ledger.get_trades(exit_type="SWING_EXIT")
aapl_trades = ledger.get_trades(symbol="AAPL")

# Stats
stats = ledger.get_summary_stats()
print(f"Win rate: {stats['win_rate_pct']:.1f}%")
print(f"Avg P&L: {stats['avg_net_pnl_pct']:+.2f}%")

# Export
ledger.export_to_csv("trades.csv")
ledger.export_to_json("trades.json")

# Access individual trade
for trade in winners:
    print(f"{trade.symbol}: {trade.net_pnl_pct:+.2f}%")
```

## Key Features

| Feature | Details |
|---------|---------|
| **Append-Only** | Trades never modified after creation |
| **Persistent** | Auto-saved to `logs/trade_ledger.json` |
| **Queryable** | Filter by symbol, date, exit type, profitability |
| **Exportable** | CSV and JSON formats |
| **Accurate** | Calculates gross P&L, net P&L (with fees), holding period |
| **Classified** | Distinguishes swing vs emergency exits |
| **Safe** | Logging failures don't block trading |

## Files

| File | Purpose |
|------|---------|
| `broker/trade_ledger.py` | Core Trade and TradeLedger classes |
| `broker/paper_trading_executor.py` | Integration into executor (pending_entries, finalization) |
| `query_trades.py` | Command-line query tool |
| `demo_trade_ledger.py` | Demonstration of all features |
| `logs/trade_ledger.json` | Persisted ledger (auto-created) |
| `TRADE_LEDGER_README.md` | Full documentation |

## Design Separation

### ❌ Events (execution_log.jsonl)
```
signals_generated
orders_submitted
order_filled
position_closed
...
(Raw, granular events)
```

### ✅ Trades (trade_ledger.json)
```
Complete lifecycle records
Entry + Exit + Metrics
One record = one complete trade
(Synthesized, higher-level)
```

## Integration Point

```python
executor = PaperTradingExecutor(
    broker=broker,
    risk_manager=risk_manager,
    trade_ledger=TradeLedger(),  # ← Integrated here
    exit_evaluator=exit_eval,
)

# Automatically:
# 1. Tracks entry fills in pending_entries
# 2. On exit fill, creates Trade object
# 3. Adds to ledger
# 4. Persists to disk
# 5. Clears pending entry
```

## Example Output

### Statistics
```
TRADE LEDGER SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Trades:       42
Winners:            28 (66.7%)
Losers:             14
Avg Net P&L:        +$156.25 (+1.85%)
Total Net P&L:      +$6,562.50
Avg Holding Days:   5.2

Exit Breakdown:
  Swing Exits:      38
  Emergency Exits:  4
```

### Query Results
```
Found 6 trades:

[abc12345] AAPL | Entry: $180.00 @ 2026-01-10 | Exit: $189.00 @ 2026-01-15
Held 5 days | SWING_EXIT (Profit target reached) | PnL: +5.00% ($+450.00)

[def67890] GOOGL | Entry: $150.00 @ 2026-01-12 | Exit: $147.00 @ 2026-01-20
Held 8 days | SWING_EXIT (Max holding period) | PnL: -2.00% ($-90.00)

[ghi34567] MSFT | Entry: $420.00 @ 2026-01-16 | Exit: $431.00 @ 2026-01-22
Held 6 days | SWING_EXIT (Profit target reached) | PnL: +2.62% ($+220.00)
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No trades in ledger | Complete at least one full trade cycle (entry fill → exit fill) |
| Trade not appearing | Check exit order filled successfully in execution logs |
| Query returns empty | Use `--all --stats` to verify ledger has trades |
| Ledger file missing | Auto-created on first completed trade |

## Next Steps

1. **Run actual trades** - Complete trades will auto-populate ledger
2. **Query results** - Use `python query_trades.py` to analyze
3. **Export for analysis** - Use CSV/JSON exports for external tools
4. **Monitor performance** - Check `--stats` regularly

---

**File**: `TRADE_LEDGER_README.md` for full documentation
