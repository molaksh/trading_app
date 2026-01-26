# Trade Ledger System - Architecture & Data Flow

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SWING TRADING SYSTEM ARCHITECTURE                    │
└─────────────────────────────────────────────────────────────────────────┘

                         ┌──────────────────────┐
                         │   Signal Generator   │
                         │   (after EOD close)  │
                         └──────────┬───────────┘
                                    │
                                    ▼
                        ┌─────────────────────────┐
                        │  Risk Manager Approval  │
                        │  (trade size, heat)     │
                        └────────┬────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────────────┐
                    │ PaperTradingExecutor           │
                    │ ├─ Execute Signal              │
                    │ ├─ Poll Order Fills            │
                    │ ├─ Evaluate Exit Signals       │
                    │ └─ Execute Exits               │
                    └────────┬─────────────────────┬──┘
                             │                     │
                ┌────────────┴──────────┐          │
                │                       │          │
                ▼                       ▼          │
           ┌─────────────┐        ┌──────────────┐│
           │ Broker Adapter       │ Trade Ledger ││  ◄─── NEW COMPONENT
           │ (Alpaca)             │ (Accounting) ││
           └─────────────┘        └──────────────┘│
                │                       │          │
                │                       │          │
                ▼                       ▼          ▼
           ┌──────────────────┐  ┌──────────────────────┐
           │ Execution Log    │  │ Trade Records        │
           │ (Events)         │  │ (Complete Trades)    │
           │                  │  │                      │
           │ • Signals        │  │ • BUY → SELL pairs   │
           │ • Orders         │  │ • Metrics calculated │
           │ • Fills          │  │ • Classified exits   │
           │ • Closes         │  │ • P&L recorded       │
           └──────────────────┘  └──────────────────────┘
             logs/                 logs/
             execution_log.jsonl    trade_ledger.json

                        ┌──────────────────────┐
                        │    Query Tools       │
                        │ • query_trades.py    │
                        │ • CLI filters        │
                        │ • Export (CSV/JSON)  │
                        └──────────────────────┘
