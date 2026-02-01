# India NSE Paper Trading Setup

## Overview

Complete production-quality paper trading system for NSE (National Stock Exchange) India with **complete isolation** from US trading systems.

**SCOPE**: `paper_nse_simulator_swing_india`  
**Market**: India (NSE)  
**Broker**: NSE Simulated Broker  
**Mode**: Swing Trading  
**Status**: ✅ Running

## Container Information

### Service Name
`paper-nse-swing-india`

### Docker Image
`paper-nse-swing-india`

### Environment Variables
```
ENV=paper                                          # Paper trading mode
BROKER=nse_simulator                               # Simulated broker
MODE=swing                                         # Swing strategy
MARKET=india                                       # NSE India
PERSISTENCE_ROOT=/app/persist                      # Storage directory
MARKET_TIMEZONE=Asia/Kolkata                       # IST timezone
ENTRY_WINDOW_MINUTES_BEFORE_CLOSE=20              # Entry timing
SWING_EXIT_DELAY_MINUTES_AFTER_CLOSE=15           # Exit timing
```

## Market Hours (IST)

| Session | Time (IST) | Notes |
|---------|-----------|-------|
| Pre-open | 9:00 AM - 9:15 AM | Price discovery |
| Regular | 9:15 AM - 3:30 PM | Main trading session |
| Post-market | 3:40 PM - 4:00 PM | Settlement |

**Swing Entry Window**: 20 minutes before close (3:10 PM - 3:30 PM IST)

## Universe

**80+ curated NSE stocks** for swing trading:
- NIFTY 50 stocks (blue-chip tier-1)
- Select NIFTY Next 50 (tier-2 growth)

### Top 20 Holdings
RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, HDFC, LT, SBIN, MARUTI, BAJAJFINSV, DRREDDY, WIPRO, AXISBANK, SUNPHARMA, ASIANPAINT, ITC, BHARTIARTL, LTT, ADANIPORTS, ULTRACEMCO

View full list: [universe/nse_swing_universe.py](universe/nse_swing_universe.py)

## Trading Architecture

### Broker Simulation
- **Source of Truth**: NSESimulatedBrokerAdapter
- **Order Execution**: Place before 3:30 PM IST → Execute at next-day 9:15 AM open
- **Slippage**: ±0.05%-0.15% realistic simulation
- **Brokerage**: ₹20 flat per order
- **State Persistence**: `state/<scope>/broker_state.json`

### Strategies
**Shared from core** (no duplication):
- Swing Trend Pullback
- Swing Momentum Breakout
- Swing Mean Reversion
- Swing Volatility Squeeze
- Swing Event Driven

Location: `core/strategies/equity/swing/`

### Market Hours Policy
- **Class**: `IndiaEquityMarketHours`
- **Location**: `policies/market_hours/india_equity_market_hours.py`
- **Holiday Calendar**: NSE holidays + weekends

### Data Provider
- **Class**: `NSEDataProvider`
- **Location**: `data/nse_data_provider.py`
- **Cache**: `data/<scope>/ohlcv/<symbol>_daily.csv`
- **Mock Data**: Built-in test data generator

## Complete Isolation from US

### Data Isolation
```
Docker Volume: india-data
├── logs/
│   └── execution_log.jsonl (India trades only)
├── models/
│   └── <strategy>/v00001/ (India ML models only)
├── state/
│   ├── broker_state.json (NSE simulator state)
│   └── scheduler_state.json (India scheduler)
└── data/
    └── trades.jsonl (India trades only)
```

### US Container (Unchanged)
- **SCOPE**: `paper_alpaca_swing_us`
- **Docker Volume**: `us-data` (isolated)
- **Broker**: Alpaca Paper Trading
- **Data**: Separate NSE India data has zero influence

### Configuration Isolation
All settings environment-driven:
- US container: `MARKET_TIMEZONE=America/New_York`
- India container: `MARKET_TIMEZONE=Asia/Kolkata`
- Different entry windows (5 min US vs 20 min India)
- Different exit delays (15 min both, but different timezone effects)

## Running the Container

### Start India Container Only
```bash
# Using docker-compose
docker-compose up -d paper-nse-swing-india

# Or using custom script
./run_india_paper_swing.sh

# Or manual docker
docker run -d \
  --name paper-nse-swing-india \
    -v $(pwd)/logs:/app/persist \
  -e ENV=paper \
  -e BROKER=nse_simulator \
  -e MODE=swing \
  -e MARKET=india \
    -e PERSISTENCE_ROOT=/app/persist \
  -e MARKET_TIMEZONE=Asia/Kolkata \
  -e ENTRY_WINDOW_MINUTES_BEFORE_CLOSE=20 \
  -e SWING_EXIT_DELAY_MINUTES_AFTER_CLOSE=15 \
  paper-nse-swing-india python -m execution.scheduler
```

