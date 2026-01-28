# PHASE 0: SCOPE-DRIVEN ARCHITECTURE

## Overview

Phase 0 completes the foundational architecture for the trading system, introducing the **SCOPE** concept as first-class, enabling:

- **Multi-scope trading**: Different strategies, brokers, modes per scope
- **Persistent storage isolation**: All data/logs/models under `BASE_DIR/<scope>/`
- **Broker modularity**: Plug-and-play via BrokerFactory (Alpaca/IBKR/Zerodha/Crypto)
- **Strategy isolation**: Scope-aware discovery and instantiation
- **ML idempotency**: Fingerprinting prevents redundant training
- **Container isolation**: Multiple containers from same codebase via config only

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TRADING CONTAINER                         │
│  (Configured by: SCOPE, BASE_DIR env vars)                  │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  [STARTUP VALIDATION]                                        │
│  └─ Fails fast if config invalid (scope, paths, broker)     │
│                                                               │
│  [SCOPE SYSTEM] ← paper_alpaca_swing_us, live_ibkr_...      │
│  ├─ Immutable dataclass: env/broker/mode/market             │
│  ├─ Validated against ALLOWED_SCOPES                        │
│  └─ Available via: get_scope()                              │
│                                                               │
│  [BROKER FACTORY] ← Selects adapter from scope.broker       │
│  ├─ AlpacaAdapter (existing)                                │
│  ├─ IBKRAdapter (Phase 1)                                   │
│  ├─ ZerodhaAdapter (Phase 1)                                │
│  └─ CryptoAdapter (Phase 1)                                 │
│                                                               │
│  [STRATEGY REGISTRY] ← Loads strategies for scope            │
│  ├─ Discovery: Scans for Strategy subclasses                │
│  ├─ Filtering: By scope.market + scope.mode                 │
│  ├─ Metadata: StrategyMetadata declares support             │
│  └─ Instantiation: get_strategies_for_scope(scope)          │
│                                                               │
│  [ML STATE MANAGER] ← Persistent training state              │
│  ├─ File: BASE_DIR/<scope>/state/ml_state.json              │
│  ├─ Fingerprinting: SHA256 of trade data                    │
│  ├─ Idempotency: should_train() skips unchanged data        │
│  └─ Promotion: Atomic model version updates                 │
│                                                               │
│  [SCOPE PATH RESOLVER] ← All paths under BASE_DIR/<scope>/  │
│  ├─ logs/ → Execution logs, errors                          │
│  ├─ models/ → Trained ML models, versions                   │
│  ├─ state/ → ml_state.json, scheduler state                 │
│  ├─ features/ → ML training features                        │
│  ├─ labels/ → ML training labels                            │
│  └─ data/ → Trade ledger, raw data                          │
│                                                               │
│  [EXECUTION PIPELINE] (unchanged)                            │
│  ├─ Strategy → Intent                                        │
│  ├─ Guard → Risk checks                                      │
│  ├─ Risk Manager → Portfolio limits                          │
│  ├─ Broker → Order execution                                │
│  ├─ Executor → Fill polling                                 │
│  └─ Ledger → Trade recording                                │
│                                                               │
│  [SCHEDULER] ← Orchestrates all activities                   │
│  ├─ Entry: Near market close                                │
│  ├─ Exits: Swing exits + emergency stops                    │
│  ├─ ML Training: Once daily, idempotent                     │
│  └─ Reconciliation: Hourly account checks                   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│            PERSISTENT STORAGE (outside container)            │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  BASE_DIR/                                                   │
│  ├── paper_alpaca_swing_us/                                 │
│  │   ├── logs/                                              │
│  │   │   ├── execution_log.jsonl                            │
│  │   │   └── errors.jsonl                                   │
│  │   ├── models/                                            │
│  │   │   ├── v1/                                            │
│  │   │   │   ├── model.pkl                                  │
│  │   │   │   └── scaler.pkl                                 │
│  │   │   └── v2/                                            │
│  │   ├── state/                                             │
│  │   │   ├── ml_state.json                                  │
│  │   │   └── scheduler_state.json                           │
│  │   ├── features/                                          │
│  │   │   ├── train_features.pkl                             │
│  │   │   └── test_features.pkl                              │
│  │   ├── labels/                                            │
│  │   │   ├── train_labels.pkl                               │
│  │   │   └── test_labels.pkl                                │
│  │   └── data/                                              │
│  │       └── trade_ledger.json                              │
│  │                                                           │
│  ├── live_ibkr_daytrade_us/                                 │
│  │   ├── logs/                                              │
│  │   ├── models/                                            │
│  │   ├── state/                                             │
│  │   ├── features/                                          │
│  │   ├── labels/                                            │
│  │   └── data/                                              │
│  │                                                           │
│  └── paper_zerodha_options_india/                           │
│      ├── logs/                                              │
│      ├── models/                                            │
│      ├── state/                                             │
│      ├── features/                                          │
│      ├── labels/                                            │
│      └── data/                                              │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Key Files

