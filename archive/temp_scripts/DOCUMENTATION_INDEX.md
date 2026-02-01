# Trading Application Documentation Index

**Last Updated:** January 28, 2026  
**Status:** Architecture refactoring complete, production-ready

---

## Quick Links

1. **[README.md](README.md)** - Main project overview and quick start
2. **[SWING_ARCHITECTURE_REFACTOR.md](SWING_ARCHITECTURE_REFACTOR.md)** - Complete swing strategy architecture design
3. **[SWING_MIGRATION_GUIDE.md](SWING_MIGRATION_GUIDE.md)** - Developer migration guide for new architecture
4. **[POSITION_SCALING_GUIDE.md](POSITION_SCALING_GUIDE.md)** - Position sizing and risk management system

---

## Project Overview

This is a multi-phase trading system with:
- **Swing Trading**: Market-agnostic 5-philosophy container (US, India, crypto-ready)
- **Screener**: Daily OHLCV analysis with rule-based confidence scoring
- **Risk Management**: Trade intent guards, position limits, account protection
- **Execution**: Paper trading and live broker integration (Zerodha for India)
- **ML-Ready**: Metadata-aware intents for downstream scoring

---

## Architecture Summary

### Current (Phase I - Swing Trading)

```
strategies/
├── us/equity/swing/          # US swing strategies
│   ├── swing.py              # Container orchestrator
│   ├── swing_base.py         # Abstract base class
│   └── [5 philosophies]      # Trend pullback, momentum breakout, etc.
├── india/equity/swing/       # India swing strategies (same philosophies)
│   └── [same structure]
└── swing.py                  # Backward compatibility shim
```

**5 Swing Trading Philosophies:**
1. **Trend Pullback** - Shallow pullbacks in confirmed uptrends
2. **Momentum Breakout** - Strength continuation with volume confirmation
3. **Mean Reversion** - Snapbacks within valid uptrends
4. **Volatility Squeeze** - Volatility expansion after compression
5. **Event-Driven** - Predictable post-event behavior

Each strategy declares:
- Entry/exit logic
- Philosophy (why it works)
- Edge (competitive advantage)
- Risks (failure modes)
- Caveats (when NOT to use)
- Supported markets (US, India, crypto)

### Key Features

✅ **100% Backward Compatible**
- Old code: `from strategies.swing import SwingEquityStrategy` still works
- New code: `from strategies.us.equity.swing.swing import SwingEquityStrategy` recommended

✅ **Market-Agnostic**
- Same 5 philosophies replicated for US and India
- No hardcoded market hours, lot sizes, or broker assumptions
- Ready to extend to crypto, options, forex

✅ **ML-Ready**
- Each entry/exit intent carries philosophy metadata
- Downstream systems can weight by strategy, risks, caveats
- ML scoring can learn per-philosophy effectiveness

✅ **Production-Ready**
- Trade intent guards prevent behavioral violations
- Position limits enforced globally
- Risk management integrated
- Paper trading support
- Live trading with Zerodha (India) integration

---

## Getting Started

### For Users
1. Read [README.md](README.md) for project overview
2. Run screener: `python3 main.py` (real data) or `python3 demo.py` (synthetic)
3. Check daily results in logs or database

### For Developers
1. Read [README.md](README.md) for architecture
2. Review [SWING_ARCHITECTURE_REFACTOR.md](SWING_ARCHITECTURE_REFACTOR.md) for design decisions
3. Follow [SWING_MIGRATION_GUIDE.md](SWING_MIGRATION_GUIDE.md) for implementation patterns
4. See code examples in individual strategy files

### For ML Engineers
1. Understand metadata system in [SWING_ARCHITECTURE_REFACTOR.md](SWING_ARCHITECTURE_REFACTOR.md)
2. Extract philosophy data from entry intents (strategy_id, risks, caveats, edge)
3. Build custom scorers that weight by philosophy effectiveness
4. Validate improvements with backtester

---

## File Structure