### Start Both Containers (US + India)
```bash
docker-compose up -d

# Or separately
docker-compose up -d paper-alpaca-swing-us
docker-compose up -d paper-nse-swing-india
```

## Monitoring

### View India Container Logs
```bash
docker logs -f paper-nse-swing-india

# Last 50 lines
docker logs --tail 50 paper-nse-swing-india

# Follow in real-time
docker logs -f --tail 20 paper-nse-swing-india
```

### Check Running Containers
```bash
docker ps --filter "name=paper-"
```

### Verify Isolation
```bash
# Check US container SCOPE
docker exec paper-alpaca-swing-us ls -la /app/logs/paper_alpaca_swing_us/

# Check India container SCOPE
docker exec paper-nse-swing-india ls -la /app/logs/paper_nse_simulator_swing_india/
```

## SCOPE System

All data organized by SCOPE:

### US SCOPE
`paper_alpaca_swing_us`
- Alpaca API connection
- US market hours (9:30 AM-4:00 PM ET)
- 500+ liquid equities
- Separate ML models

### India SCOPE
`paper_nse_simulator_swing_india`
- NSE Simulator (no real API)
- India market hours (9:15 AM-3:30 PM IST)
- 80+ curated stocks
- Separate ML models

### Cross-Market Isolation
✅ Separate Docker volumes  
✅ Separate broker implementations  
✅ Separate market hours policies  
✅ Separate data providers  
✅ Separate ML systems  
✅ Zero configuration conflict  
✅ Independent restart/crash behavior  

## State Persistence

### Broker State
- **File**: `state/<scope>/broker_state.json`
- **Persists**: Positions, orders, account balance
- **Survives**: Container restart
- **Auto-load**: On scheduler startup

### Trade Ledger
- **File**: `logs/<scope>/trades.jsonl`
- **Format**: JSON lines (one trade per line)
- **Immutable**: Append-only for audit trail
- **Includes**: Entry, exit, P&L, duration

### ML State
- **Directory**: `models/<scope>/`
- **Versioning**: v00001, v00002, etc.
- **Active**: `active.json` points to current version
- **Features/Labels**: `features/` and `labels/` subdirs

## Daily Schedule

### 2:50 PM IST (9:20 AM ET)
- Scheduler tick
- Market hours check
- Recon cadence evaluation

### 3:00 PM - 3:10 PM IST (9:30 AM - 9:40 AM ET)
- Signal generation (after-hours analysis)
- Guard validation
- Risk check

### 3:10 PM - 3:30 PM IST (9:40 AM - 10:00 AM ET)
**Entry Window** ⚡
- Submit market orders
- NSE simulator records orders as pending
- Set to execute at next-day 9:15 AM

### 3:30 PM IST (10:00 AM ET)
- Market close
- Pending orders recorded for next-day execution

### Next Day 9:15 AM IST (11:45 PM ET previous day)
- Orders execute at market open with simulated slippage
- Positions opened
- Add to trade ledger

### 3:30 PM IST (Next day)
- Exit evaluation window
- 15 minutes after close for swing exit decisions
- Positions closed on meeting exit criteria

## Configuration Files

### [config/india_config.py](config/india_config.py)
India-specific settings:
- Market timezone (Asia/Kolkata)
- Trading windows (entry 20 min before close)
- Broker config (₹10,00,000 starting capital)
- Risk limits (20% max position, 5 total)
- Brokerage (₹20 per order)

### [policies/market_hours/india_equity_market_hours.py](policies/market_hours/india_equity_market_hours.py)
NSE market hours policy:
- Trading session times
- Holiday calendar
- Timezone handling
- Next trading day calculation

### [universe/nse_swing_universe.py](universe/nse_swing_universe.py)
NSE stock universe:
- 80+ curated stocks
- NIFTY 50 + selected NIFTY Next 50
- Metadata (sector, volatility, etc.)
- Universe validation

### [data/nse_data_provider.py](data/nse_data_provider.py)
NSE OHLCV data:
- Historical data fetching
- Caching layer
- Mock data for testing
- Cache-first architecture

### [broker/nse_simulator_adapter.py](broker/nse_simulator_adapter.py)
NSE Simulated Broker:
- Order management
- Position tracking
- State persistence
- Slippage simulation
- Account balance tracking

## Development & Testing

### Running with Mock Data
```bash
from data.nse_data_provider import NSEDataProvider, create_mock_data_for_testing

provider = NSEDataProvider(cache_dir="/app/logs/paper_nse_simulator_swing_india/data")

# Create mock data for testing
mock_data = create_mock_data_for_testing(
    symbol="RELIANCE",
    days=200,
    starting_price=2500.0
)
```

