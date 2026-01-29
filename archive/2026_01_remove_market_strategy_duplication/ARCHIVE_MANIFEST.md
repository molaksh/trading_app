# Archive: Market Strategy Duplication Removal

**Date:** January 28, 2026  
**Purpose:** Remove duplicated swing strategy files from market-specific directories  
**Status:** ✅ Complete

---

## Rationale

Swing strategies are **market-agnostic** — they contain no market-specific logic and should exist in a single canonical location. Having identical copies in `strategies/us/equity/swing/` and `strategies/india/equity/swing/` violated the DRY principle and created maintenance risk.

**Problem:**
- 14 identical files across 2 market directories
- High risk of drift if one copy was updated but not the others
- Confusing for developers: which location is the source of truth?

**Solution:**
- Move all strategy logic to `core/strategies/equity/swing/` (single source of truth)
- Market directories now contain only import shims that re-export from core
- No behavioral changes — same classes, same logic, same exports

---

## Archived Files

### US Strategy Files
Moved from `strategies/us/equity/swing/` to `archive/2026_01_remove_market_strategy_duplication/strategies/us/equity/swing/`:

```
swing_base.py                    (Abstract base + metadata)
swing_trend_pullback.py          (Philosophy: pullback)
swing_momentum_breakout.py       (Philosophy: momentum)
swing_mean_reversion.py          (Philosophy: mean reversion)
swing_volatility_squeeze.py      (Philosophy: volatility)
swing_event_driven.py            (Philosophy: events)
swing.py                         (Container/orchestrator)
```

### India Strategy Files
Moved from `strategies/india/equity/swing/` to `archive/2026_01_remove_market_strategy_duplication/strategies/india/equity/swing/`:

```
swing_base.py                    (Abstract base + metadata)
swing_trend_pullback.py          (Philosophy: pullback)
swing_momentum_breakout.py       (Philosophy: momentum)
swing_mean_reversion.py          (Philosophy: mean reversion)
swing_volatility_squeeze.py      (Philosophy: volatility)
swing_event_driven.py            (Philosophy: events)
swing.py                         (Container/orchestrator)
```

---

## New Canonical Location

All files now exist at: `core/strategies/equity/swing/`

```
core/strategies/equity/swing/
├── __init__.py                          (Re-exports all classes)
├── swing_base.py                        (Source of truth: abstract base)
├── swing_trend_pullback.py              (Source of truth: philosophy)
├── swing_momentum_breakout.py           (Source of truth: philosophy)
├── swing_mean_reversion.py              (Source of truth: philosophy)
├── swing_volatility_squeeze.py          (Source of truth: philosophy)
├── swing_event_driven.py                (Source of truth: philosophy)
└── swing_container.py                   (Source of truth: container)
```

---

## Import Shim Updates

**Market-specific directories now contain ONLY import shims:**

### `strategies/us/equity/swing/__init__.py`
```python
# Re-export canonical swing strategies from core
from core.strategies.equity.swing import SwingEquityStrategy, ...
```

### `strategies/india/equity/swing/__init__.py`
```python
# Re-export canonical swing strategies from core
from core.strategies.equity.swing import SwingEquityStrategy, ...
```

### `strategies/swing.py` (backward compat)
```python
# Re-export from canonical core location
from core.strategies.equity.swing import SwingEquityStrategy, ...
```

---

## Registry Updates

**`strategies/registry.py` now imports from core:**
```python
from core.strategies.equity.swing import SwingEquityStrategy
```

This ensures there is ONE source of truth for strategy discovery.

---

## Verification Checklist

- ✅ Duplicated files archived with path preservation
- ✅ Canonical location: `core/strategies/equity/swing/` (single source of truth)
- ✅ No .py strategy files remain in `strategies/us/equity/swing/` except `__init__.py`
- ✅ No .py strategy files remain in `strategies/india/equity/swing/` except `__init__.py`
- ✅ Import shims in market directories re-export from core
- ✅ StrategyRegistry imports from core location
- ✅ Backward compat: `strategies/swing.py` still works
- ✅ Behavior: ZERO changes to strategy logic or exports
- ✅ Docker container: Unaffected by refactoring

---

## Why This Prevents Future Drift

1. **Single Source:** Developers edit ONE location, not multiple copies
2. **Auto-consistency:** US and India markets **automatically** use identical strategy logic
3. **Market-agnostic:** Strategy core is isolated from market configuration
4. **Clear separation:** Strategy logic (core) vs. market policy (strategies/*/...)
5. **Auditable:** Archive preserves history of removed duplicates

---

## Future Enhancements

If new markets are added (e.g., crypto, futures):

**Old way (creates drift):**
```
strategies/crypto/equity/swing/     (copy 15 files here)
strategies/futures/equity/swing/    (copy 15 files here)
```

**New way (prevents drift):**
```
strategies/crypto/equity/swing/__init__.py    (1 line: from core.strategies...)
strategies/futures/equity/swing/__init__.py   (1 line: from core.strategies...)
```

Only one copy to maintain. No risk of divergence.

---

## References

- Canonical location: [core/strategies/equity/swing/](core/strategies/equity/swing/)
- Archive: [archive/2026_01_remove_market_strategy_duplication/](archive/2026_01_remove_market_strategy_duplication/)
- Import shims: [strategies/us/equity/swing/__init__.py](strategies/us/equity/swing/__init__.py)
