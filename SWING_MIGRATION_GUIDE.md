# MIGRATION GUIDE: NEW SWING STRATEGY ARCHITECTURE

## For Developers

### Quick Orientation

**Old Mental Model:**
```
SwingEquityStrategy = One trading philosophy
```

**New Mental Model:**
```
SwingEquityStrategy = Container that loads 5 philosophies
- SwingTrendPullbackStrategy
- SwingMomentumBreakoutStrategy
- SwingMeanReversionStrategy
- SwingVolatilitySqueezeStrategy
- SwingEventDrivenStrategy
```

### What Changed?

**Nothing you need to do immediately.** Existing code works unchanged.

```python
# This code still works exactly the same
strategy = SwingEquityStrategy()
intents = strategy.generate_entry_intents(market_data, portfolio_state)
```

But now you can access philosophy details:

```python
# NEW: See all philosophies loaded
for name in strategy.get_active_strategies():
    print(f"Active: {name}")

# NEW: See risk/caveat documentation
for philosophy in strategy.get_strategy_philosophies():
    print(f"{philosophy['name']}: {philosophy['philosophy']}")
    print(f"  Risks: {philosophy['risks']}")
    print(f"  Caveats: {philosophy['caveats']}")
```

### Entry Intent Metadata (NEW)

Entry intents now include philosophy details:

```python
intent.risk_metadata = {
    # Was already here
    "strategy_type": "swing",
    "hold_days_max": 20,
    
    # NEW: Philosophy metadata
    "strategy_id": "trend_pullback_v1",
    "strategy_philosophy": "Trade shallow pullbacks in strong uptrends",
    "strategy_edge": "Strong uptrends have higher continuation probability",
    "strategy_risks": [...],        # 4-5 documented risks
    "strategy_caveats": [...],      # 4-5 documented caveats
    "strategy_version": "1.0.0",
}
```

### Logs (NEW)

Logs now show which philosophy generated each intent:

```
INFO: Total entry intents: 3 from 5 strategies
INFO:   Entry from trend_pullback: AAPL - Trend pullback
INFO:   Entry from momentum_breakout: MSFT - Momentum breakout
INFO:   Entry from mean_reversion: TSLA - Mean reversion
```

---

## For ML/Monitoring

### New Data Available

Each intent now carries philosophy metadata. Use this for:

**1. Philosophy-based filtering:**
```python
# Only use trend-pullback signals
valid_intents = [
    i for i in intents
    if i.risk_metadata.get("strategy_id") == "trend_pullback_v1"
]
```

**2. Philosophy-aware confidence adjustment:**
```python
# Weight by strategy reliability
confidence_multipliers = {
    "trend_pullback_v1": 1.2,        # Trend pullback is reliable
    "event_driven_v1": 0.8,          # Event-driven is riskier
}

adjusted_confidence = intent.confidence * confidence_multipliers.get(
    intent.risk_metadata.get("strategy_id"),
    1.0
)
```

**3. Philosophy-specific risk sizing:**
```python
# Event-driven is riskier, size smaller
size_multiplier = {
    "trend_pullback_v1": 1.0,        # Full size
    "momentum_breakout_v1": 1.0,     # Full size
    "mean_reversion_v1": 0.8,        # 20% smaller (knife-catch risk)
    "volatility_squeeze_v1": 0.7,    # 30% smaller (directional risk)
    "event_driven_v1": 0.6,          # 40% smaller (tail risk)
}.get(intent.risk_metadata.get("strategy_id"), 1.0)
```

**4. Monitoring dashboard:**
```python
# Show which philosophies are currently generating intents
active_philosophies = Counter(
    intent.risk_metadata.get("strategy_id")
    for intent in intents
)
# Display: "Trend Pullback: 3, Momentum Breakout: 1, Mean Reversion: 2"
```

---

## For Risk Management

### New Risk Assessment

Each philosophy has documented risks and caveats.