### Core Abstractions (NEW)

| File | Purpose | Lines |
|------|---------|-------|
| `config/scope.py` | SCOPE definition, validation, parsing | 380 |
| `config/scope_paths.py` | Path resolver for persistent storage | 280 |
| `broker/broker_factory.py` | Broker selection factory | 55 |
| `strategies/registry.py` | Strategy discovery and filtering | 200 |
| `ml/ml_state.py` | Persistent ML state management | 250 |
| `startup/validator.py` | Comprehensive startup validation | 300+ |

### Integration (MODIFIED)

| File | Changes |
|------|---------|
| `execution/runtime.py` | Use BrokerFactory, StrategyRegistry, ScopePathResolver |
| `execution/scheduler.py` | Call validate_startup(), use MLStateManager |
| `broker/execution_logger.py` | Use ScopePathResolver for log paths |
| `broker/trade_ledger.py` | Use ScopePathResolver for ledger paths |
| `strategies/base.py` | Add get_metadata() abstract method |
| `strategies/swing.py` | Implement get_metadata() with scope info |

## Configuration

### Environment Variables

```bash
# SCOPE Configuration (required)
export SCOPE=paper_alpaca_swing_us
# Format: <env>_<broker>_<mode>_<market>
# Valid env: paper, live
# Valid broker: alpaca, ibkr, zerodha, crypto
# Valid mode: swing, daytrade, options, crypto
# Valid market: us, india, global

# Storage (required)
export BASE_DIR=/data/trading_app
# All logs, models, state stored under BASE_DIR/<scope>/

# Existing (unchanged)
export MARKET_TIMEZONE=America/New_York
export ALPACA_API_KEY=...
export ALPACA_BASE_URL=...
export RUN_PAPER_TRADING=true
```

### Valid SCOPES

```python
ALLOWED_SCOPES = [
    # Paper trading (for development/testing)
    ("paper", "alpaca", "swing", "us"),
    ("paper", "alpaca", "daytrade", "us"),
    ("paper", "zerodha", "swing", "india"),
    ("paper", "zerodha", "options", "india"),
    ("paper", "ibkr", "daytrade", "us"),
    ("paper", "crypto", "crypto", "global"),
    
    # Live trading (careful!)
    ("live", "alpaca", "swing", "us"),
    ("live", "ibkr", "daytrade", "us"),
    ("live", "zerodha", "options", "india"),
    ("live", "crypto", "crypto", "global"),
]
```

## Usage

### Running with Phase 0

```bash
# 1. Set environment
export SCOPE=paper_alpaca_swing_us
export BASE_DIR=/tmp/trading_app_data
export ALPACA_API_KEY=...
export ALPACA_BASE_URL=...

# 2. Run scheduler (handles validation + all trading)
python -m execution.scheduler

# 3. Check logs
cat /tmp/trading_app_data/paper_alpaca_swing_us/logs/execution_log.jsonl

# 4. View trades
cat /tmp/trading_app_data/paper_alpaca_swing_us/data/trade_ledger.json | jq .
```

### Multi-Scope Containers

```bash
# Container 1: Paper trading with Alpaca
SCOPE=paper_alpaca_swing_us BASE_DIR=/shared/data python -m execution.scheduler &

# Container 2: Paper trading with Zerodha (different scope, same BASE_DIR)
SCOPE=paper_zerodha_options_india BASE_DIR=/shared/data python -m execution.scheduler &

# Container 3: Live trading with IBKR (separate SCOPE, same BASE_DIR)
SCOPE=live_ibkr_daytrade_us BASE_DIR=/shared/data python -m execution.scheduler &

# All three run in parallel with isolated logs, models, state
ls /shared/data/
# → paper_alpaca_swing_us/
# → paper_zerodha_options_india/
# → live_ibkr_daytrade_us/
```