```
trading_app/
├── README.md                              # Main project documentation ✅
├── DOCUMENTATION_INDEX.md                 # This file
├── SWING_ARCHITECTURE_REFACTOR.md         # Architecture design ✅
├── SWING_MIGRATION_GUIDE.md               # Developer guide ✅
├── requirements.txt                       # Python dependencies
│
├── config/                    # Configuration
│   ├── __init__.py
│   ├── scope.py              # Market/mode/broker scope
│   └── settings.py           # All configuration constants
│
├── strategies/                # Trading strategies
│   ├── base.py               # Strategy interface contract
│   ├── registry.py           # Strategy discovery
│   ├── swing.py              # Backward compat shim
│   ├── us/equity/swing/      # US swing strategies
│   └── india/equity/swing/   # India swing strategies
│
├── universe/                 # Symbols and instruments
│   ├── __init__.py
│   └── symbols.py
│
├── data/                     # Data loading
│   ├── price_loader.py      # Load OHLCV (yfinance)
│   └── synthetic_data.py    # Generate test data
│
├── features/                 # Technical indicators
│   └── feature_engine.py    # SMA, ATR, RSI, MACD, BB
│
├── scoring/                  # Confidence scoring
│   └── rule_scorer.py       # Rule-based (ML-ready)
│
├── risk/                     # Risk management
│   ├── trade_intent_guard.py  # Behavioral compliance
│   ├── risk_manager.py        # Position sizing
│   └── account_manager.py     # Account state
│
├── instruments/              # Instrument definitions
│   └── base.py
│
├── markets/                  # Market definitions
│   ├── base.py
│   ├── us_market.py         # Market hours, holidays
│   └── india_market.py      # Market hours, holidays
│
├── execution/                # Order execution
│   ├── base.py              # Execution interface
│   ├── paper_executor.py    # Paper trading
│   └── broker_executor.py   # Zerodha integration (India)
│
├── broker/                   # Broker integrations
│   └── zerodha_broker.py    # India equities (Zerodha)
│
├── core/                     # Core engine
│   └── engine.py            # Trading orchestrator
│
├── backtest/                 # Backtesting (future)
│   └── __init__.py
│
├── ml/                       # ML scoring (future)
│   └── __init__.py
│
└── monitoring/               # Logging and alerts (future)
    └── __init__.py
```

---

## Current Status

### ✅ Completed (Phase I)

- [x] Swing trading container architecture
- [x] 5 trading philosophies with full documentation
- [x] BaseSwingStrategy contract with metadata
- [x] Market-agnostic strategy implementations
- [x] Hierarchical folder structure (market/instrument/mode)
- [x] Backward compatibility maintained
- [x] Trade intent guards (behavioral compliance)
- [x] Risk management (position limits, sizing)
- [x] Paper trading support
- [x] Zerodha integration (India live trading)
- [x] Complete architecture documentation

### 🔶 In Progress / Future

- [ ] ML-based confidence scoring (replaces rules)
- [ ] Backtesting framework
- [ ] Day trading strategies
- [ ] Options strategies
- [ ] Crypto market support
- [ ] Real-time market data integration
- [ ] Advanced monitoring and alerting

---

## Key Concepts

### Strategy Container vs Philosophy

- **SwingEquityStrategy** = Container that loads and orchestrates philosophies
- **SwingTrendPullbackStrategy** = One philosophy with specific entry/exit logic
- **Each philosophy is independent** - can be enabled/disabled per market

### Metadata Flow

```
Entry Signal
    ↓
Philosophy generates intent
    ↓
Container attaches metadata (strategy_id, philosophy, risks, caveats, edge)
    ↓
ML/Risk systems use metadata
    ↓
Execution or rejection
```

### Backward Compatibility

```
Old (still works):
  from strategies.swing import SwingEquityStrategy

New (recommended):
  from strategies.us.equity.swing.swing import SwingEquityStrategy
  from strategies.india.equity.swing.swing import SwingEquityStrategy
```

---

## Common Tasks

### Run the Screener
```bash
# Real data (requires internet)
python3 main.py

# Test data (no network)
python3 demo.py
```

### Access US Swing Strategies
```python
from strategies.us.equity.swing.swing import SwingEquityStrategy

strategy = SwingEquityStrategy(config={
    "enabled_strategies": [
        "trend_pullback",
        "momentum_breakout",
    ]
})

intents = strategy.generate_entry_intents(market_data, portfolio_state)
```

### Access India Swing Strategies
```python
from strategies.india.equity.swing.swing import SwingEquityStrategy

strategy = SwingEquityStrategy()  # All 5 philosophies enabled by default
intents = strategy.generate_entry_intents(market_data, portfolio_state)
```

### View Philosophy Metadata
```python
strategy = SwingEquityStrategy()
for philosophy in strategy.get_strategy_philosophies():
    print(f"{philosophy['name']}")
    print(f"  Philosophy: {philosophy['philosophy']}")
    print(f"  Edge: {philosophy['edge']}")
    print(f"  Risks: {philosophy['risks']}")
    print(f"  Caveats: {philosophy['caveats']}")
```

---

## Architecture Decisions

1. **Market-agnostic strategies**: Same philosophy code works for US, India, crypto
2. **Philosophy-based metadata**: Each intent carries origin, risks, caveats for ML
3. **Container orchestrator**: SwingEquityStrategy loads and aggregates philosophies
4. **Backward compatibility shim**: Old code continues to work unchanged
5. **Hierarchical folders**: Enables scaling to multiple modes (swing, daytrade, options)

---

## Contact & Support

For architecture questions, refer to:
- **[SWING_ARCHITECTURE_REFACTOR.md](SWING_ARCHITECTURE_REFACTOR.md)** - Design rationale
- **[SWING_MIGRATION_GUIDE.md](SWING_MIGRATION_GUIDE.md)** - Implementation patterns
- Code comments in individual strategy files

---

## License & Disclaimer

Educational and research only. Not for live trading without extensive validation.
Always backtest, paper trade, and validate thoroughly before production use.

Past performance ≠ future results. Risk management is your responsibility.