**Example: Trend Pullback Risks**
```
"sideways_markets": "Stops hit frequently in choppy markets",
"late_stage_trends": "Reversal without warning in extended trends",
"gap_downs": "Overnight gaps can exceed 5% pullback threshold",
"false_breakouts": "Pullback trend can reverse after entry",
```

**Use for:**

1. **Confidence adjustment:**
   - Low ADX → Reduce trend pullback confidence
   - Post-earnings → Reduce volatility squeeze confidence

2. **Position sizing:**
   - Event-driven during earnings week → Half size
   - Mean reversion in downtrend → Half size

3. **Stop-loss placement:**
   - Trend pullback → Tight stop below SMA20
   - Event-driven → Loose stop, allow mean reversion

---

## For Configuration

### Disable Specific Philosophies

```python
container = SwingEquityStrategy(config={
    "enabled_strategies": [
        "trend_pullback",
        "momentum_breakout",
        # "mean_reversion",           # Disabled
        # "volatility_squeeze",       # Disabled
        # "event_driven",             # Disabled
    ],
})
```

### Override Philosophy Parameters

```python
container = SwingEquityStrategy(config={
    "enabled_strategies": [
        "trend_pullback",
        "momentum_breakout",
    ],
    "strategy_configs": {
        "trend_pullback": {
            "min_confidence": 5,       # Override default (4)
            "pullback_threshold": 0.03,  # 3% instead of 5%
            "profit_target_pct": 0.12,   # 12% instead of 10%
        },
        "momentum_breakout": {
            "max_positions": 5,        # Override global default (10)
        },
    },
})
```

### Scale Based on Market Conditions

```python
def get_container_for_market(market_regime):
    if market_regime == "strong_uptrend":
        return SwingEquityStrategy(config={
            "enabled_strategies": [
                "trend_pullback",      # Best in uptrends
                "momentum_breakout",   # Works too
            ],
            "max_positions": 10,
        })
    
    elif market_regime == "choppy":
        return SwingEquityStrategy(config={
            "enabled_strategies": [
                "mean_reversion",      # Works in ranges
                "volatility_squeeze",  # Compress/expand cycles
            ],
            "max_positions": 5,        # Fewer trades in chop
        })
    
    elif market_regime == "event_rich":
        return SwingEquityStrategy(config={
            "enabled_strategies": [
                "event_driven",        # Specific to events
                "mean_reversion",      # Follow-on reversion
            ],
            "max_positions": 3,        # Conservative, tail risk
        })
```

---

## File Organization

### Where to Find Each Philosophy

```
strategies/
├── swing.py                          ← SwingEquityStrategy container
├── swing_base.py                     ← BaseSwingStrategy abstract
├── swing_trend_pullback.py           ← Trend Pullback philosophy
├── swing_momentum_breakout.py        ← Momentum Breakout philosophy
├── swing_mean_reversion.py           ← Mean Reversion philosophy
├── swing_volatility_squeeze.py       ← Volatility Squeeze philosophy
└── swing_event_driven.py             ← Event-Driven philosophy
```

### Import Paths

```python
# Import container
from strategies.swing import SwingEquityStrategy

# Import base (for extending)
from strategies.swing_base import BaseSwingStrategy, SwingStrategyMetadata

# Import individual philosophies (rarely needed, container handles it)
from strategies.swing_trend_pullback import SwingTrendPullbackStrategy
from strategies.swing_momentum_breakout import SwingMomentumBreakoutStrategy
# ... etc
```

---

## Testing & Validation

### Test Container Loads Correctly

```python
def test_swing_container():
    strategy = SwingEquityStrategy()
    
    # Check all strategies loaded
    assert len(strategy.get_active_strategies()) == 5
    
    # Check metadata exists
    philosophies = strategy.get_strategy_philosophies()
    assert all("philosophy" in p for p in philosophies)
    assert all("risks" in p for p in philosophies)
    assert all("caveats" in p for p in philosophies)
    
    print("✅ Container loads correctly")
```

### Test Individual Philosophy