## Data Flow

### Startup

```
1. Container environment: SCOPE, BASE_DIR
2. scheduler.__init__()
   a. validate_startup()
      - Check SCOPE valid
      - Check BASE_DIR writable
      - Check broker selectable
      - Check strategies available
      - FAIL FAST if any check fails
   b. build_paper_trading_runtime()
      - get_scope() → Scope instance
      - get_scope_paths(scope) → ScopePathResolver
      - get_broker_adapter(scope) → BrokerAdapter
      - instantiate_strategies_for_scope(scope) → [Strategy]
   c. reconcile_runtime() → sync with broker
   d. _load_ml_model() → load active model (do NOT train)
3. Enter main tick loop
```

### Trading Loop

```
Every SCHEDULER_TICK_SECONDS:
  1. Check market clock
  2. Emergency exits: Check for stop losses every 15 minutes
  3. Order polling: Check for fills every 5 minutes
  4. Entry signals: Check near market close
  5. Swing exits: Check after market close
  6. ML training: Once daily after close (idempotent)
```

### ML Training (Idempotent)

```
Each day after market close:
  1. Get all trades from trade_ledger
  2. Compute fingerprint = SHA256(symbol|prices|timestamps)
  3. Check: should_train(fingerprint)
     - False: Data unchanged → skip training
     - True: New data → proceed
  4. Build features/labels from trades
  5. Train model
  6. Save model version
  7. Update ml_state.json: fingerprint, run_id, promoted version
  8. Next day: Skip training if fingerprint unchanged
```

## Validation Checks

The startup validator checks 6 areas:

### 1. SCOPE Configuration
```
SCOPE={env}__{broker}_{mode}_{market}
- env: paper|live (validated)
- broker: alpaca|ibkr|zerodha|crypto (validated)
- mode: swing|daytrade|options|crypto (validated)
- market: us|india|global (validated)
- Combo: Must be in ALLOWED_SCOPES tuple
```

### 2. Storage Paths
```
BASE_DIR/<scope>/
├── logs/        ✓ Directory exists and writable
├── models/      ✓ Directory exists and writable
├── state/       ✓ Directory exists and writable
├── features/    ✓ Directory exists and writable
├── labels/      ✓ Directory exists and writable
└── data/        ✓ Directory exists and writable
```

### 3. Broker Adapter
```
BrokerFactory.get_broker_adapter(scope)
- Alpaca: ✓ AlpacaAdapter (existing implementation)
- IBKR: ✓ IBKRAdapter stub (NotImplementedError for Phase 1)
- Zerodha: ✓ ZerodhaAdapter stub
- Crypto: ✓ CryptoAdapter stub
```

### 4. Strategies
```
StrategyRegistry.get_strategies_for_scope(scope)
- Must have at least one strategy for scope
- Each strategy declares supported_markets + supported_modes
- SwingEquityStrategy: supported_markets=["us"], supported_modes=["swing"]
```

### 5. ML System
```
MLStateManager()
- state_dir exists
- ml_state.json loadable (or created)
- active_model_version available (optional)
```

### 6. Execution Pipeline
```
Check imports:
- TradingEngine exists
- TradeIntentGuard exists
- RiskManager exists
- All OK for execution
```

## Data Persistence

### ml_state.json

```json
{
  "last_trained_data_end_ts": "2024-01-15T16:00:00",
  "last_dataset_fingerprint": "abc123...",
  "last_run_id": "run_2024-01-15T16:00:00",
  "last_promoted_model_version": "v3",
  "active_model_version": "v3"
}
```

### trade_ledger.json

```json
[
  {
    "trade_id": "trade_xyz123",
    "symbol": "TSLA",
    "entry_price": 150.25,
    "exit_price": 155.50,
    "holding_days": 3,
    "exit_type": "SWING_EXIT",
    "exit_reason": "target reached",
    "net_pnl": 265.00,
    "net_pnl_pct": 3.46,
    ...
  }
]
```

## Testing

### Verification Script