```

## Trade Lifecycle Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COMPLETE TRADE LIFECYCLE                             │
└─────────────────────────────────────────────────────────────────────────────┘

DAY 1 (4 PM - MARKET CLOSE)
═══════════════════════════════════════════════════════════════════════════════

    Signal Generation
    ┌────────────────────┐
    │ Screen detects BUY │         Logged to:
    │ signal: AAPL       │    → execution_log.jsonl
    │ confidence: 4.5/5  │
    └─────────┬──────────┘
              │
              ▼
    Risk Manager Check
    ┌────────────────────────┐
    │ Risk: 1% of portfolio  │    Logged to:
    │ Position: 50 shares    │  → execution_log.jsonl
    │ Entry target: $180.00  │
    └─────────┬──────────────┘
              │
              ▼
    Order Submission
    ┌────────────────────────┐
    │ BUY 50 shares          │
    │ Order ID: entry_001    │    Logged to:
    │ Time: 4:10 PM (queue)  │  → execution_log.jsonl
    └─────────┬──────────────┘
              │
              ▼
    Metadata Stored
    ┌─────────────────────────────┐
    │ order_metadata[entry_001] = │
    │   (4.5, 90.00)              │  Tracked in:
    │   confidence, risk_amount   │  → executor.order_metadata
    └─────────────────────────────┘


DAY 2 (9:30 AM - MARKET OPEN)
═══════════════════════════════════════════════════════════════════════════════

    Pre-Market: Order fills
    ┌────────────────────────────┐
    │ BUY 50 AAPL @ $180.00      │    Logged to:
    │ Fill time: 9:30:05 AM      │  → execution_log.jsonl
    │ Order ID: entry_001        │
    └─────────┬──────────────────┘
              │
              ├──────────────────────────────────────┐
              │                                      │
              ▼                                      ▼
    Portfolio State Update          TRADE LEDGER: Entry Stored
    ┌──────────────────────────┐   ┌──────────────────────────────┐
    │ Portfolio                │   │ pending_entries[AAPL] = (    │
    │ ├─ AAPL: 50 @ $180.00    │   │   order_id: entry_001,       │
    │ ├─ equity: $99,000       │   │   timestamp: 2026-01-02...,  │
    │ └─ position opened       │   │   price: $180.00,            │
    │                          │   │   qty: 50,                   │
    └──────────────────────────┘   │   confidence: 4.5,           │
                                   │   risk_amount: $90.00        │
                                   │ )                            │
                                   │                              │
                                   │ Status: WAITING FOR EXIT     │
                                   └──────────────────────────────┘

    Throughout Day
    ┌────────────────────────────────┐
    │ • Monitor position             │  Logged to:
    │ • Check emergency exits        │ → execution_log.jsonl
    │ • Price ticks up (no action)   │
    └────────────────────────────────┘


DAY 3 (4 PM - MARKET CLOSE)
═══════════════════════════════════════════════════════════════════════════════

    Exit Signal Evaluation
    ┌──────────────────────────────┐
    │ AAPL up to $189.00           │
    │ Profit: +5.00% ($450)        │
    │ Target: 10% or 20 days       │   Logged to:
    │ → Profit target REACHED!     │ → execution_log.jsonl
    │                              │
    │ Exit Type: SWING_EXIT        │
    │ Reason: "Profit target..."   │
    └─────────┬────────────────────┘
              │
              ▼
    Exit Order Submission
    ┌──────────────────────────────┐
    │ SELL 50 AAPL @ market        │    Logged to:
    │ Order ID: exit_001           │  → execution_log.jsonl
    │ Time: 4:00 PM (queue)        │
    └─────────┬────────────────────┘
              │
              ▼
    Exit Order Fills
    ┌──────────────────────────────┐
    │ SELL 50 AAPL @ $189.00       │
    │ Fill time: 4:02 PM           │    Logged to:
    │ Order ID: exit_001           │  → execution_log.jsonl
    └─────────┬────────────────────┘
              │
              ├──────────────────────────────────────┐
              │                                      │
              ▼                                      ▼
    Portfolio State Update          TRADE LEDGER: Trade Finalized
    ┌──────────────────────────┐   ┌────────────────────────────────┐
    │ Portfolio                │   │ CREATE Trade Object:           │
    │ ├─ AAPL: CLOSED          │   │                                │
    │ ├─ equity: $99,450       │   │ trade_id: UUID()               │
    │ ├─ P&L: +$450            │   │ symbol: AAPL                   │
    │ └─ cash: $99,450         │   │                                │
    │                          │   │ ENTRY:                         │
    └──────────────────────────┘   │   order_id: entry_001          │
                                   │   timestamp: 2026-01-02 9:30   │
                                   │   price: $180.00               │
                                   │   qty: 50                      │
                                   │                                │
                                   │ EXIT:                          │
                                   │   order_id: exit_001           │
                                   │   timestamp: 2026-01-03 16:02  │
                                   │   price: $189.00               │
                                   │   qty: 50                      │
                                   │                                │
                                   │ CLASSIFICATION:                │
                                   │   exit_type: SWING_EXIT        │
                                   │   exit_reason: "Profit..."     │
                                   │                                │
                                   │ METRICS:                       │
                                   │   holding_days: 1              │
                                   │   gross_pnl: $450              │
                                   │   gross_pnl_pct: +5.00%        │
                                   │   net_pnl: $450 (no fees)      │
                                   │   net_pnl_pct: +5.00%          │
                                   │                                │
                                   │ RISK CONTEXT:                  │
                                   │   confidence: 4.5              │
                                   │   risk_amount: $90.00          │
                                   │   position_size: $9,000.00     │
                                   │                                │
                                   │ ADD TO LEDGER & PERSIST        │
                                   │ → logs/trade_ledger.json       │
                                   │                                │
                                   │ CLEAR pending_entries[AAPL]    │
                                   └────────────────────────────────┘

LATER - ANALYSIS
═══════════════════════════════════════════════════════════════════════════════

    Query Trades
    ┌──────────────────────────────────────────────────────┐
    │ $ python query_trades.py --all --sort pnl            │
    │                                                      │
    │ Found 1 trade:                                       │
    │                                                      │
    │ [abc12345] AAPL | Entry: $180.00 @ 2026-01-02       │
    │ Exit: $189.00 @ 2026-01-03 | Held 1 days           │
    │ SWING_EXIT (Profit target reached) | PnL: +5.00%    │
    └──────────────────────────────────────────────────────┘

    Summary Stats
    ┌──────────────────────────────────────────────────────┐
    │ $ python query_trades.py --stats                     │
    │                                                      │
    │ Total Trades:       1                                │
    │ Winners:            1 (100.0%)                       │
    │ Losers:             0                                │
    │ Avg Net P&L:        +$450.00 (+5.00%)                │
    │ Total Net P&L:      +$450.00                         │
    │ Avg Holding Days:   1.0                              │
    │ Swing Exits:        1                                │
    │ Emergency Exits:    0                                │
    └──────────────────────────────────────────────────────┘

    Export for Analysis
    ┌──────────────────────────────────────────────────────┐
    │ $ python query_trades.py --export-csv trades.csv     │
    │ ✓ Exported 1 trades to trades.csv                    │
    │                                                      │
    │ Opens in Excel/Pandas:                               │
    │ trade_id | symbol | entry_price | exit_price | P&L  │
    │ abc1... | AAPL | 180.00 | 189.00 | +5.00%           │
    └──────────────────────────────────────────────────────┘
```