```python
def test_trend_pullback():
    strategy = SwingTrendPullbackStrategy()
    metadata = strategy.get_swing_metadata()
    
    assert metadata.strategy_id == "trend_pullback_v1"
    assert "uptrend" in metadata.philosophy.lower()
    assert len(metadata.risks) == 4
    assert len(metadata.caveats) == 5
    
    print("✅ Trend pullback philosophy valid")
```

### Test Entry Generation

```python
def test_entries():
    container = SwingEquityStrategy()
    
    market_data = {
        "signals": [
            {
                "symbol": "AAPL",
                "confidence": 4,
                "features": {
                    "sma20": 150,
                    "sma200": 145,
                    "pullback_pct": 0.03,
                    "volume_ratio": 1.5,
                    # ... more features
                }
            }
        ]
    }
    
    portfolio_state = {
        "positions": [],
    }
    
    intents = container.generate_entry_intents(market_data, portfolio_state)
    
    # Check intents have philosophy metadata
    assert all("strategy_id" in i.risk_metadata for i in intents)
    assert any("trend_pullback" in i.risk_metadata.get("strategy_id", "")
               for i in intents)
    
    print(f"✅ Generated {len(intents)} intents with philosophy metadata")
```

---

## Troubleshooting

### "No intents generated"

**Check:**
1. Are signals in market_data provided?
2. Is container configured with enabled_strategies?
3. Do signals meet each philosophy's entry criteria?

```python
container = SwingEquityStrategy()
philosophies = container.get_strategy_philosophies()
print(f"Enabled philosophies: {[p['name'] for p in philosophies]}")
```

### "Only one philosophy generating intents"

**This is normal.** Different philosophies have different entry criteria:
- Trend Pullback: Requires uptrend + pullback
- Momentum Breakout: Requires volume spike + RSI > 60
- Mean Reversion: Requires uptrend + oversold (RSI < 40)
- Volatility Squeeze: Requires compression + breakout
- Event-Driven: Requires post-event setup

**Solution:** Provide more diverse market data with different characteristics.

### "IntentMetadata missing philosophy fields"

**Check:** Intent came from individual strategy, not container.

```python
# ❌ Wrong - missing philosophy metadata
intent = SwingTrendPullbackStrategy().generate_entry_intents(...)

# ✅ Right - container adds metadata
intent = SwingEquityStrategy().generate_entry_intents(...)
```

---

## Documentation Changes

### Old Documentation (Still Valid)

All previous documentation about:
- 2-20 day hold periods
- Max 10 positions
- EOD evaluation
- NEXT_OPEN execution
- Risk management

**Still 100% valid and unchanged.**

### New Documentation (Read This)

- [SWING_ARCHITECTURE_REFACTOR.md](SWING_ARCHITECTURE_REFACTOR.md) - Complete architecture overview
- [This file] - Migration guide
- Individual strategy docstrings - Philosophy details

---

## Summary

### What You Need to Know

1. **No immediate changes needed** - Existing code works
2. **New metadata available** - Use philosophy details in logging, monitoring, risk adjustment
3. **Same 2-20 day hold** - Swing behavior completely unchanged
4. **5 independent philosophies** - Can enable/disable individually
5. **Market-agnostic** - Same strategies work for US, India, crypto

### What Changed

- SwingEquityStrategy is now a container
- Entry intents include philosophy metadata (risks, caveats, edge)
- Logs show which philosophy generated each intent
- Can selectively disable philosophies

### What Stayed the Same

- Entry/exit logic
- Hold periods (2-20 days)
- Position limits (max 10)
- Risk management
- Broker integration
- ML integration

---

## Questions?

Refer to:
- **Architecture Details:** [SWING_ARCHITECTURE_REFACTOR.md](SWING_ARCHITECTURE_REFACTOR.md)
- **Code Examples:** Individual strategy files (swing_*.py)
- **Philosophy Details:** SwingStrategyMetadata in each philosophy
- **API Docs:** Docstrings in BaseSwingStrategy and SwingEquityStrategy