```bash
# Run Phase 0 verification
python verify_phase0.py

# Expected output:
# ✓ SCOPE system (config/scope.py)
# ✓ ScopePathResolver (config/scope_paths.py)
# ✓ BrokerFactory (broker/broker_factory.py)
# ✓ Broker Adapters (ibkr, zerodha, crypto)
# ✓ StrategyRegistry (strategies/registry.py)
# ✓ ML State Manager (ml/ml_state.py)
# ✓ Startup Validator (startup/validator.py)
# ✓ Strategy Metadata (strategies/base.py updated)
# ✓ SwingEquityStrategy.get_metadata()
# ✓ Runtime assembly (execution/runtime.py)
# RESULTS: Checks passed: 10/10
```

### Manual Testing

```bash
# 1. Test SCOPE parsing
python -c "from config.scope import Scope; print(Scope.from_string('paper_alpaca_swing_us'))"

# 2. Test path resolution
export SCOPE=paper_alpaca_swing_us
export BASE_DIR=/tmp/test_trading
python -c "from config.scope_paths import get_scope_paths; from config.scope import get_scope; print(get_scope_paths(get_scope()).get_scope_summary())"

# 3. Test startup validation
python -c "from startup.validator import validate_startup; validate_startup()"
```

## Migration from Legacy

The system is backward compatible. Existing code continues to work:

| Old | New | Status |
|-----|-----|--------|
| `config.log_paths.LogPathResolver` | `config.scope_paths.ScopePathResolver` | Deprecated |
| Hardcoded `AlpacaAdapter` | `broker_factory.get_broker_adapter(scope)` | Replaced |
| Direct imports of strategies | `StrategyRegistry.instantiate_strategies_for_scope(scope)` | Recommended |
| No ML state tracking | `MLStateManager` for idempotency | New |
| No startup validation | `validate_startup()` | New |

## Troubleshooting

### "SCOPE invalid: ..."
```
Solution: Set SCOPE env var to valid format
export SCOPE=paper_alpaca_swing_us
```

### "Storage paths not accessible"
```
Solution: Create BASE_DIR and ensure writable
mkdir -p /data/trading_app
chmod 755 /data/trading_app
export BASE_DIR=/data/trading_app
```

### "No strategies available for scope"
```
Solution: Verify SwingEquityStrategy is installed and matches scope
- SwingEquityStrategy supports: market=us, mode=swing
- Use SCOPE=paper_alpaca_swing_us (or similar)
```

### "Broker adapter not found"
```
Solution: Ensure BrokerFactory can select adapter
- paper_alpaca uses AlpacaAdapter ✓
- paper_ibkr uses IBKRAdapter (stub, Phase 1)
- live_ibkr needs full IBKRAdapter implementation
```

## Next Phases

### Phase 0.1: Per-Scope Risk Limits
- Risk limits configured per scope
- Example: paper has lower leverage than live
- Requires: ScopeMetadata with risk config

### Phase 1: Adapter Implementations
- IBKRAdapter: Full Interactive Brokers integration
- ZerodhaAdapter: Full Zerodha integration
- CryptoAdapter: Full crypto exchange integration
- Currently: All raise NotImplementedError

### Phase 2: Multi-Scope Orchestration
- Multiple containers from same BASE_DIR
- Coordinated entry signals across scopes
- Requires: Orchestrator service

### Phase 3: ML Ensemble
- Multiple models per scope
- Ensemble voting for signals
- Continuous retraining

## Documentation

- [PHASE_0_INTEGRATION.md](./PHASE_0_INTEGRATION.md) - Detailed integration checklist
- [verify_phase0.py](./verify_phase0.py) - Verification script
- Individual module docstrings for API details

---

**Phase 0 Status**: ✅ COMPLETE

All foundational abstractions in place:
- ✅ SCOPE: First-class, immutable, validated
- ✅ Storage: Scope-isolated via ScopePathResolver
- ✅ Brokers: Modular via BrokerFactory
- ✅ Strategies: Discoverable, filterable via registry
- ✅ ML: Idempotent via fingerprinting + MLStateManager
- ✅ Validation: Fail-fast startup checks
- ✅ Integration: All components wired together

Ready for Phase 1 (adapter implementations) or Phase 2 (multi-scope orchestration).