## State Transitions

```
Entry Order Lifecycle:
─────────────────────

    submitted
         │
         ▼
    pending_orders[order_id] = symbol
         │
         ▼
    FILL CONFIRMED
         │
         ├─ Poll detects fill
         │
         ├─ Log to execution_log ✓
         │
         ├─ Update portfolio ✓
         │
         └─ Store in pending_entries[symbol] ←─── NEW TRADE STARTED
               (awaiting exit)


Exit Order Lifecycle:
────────────────────

    EXIT SIGNAL (from pending_entries[symbol])
         │
         ▼
    submit SELL order
         │
         ├─ Log to execution_log ✓
         │
         ▼
    FILL CONFIRMED
         │
         ├─ Log to execution_log ✓
         │
         ├─ Update portfolio ✓
         │
         └─ FINALIZE TRADE ←─────── NEW LOGIC
              ├─ Retrieve entry from pending_entries[symbol] ✓
              ├─ Create Trade object ✓
              ├─ Calculate metrics ✓
              ├─ Add to ledger ✓
              ├─ Persist to JSON ✓
              └─ Clear pending_entries[symbol] ✓


Complete State Machine:
──────────────────────

Entry Order               Exit Order                 Trade Ledger
submitted ─────┐         submitted ─────┐           
               │                        │           
               ▼                        │           
           pending ─────┐               │           
               │         │              │           
               ▼         │              │           
            filled       │              │           
               │         │              │           
               └─────────┼──→ pending_entries[symbol]
                         │              │
                         │              │
                         ▼              │
                      pending ─────┐    │
                         │         │    │
                         ▼         │    │
                      filled       │    │
                         │         │    │
                         └─────────┼──→ _finalize_trade()
                                  │         │
                                  │         ▼
                                  │    Create Trade()
                                  │         │
                                  │         ▼
                                  │    ledger.add_trade()
                                  │         │
                                  │         ▼
                                  │    persist JSON ✓
                                  │         │
                                  └────────→ COMPLETE ✓
```

## Data Model

