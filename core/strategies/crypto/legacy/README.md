# Legacy Wrapper Strategies (ARCHIVED)

These files contain deprecated wrapper strategies that have been replaced by the 6 canonical crypto strategies registered via `CryptoStrategyRegistry`.

## Why These Exist

During the Phase 0 implementation, wrapper strategies (`CryptoMomentumStrategy`, `CryptoTrendStrategy`) were used to organize the crypto strategy system. These have been refactored out and replaced with a direct registration of 6 first-class strategies.

## Migration Path

- ✅ **crypto_momentum.py**: Functionality now provided by `LongTermTrendFollower` and `VolatilityScaledSwing`
- ✅ **crypto_trend.py**: Functionality now provided by `LongTermTrendFollower`

## For Developers

Do NOT import these files from production code. They are kept here for historical reference only.

### Correct Import Path (Production)
```python
from core.strategies.crypto import CryptoStrategyRegistry
strategies = CryptoStrategyRegistry.get_all_strategies()
# Returns 6 canonical strategies
```

### Incorrect Import Path (DO NOT USE)
```python
# ❌ WRONG - These are archived
from core.strategies.crypto import CryptoMomentumStrategy
from core.strategies.crypto import CryptoTrendStrategy
```

## Cleanup Schedule

These files can be deleted after:
1. All Phase 1 integrations complete
2. Production containers have been running for 30 days
3. No historical backtesting references these wrappers
