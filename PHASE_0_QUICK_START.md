# PHASE 0 QUICK REFERENCE

## Start Trading (5 minutes)

```bash
# 1. Set environment (1 min)
export SCOPE=paper_alpaca_swing_us
export BASE_DIR=/tmp/trading_app

# 2. Verify setup (1 min)
python verify_phase0.py
# Expected: ✓ ALL CHECKS PASSED (10/10)

# 3. Start trading (3 min)
python -m execution.scheduler
# Logs: $BASE_DIR/$SCOPE/logs/
# Trades: $BASE_DIR/$SCOPE/data/
# Models: $BASE_DIR/$SCOPE/models/
```

## Key Concepts (Reference)

### SCOPE Format
```
<env>_<broker>_<mode>_<market>

Examples:
- paper_alpaca_swing_us      ← Paper trading, Alpaca, swing, US
- live_ibkr_daytrade_us      ← Live trading, IBKR, day trading, US
- paper_zerodha_options_india ← Paper trading, Zerodha, options, India
- paper_crypto_crypto_global  ← Paper trading, Crypto, crypto, Global

Valid values:
- env: paper, live
- broker: alpaca, ibkr, zerodha, crypto
- mode: swing, daytrade, options, crypto
- market: us, india, global
```

### Storage Layout
```
BASE_DIR/
└── <scope>/
    ├── logs/
    │   ├── execution_log.jsonl
    │   └── errors.jsonl
    ├── models/
    │   ├── v1/, v2/, ...
    ├── state/
    │   ├── ml_state.json
    │   └── scheduler_state.json
    ├── features/
    ├── labels/
    └── data/
        └── trade_ledger.json
```

## API Quick Reference

### Get Current SCOPE
```python
from config.scope import get_scope
scope = get_scope()
print(f"Trading scope: {scope}")  # paper_alpaca_swing_us
```

### Get Path Resolver
```python
from config.scope_paths import get_scope_paths
from config.scope import get_scope

paths = get_scope_paths(get_scope())
logs_dir = paths.get_logs_dir()
models_dir = paths.get_models_dir()
```

### Get Broker for SCOPE
```python
from broker.broker_factory import get_broker_adapter
from config.scope import get_scope

broker = get_broker_adapter(get_scope())
# Returns: AlpacaAdapter, IBKRAdapter, ZerodhaAdapter, or CryptoAdapter
```

### Get Strategies for SCOPE
```python
from strategies.registry import instantiate_strategies_for_scope
from config.scope import get_scope

strategies = instantiate_strategies_for_scope(get_scope())
# Returns: List of Strategy objects matching scope's market+mode
```

### Check ML Training Status
```python
from ml.ml_state import MLStateManager

manager = MLStateManager()
active_version = manager.get_active_model_version()
print(f"Active model: {active_version}")

# Check if training needed
should_train = manager.should_train(current_fingerprint)
```

### Validate Configuration
```python
from startup.validator import validate_startup

try:
    validate_startup()
    print("✓ Configuration valid")
except Exception as e:
    print(f"✗ Configuration invalid: {e}")
```

## Common Workflows

### Add a New Strategy
```python
# 1. Create strategies/my_strategy.py
from strategies.base import Strategy, StrategyMetadata

class MyStrategy(Strategy):
    def __init__(self):
        super().__init__(name="my_strategy")
    
    def get_metadata(self):
        return StrategyMetadata(
            name="my_strategy",
            version="1.0",
            supported_markets=["us"],
            supported_modes=["swing"],
            instrument_type="equity"
        )
    
    def get_signals(self, data):
        # Your strategy logic
        return []

# 2. Restart scheduler
# Registry will auto-discover on next startup

# 3. Verify
strategies = instantiate_strategies_for_scope(get_scope())
assert any(s.name == "my_strategy" for s in strategies)
```

### Run Multiple Scopes (Same BASE_DIR)
```bash
# Terminal 1: Paper Alpaca
SCOPE=paper_alpaca_swing_us BASE_DIR=/shared/data python -m execution.scheduler &

# Terminal 2: Paper Zerodha (same BASE_DIR)
SCOPE=paper_zerodha_options_india BASE_DIR=/shared/data python -m execution.scheduler &

# Each has isolated:
# /shared/data/paper_alpaca_swing_us/
# /shared/data/paper_zerodha_options_india/
```

### Check Trade Performance
```bash
# View all trades
cat $BASE_DIR/$SCOPE/data/trade_ledger.json | jq .

# Filter by symbol
jq '.[] | select(.symbol=="TSLA")' $BASE_DIR/$SCOPE/data/trade_ledger.json

# Summary stats
jq '[.[] | .net_pnl_pct] | {min: min, max: max, avg: (add/length)}' \
   $BASE_DIR/$SCOPE/data/trade_ledger.json
```

### Check ML Training Status
```bash
# View state
cat $BASE_DIR/$SCOPE/state/ml_state.json | jq .

# Check active model
jq .active_model_version $BASE_DIR/$SCOPE/state/ml_state.json

# Check fingerprint (used for idempotency)
jq .last_dataset_fingerprint $BASE_DIR/$SCOPE/state/ml_state.json
```