```
┌──────────────────────────────────────────────────────────────┐
│                        TRADE OBJECT                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  IDENTITY                                                    │
│  ├─ trade_id: "4a49512e-73b3-46f3-a2eb-151a09709367"       │
│  └─ symbol: "AAPL"                                           │
│                                                              │
│  ENTRY (BUY FILL)                                           │
│  ├─ entry_order_id: "entry_001"                             │
│  ├─ entry_timestamp: "2026-01-10T09:30:00"                 │
│  ├─ entry_price: 180.00                                     │
│  └─ entry_quantity: 50                                      │
│                                                              │
│  EXIT (SELL FILL)                                           │
│  ├─ exit_order_id: "exit_001"                               │
│  ├─ exit_timestamp: "2026-01-15T16:00:00"                  │
│  ├─ exit_price: 189.00                                      │
│  └─ exit_quantity: 50                                       │
│                                                              │
│  CLASSIFICATION                                              │
│  ├─ exit_type: "SWING_EXIT"                                 │
│  └─ exit_reason: "Profit target reached (10%)"              │
│                                                              │
│  PERFORMANCE METRICS                                         │
│  ├─ holding_days: 5                                         │
│  ├─ gross_pnl: 450.00                                       │
│  ├─ gross_pnl_pct: 5.0                                      │
│  ├─ fees: 0.0                                               │
│  ├─ net_pnl: 450.00                                         │
│  └─ net_pnl_pct: 5.0                                        │
│                                                              │
│  RISK CONTEXT (at entry)                                    │
│  ├─ confidence: 4.5                                         │
│  ├─ risk_amount: 90.00                                      │
│  └─ position_size: 9000.00                                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘

              ↓↓↓ PERSISTED TO ↓↓↓

    {
      "trade_id": "4a49512e-...",
      "symbol": "AAPL",
      "entry_order_id": "entry_001",
      "entry_timestamp": "2026-01-10T09:30:00",
      "entry_price": 180.0,
      "entry_quantity": 50,
      "exit_order_id": "exit_001",
      "exit_timestamp": "2026-01-15T16:00:00",
      "exit_price": 189.0,
      "exit_quantity": 50,
      "exit_type": "SWING_EXIT",
      "exit_reason": "Profit target reached (10%)",
      "holding_days": 5,
      "gross_pnl": 450.0,
      "gross_pnl_pct": 5.0,
      "fees": 0.0,
      "net_pnl": 450.0,
      "net_pnl_pct": 5.0,
      "confidence": 4.5,
      "risk_amount": 90.0,
      "position_size": 9000.0
    }

              ↓↓↓ STORED IN ↓↓↓

              logs/trade_ledger.json
```

## Separation of Concerns

```
┌────────────────────────────────────────────────────────────────────┐
│              EVENTS vs TRADES (Different Purposes)                 │
└────────────────────────────────────────────────────────────────────┘

EXECUTION LOG (execution_log.jsonl)           TRADE LEDGER (trade_ledger.json)
─────────────────────────────────────────     ──────────────────────────────
Granular, raw events                          Synthesized, complete records
Low-level (operations)                        High-level (results)

• signal_generated                            • trade (complete BUY→SELL)
  ├─ symbol, confidence, timestamp            ├─ symbol, entry/exit prices
  └─ features                                 ├─ holding period
                                              ├─ P&L (gross/net)
• order_submitted                             ├─ exit classification
  ├─ order_id, symbol, quantity              └─ confidence & risk context
  └─ risk_amount
                                         ONE RECORD = ONE COMPLETE TRADE
• order_filled
  ├─ order_id, price, qty, timestamp
  └─ fill_time
                                         Query: "Show me all swing exits"
• position_closed                        → Returns 10 TRADES (not 20 events)
  ├─ entry_price, exit_price
  ├─ P&L (calculated at close)          Export: CSV with trade performance
  └─ hold days                          → Easy analysis in Excel/Python

Query: "Show me all fill events"
→ Returns 20+ EVENTS (entry fill + exit fill per trade)

Use Case: Debugging                     Use Case: Performance Analysis
"Why did this order fill late?"         "Which symbols are most profitable?"
```

---

**See TRADE_LEDGER_README.md for complete documentation**