### Testing Order Execution
```bash
from broker.nse_simulator_adapter import NSESimulatedBrokerAdapter
from pathlib import Path

adapter = NSESimulatedBrokerAdapter(state_dir=Path("/app/logs/paper_nse_simulator_swing_india/state"))

# Submit order
order = adapter.submit_market_order(
    symbol="TCS",
    side="buy",
    quantity=10,
    notes="Test order"
)

# Simulate next-day open
adapter.execute_pending_orders(
    open_prices={"TCS": 3550.0}  # Simulated open price
)
```

## Troubleshooting

### Container Exiting Immediately
Check logs:
```bash
docker logs paper-nse-swing-india
```

Common issues:
- Invalid SCOPE: Update `config/scope.py` ALLOWED_SCOPES
- Missing module: Rebuild image `docker build -f Dockerfile.india -t paper-nse-swing-india .`
- Timezone error: Verify `MARKET_TIMEZONE=Asia/Kolkata`

### Order Not Executing
1. Check market hours: Is 3:10 PM-3:30 PM IST?
2. Check account balance: `docker exec paper-nse-swing-india cat /app/logs/paper_nse_simulator_swing_india/state/broker_state.json`
3. Check pending orders: Same file, look for `pending_orders` array

### Reconciliation Failures
If startup reconciliation reports errors:
```bash
docker logs paper-nse-swing-india | grep -i "reconciliation"
```

This is expected if broker_state.json is missing - it will auto-initialize.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│          Docker Compose (Multi-Market)                   │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────────────┐   ┌──────────────────────┐    │
│  │ paper-alpaca-swing-us │   │paper-nse-swing-india │    │
│  ├──────────────────────┤   ├──────────────────────┤    │
│  │ SCOPE:               │   │ SCOPE:               │    │
│  │ paper_alpaca_swing_us│   │paper_nse_simulator_  │    │
│  │                      │   │swing_india           │    │
│  │ Volume: us-data      │   │ Volume: india-data   │    │
│  ├──────────────────────┤   ├──────────────────────┤    │
│  │ AlpacaAdapter        │   │ NSESimulatedAdapter  │    │
│  │ ├─ Real API          │   │ ├─ Simulated (No API)│    │
│  │ ├─ Alpaca Paper      │   │ ├─ Full simulation   │    │
│  │ └─ 500+ stocks       │   │ └─ 80+ stocks        │    │
│  ├──────────────────────┤   ├──────────────────────┤    │
│  │ US Equity Hours      │   │ NSE Market Hours     │    │
│  │ ├─ 9:30 AM-4:00 PM   │   │ ├─ 9:15 AM-3:30 PM  │    │
│  │ ├─ America/New_York  │   │ ├─ Asia/Kolkata      │    │
│  │ └─ Est. holidays     │   │ └─ NSE holidays      │    │
│  ├──────────────────────┤   ├──────────────────────┤    │
│  │ SwingEquity (Shared) │   │ SwingEquity (Shared) │    │
│  │ ├─ Trend Pullback    │   │ ├─ Trend Pullback    │    │
│  │ ├─ Momentum Breakout │   │ ├─ Momentum Breakout │    │
│  │ ├─ Mean Reversion    │   │ ├─ Mean Reversion    │    │
│  │ ├─ Vol Squeeze       │   │ ├─ Vol Squeeze       │    │
│  │ └─ Event Driven      │   │ └─ Event Driven      │    │
│  └──────────────────────┘   └──────────────────────┘    │
│                                                           │
│  COMPLETE ISOLATION ✅                                   │
│  ├─ Separate volumes (us-data vs india-data)            │
│  ├─ Separate brokers (Alpaca vs Simulator)              │
│  ├─ Separate data providers (US vs NSE)                 │
│  ├─ Separate market hours (ET vs IST)                   │
│  ├─ Separate ML models per scope                        │
│  └─ Independent scheduling + execution                   │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

## Next Steps

1. **Generate Mock Data**: Use `create_mock_data_for_testing()` for offline testing
2. **Train ML Models**: Run post-market ML training on India data
3. **Monitor Performance**: Track P&L, drawdown, win rate
4. **Scale Universe**: Expand from 80 to 300+ NSE stocks
5. **Add Real Data**: Connect to NSE data feeds for live historical data
6. **Documentation**: Add trade analysis and performance reporting

## References

- NSE Website: https://www.nseindia.com/
- NIFTY Index: https://www.nseindia.com/products/content/indices/index_info.htm
- Market Hours: https://www.nseindia.com/trade/aboutfaq.jsp
- Holiday Calendar: https://www.nseindia.com/trade/hol_calender.jsp

---

**Last Updated**: 2026-01-29  
**Status**: ✅ Running  
**Isolation**: ✅ Complete  
**Strategies**: ✅ All 5 swing strategies active  
**Data**: ✅ Mock + cached OHLCV ready