## Troubleshooting

### Issue: "SCOPE invalid"
**Solution**: Check SCOPE format
```bash
# ✗ Wrong
export SCOPE=alpaca_paper_us

# ✓ Correct
export SCOPE=paper_alpaca_swing_us
```

### Issue: "Storage paths not accessible"
**Solution**: Create BASE_DIR
```bash
mkdir -p $BASE_DIR
chmod 755 $BASE_DIR
```

### Issue: "No strategies available for scope"
**Solution**: Check strategy metadata matches scope
```bash
# SwingEquityStrategy only supports:
# - market: us
# - mode: swing

# ✓ Correct
export SCOPE=paper_alpaca_swing_us

# ✗ Wrong (no matching strategy)
export SCOPE=paper_alpaca_daytrade_us
```

### Issue: Validation fails
**Solution**: Run diagnostic
```bash
python -c "from startup.validator import validate_startup; validate_startup()" 2>&1 | head -50
```

## Files to Know

| File | Purpose | When to Edit |
|------|---------|--------------|
| `config/scope.py` | SCOPE definition | Add new env/broker/mode/market combo |
| `config/scope_paths.py` | Path resolution | Change storage structure |
| `broker/broker_factory.py` | Broker selection | Add new broker type |
| `strategies/registry.py` | Strategy loading | Change discovery logic |
| `ml/ml_state.py` | ML state persistence | Change training tracking |
| `startup/validator.py` | Startup checks | Add validation rules |

## Documentation Map

```
PHASE_0_QUICK_START.md (you are here)
    ↓
PHASE_0_README.md (detailed guide)
    ↓
PHASE_0_INDEX.md (navigation)
    ↓
Source code (docstrings)
```

## Verification Commands

```bash
# Check Phase 0 is installed
python verify_phase0.py
# Expected: 10 checks passed

# List all Phase 0 files
python audit_phase0.py
# Expected: All files present

# Test SCOPE parsing
python -c "from config.scope import Scope; print(Scope.from_string('paper_alpaca_swing_us'))"

# Test path resolution
SCOPE=paper_alpaca_swing_us BASE_DIR=/tmp/test python -c \
  "from config.scope_paths import get_scope_paths; from config.scope import get_scope; \
   print(get_scope_paths(get_scope()).get_scope_summary())"

# Test startup validation
python -c "from startup.validator import validate_startup; validate_startup()"
```

## Environment Checklist

Before running `python -m execution.scheduler`:

```
☐ SCOPE set: export SCOPE=paper_alpaca_swing_us
☐ BASE_DIR set: export BASE_DIR=/data/trading_app
☐ BASE_DIR exists: ls -la $BASE_DIR
☐ BASE_DIR writable: touch $BASE_DIR/.test && rm $BASE_DIR/.test
☐ ALPACA_API_KEY set: echo $ALPACA_API_KEY (should be non-empty)
☐ ALPACA_BASE_URL set: echo $ALPACA_BASE_URL (should be non-empty)
☐ MARKET_TIMEZONE set: echo $MARKET_TIMEZONE (should be America/New_York or similar)
☐ RUN_PAPER_TRADING=true: echo $RUN_PAPER_TRADING
☐ Verify setup: python verify_phase0.py (10/10 passed)
☐ Ready to trade!
```

## Performance Notes

- **Startup time**: ~5 seconds (validation + loading strategies)
- **Per-tick overhead**: ~1ms (scope lookup + path resolution)
- **ML training**: ~1-2 minutes (once daily, depends on trade count)
- **Memory usage**: +10KB (Phase 0 components)
- **Disk usage**: ~1-2MB per scope (logs, state, models)

## Next Steps

### Phase 0.1 (Coming soon)
- Per-scope risk configuration
- Scope-specific leverage limits
- Scope-specific position size limits

### Phase 1 (Development)
- Complete IBKRAdapter
- Complete ZerodhaAdapter
- Complete CryptoAdapter
- Test with multiple brokers

### Phase 2 (Planning)
- Multi-scope orchestration
- Coordinated entries across scopes
- Shared BASE_DIR optimization

### Phase 3 (Future)
- ML model ensembles
- Continuous retraining
- Advanced strategies

## Support

1. **Quick issue?** → Check [Troubleshooting](#troubleshooting)
2. **How to use?** → Read [PHASE_0_README.md](./PHASE_0_README.md)
3. **API details?** → See [PHASE_0_INDEX.md](./PHASE_0_INDEX.md)
4. **Technical?** → Check source docstrings
5. **Still stuck?** → See [PHASE_0_INTEGRATION.md](./PHASE_0_INTEGRATION.md)

---

**Quick Start**: `export SCOPE=paper_alpaca_swing_us && export BASE_DIR=/tmp/trading && python verify_phase0.py && python -m execution.scheduler`

**Time**: 5 minutes to start trading ⏱️
