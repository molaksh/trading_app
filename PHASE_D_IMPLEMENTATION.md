# Phase D v0 & v1 Implementation

## Overview

Phase D is a **constitutional governance layer** that studies whether the BTC regime gate is potentially over-constraining based on evidence. It answers: "Is the BTC regime gate blocking too conservatively?" WITHOUT changing any trading behavior.

**Status**: ✅ Phase D v0 & v1 fully implemented

## What Phase D Does

### v0: Block Detection & Evidence Collection
- Detects when regime blocks start/end
- Collects post-facto metrics: upside missed, drawdowns, volatility
- Classifies blocks as: NOISE, COMPRESSION, SHOCK, or STRUCTURAL
- Persists all data append-only (JSONL format)

### v1: Eligibility Evaluation
- Evaluates 5-rule framework to compute PHASE_D_ELIGIBLE flag
- Rule 1: Evidence Sufficiency (≥3 completed blocks)
- Rule 2: Duration Anomaly (current > p90)
- Rule 3: Block Type (COMPRESSION or STRUCTURAL, not SHOCK)
- Rule 4: Cost-Benefit (missed upside > drawdown in ≥2 blocks)
- Rule 5: Regime Safety (no PANIC/SHOCK, vol normal)
- Auto-expires after 24h

## Architecture

### Directory Structure

```
phase_d/
├── __init__.py                    # Package exports
├── schemas.py                     # Pydantic models
├── persistence.py                 # Append-only JSONL storage
├── block_detector.py              # Detects block start/end
├── evidence_collector.py           # Post-facto metrics
├── block_classifier.py            # NOISE/COMPRESSION/SHOCK/STRUCTURAL
├── eligibility_checker.py         # 5-rule evaluation
└── phase_d_loop.py               # Main orchestration

config/
└── phase_d_settings.py            # Feature flags & thresholds

tests/test_phase_d/
├── __init__.py
└── test_phase_d_integration.py   # Integration tests (9 tests)

persist/phase_d/crypto/
├── blocks/block_events.jsonl      # Block lifecycle events
├── evidence/evidence_*.json       # Evidence per block
└── eligibility/eligibility_history.jsonl  # Eligibility evaluations
```

### Key Components

#### 1. BlockDetector (`phase_d/block_detector.py`)
```python
detector = BlockDetector()
block_start, block_end = detector.detect_blocks(scope)
```

**Responsibility**:
- Monitor `daily_summary.jsonl` for `regime_blocked_period` field
- Detect when blocks start (zero eligible strategies)
- Detect when blocks end (strategies become eligible again)
- Track active blocks per scope

**Data Source**: `logs/<scope>/logs/daily_summary.jsonl` field `regime_blocked_period`

#### 2. EvidenceCollector (`phase_d/evidence_collector.py`)
```python
evidence = collector.collect_evidence(completed_block)
```

**Responsibility**:
- Load price data using `crypto.data.crypto_price_loader`
- Compute metrics:
  - Missed upside: max price moves during block
  - Drawdown avoided: max drawdowns during block
  - Volatility expansion: vol before/after ratio
- Attach historical context from HistoricalAnalyzer

**Data Sources**:
- Price data: `crypto.data.crypto_price_loader.load_crypto_price_data_two_timeframes()`
- Historical stats: Historical daily summaries

#### 3. BlockClassifier (`phase_d/block_classifier.py`)
```python
block_type = classifier.classify_block(block, evidence)
```

**Classification Logic** (evaluated in order):
1. **SHOCK**: `vol_expansion >= 2.0 OR drawdown <= -10%`
2. **NOISE**: `duration < 1.5x median AND upside < 3%`
3. **COMPRESSION**: `duration >= p90 AND vol < 1.2x AND upside < 5%`
4. **STRUCTURAL**: Default (long, high upside)

#### 4. EligibilityChecker (`phase_d/eligibility_checker.py`)
```python
result = checker.check_eligibility(scope, current_block, block_history, evidence_map)
```

**Evaluation**:
- ALL 5 rules must pass for `eligible = True`
- Auto-expires 24h after evaluation
- Caches in `eligibility_history.jsonl`

#### 5. HistoricalAnalyzer (`phase_d/historical_analyzer.py`)
```python
stats = analyzer.get_regime_block_stats(scope, regime, lookback_days=30)
```

**Computes**:
- Median, p90, p10 block durations
- Min/max durations
- Count of blocks in lookback period

#### 6. PhaseDPersistence (`phase_d/persistence.py`)
```python
persistence = PhaseDPersistence()
persistence.write_block_event(event)
persistence.write_block_evidence(evidence)
persistence.write_eligibility_result(result)
```

**Append-Only Storage**:
- Block events: `persist/phase_d/crypto/blocks/block_events.jsonl`
- Evidence: `persist/phase_d/crypto/evidence/evidence_<block_id>.json`
- Eligibility: `persist/phase_d/crypto/eligibility/eligibility_history.jsonl`
- Events: `persist/phase_d/crypto/events/phase_d_events.jsonl`

#### 7. PhaseDLoop (`phase_d/phase_d_loop.py`)
```python
loop = PhaseDLoop(scopes=["live_kraken_crypto_global", "paper_kraken_crypto_global"])
loop.tick()  # Run once per iteration
```

**Orchestration**:
- Calls `detect_blocks()` for each scope
- Handles block start/end events
- Collects evidence for completed blocks
- Classifies blocks
- Evaluates eligibility (v1)

## Integration Points

### 1. Trading Runtime (`runtime/observability.py`)
Added regime block tracking:
```python
# ObservabilityCounters: regime_block_active, regime_block_start_ts, regime_block_regime
# Method: on_strategies_selected(eligible_strategies, regime)
# Daily summary field: regime_blocked_period
```

### 2. Crypto Pipeline (`crypto/pipeline/crypto_pipeline.py`)
Added observability hook after strategy selection:
```python
eligible = selector.get_eligible_strategies(regime_signal.regime)
get_observability().on_strategies_selected([e.value for e in eligible], regime_signal.regime.value)
```

### 3. Ops Agent (`ops_agent/response_generator.py`)
Added Phase D context to "no trades" explanations:
```python
response = self._add_phase_d_context(response, scope)
```

Shows eligibility status and expiry in Telegram responses.

## Feature Flags

All in `config/phase_d_settings.py`:

```bash
# Enable Phase D v0 (block detection + evidence)
export PHASE_D_V0_ENABLED=true

# Enable Phase D v1 (eligibility computation)
export PHASE_D_V1_ENABLED=true

# Global kill-switch (overrides all)
export PHASE_D_KILL_SWITCH=false
```

**Defaults**: All FALSE (opt-in, backward compatible)

## Configuration

### Block Classification Thresholds
```python
NOISE_DURATION_MULTIPLIER = 1.5      # < 1.5x median
NOISE_MAX_UPSIDE_PCT = 3.0           # < 3% upside
COMPRESSION_VOL_EXPANSION_MAX = 1.2  # < 1.2x vol ratio
COMPRESSION_MAX_UPSIDE_PCT = 5.0     # < 5% upside
SHOCK_VOL_EXPANSION_MIN = 2.0        # >= 2.0x vol ratio
SHOCK_MAX_DRAWDOWN_PCT = 10.0        # <= -10% drawdown
```

### Eligibility Configuration
```python
ELIGIBILITY_MIN_BLOCKS = 3                # >= 3 completed blocks
ELIGIBILITY_MIN_POSITIVE_CB = 2           # >= 2 blocks with positive CB
ELIGIBILITY_EXPIRY_HOURS = 24             # Auto-reset every 24h
```

### Evidence Configuration
```python
EVIDENCE_CORE_SYMBOLS = ["BTC", "ETH", "SOL"]
REGIME_BLOCK_MIN_DURATION_SECONDS = 60     # Report blocks > 1 min
```

## Usage

### Enable Phase D v0 (Recommended First Step)

```bash
export PHASE_D_V0_ENABLED=true
export PHASE_D_V1_ENABLED=false

# Run ops agent (integrates Phase D)
./run_ops_agent.sh

# Verify:
tail -f persist/phase_d/crypto/blocks/block_events.jsonl
```

### Enable Phase D v1 (After v0 Validation)

```bash
export PHASE_D_V1_ENABLED=true

# Run ops agent
./run_ops_agent.sh

# Test Phase E integration:
# Send Telegram: "Why no trades?"
# Response will include Phase D eligibility info
```

### Query Phase D Data

```python
from phase_d.persistence import PhaseDPersistence

persistence = PhaseDPersistence()

# Get latest eligibility
eligibility = persistence.read_latest_eligibility("live_kraken_crypto_global")
print(f"Eligible: {eligibility.eligible}")
print(f"Rule details: {eligibility.rule_details}")

# Get block events
blocks = persistence.read_block_events("live_kraken_crypto_global")
for block in blocks:
    print(f"Block {block.block_id}: {block.duration_seconds}s")

# Get evidence
evidence = persistence.read_block_evidence(block.block_id)
print(f"Upside: {evidence.btc_max_upside_pct:.2f}%")
```

## Testing

All tests pass ✅

```bash
# Run all Phase D tests
python -m pytest tests/test_phase_d/ -v

# Run specific test
python -m pytest tests/test_phase_d/test_phase_d_integration.py::TestBlockClassification::test_shock_classification -v
```

**Test Coverage**:
- Block detection logic
- Block type classification (SHOCK, NOISE, COMPRESSION, STRUCTURAL)
- Eligibility evaluation (all 5 rules)
- Persistence (append-only JSONL)
- Expiry auto-reset
- Integration end-to-end

## Safety Guarantees

✅ **Hard Constraints** (verified by implementation):

1. **READ-ONLY**: Never trades, never modifies trading state
2. **ZERO EXECUTION IMPACT**: All analysis post-facto or on separate tick
3. **FAIL-SAFE**: If Phase D crashes → trading continues unchanged
4. **FEATURE-FLAGGED**: Default FALSE, opt-in
5. **KILL-SWITCH**: `PHASE_D_KILL_SWITCH=true` disables all logic
6. **AUTO-EXPIRY**: Eligibility expires after 24h
7. **APPEND-ONLY**: All persistence immutable JSONL/JSON
8. **ISOLATED**: Runs in ops_agent, not trading pipeline
9. **BOUNDED**: All calculations deterministic, no infinite loops
10. **CONSTITUTIONAL**: Studies law, never amends it

## Design Decisions

### Why Regime Block Tracking in Observability?

✅ **Chosen**: Track `regime_blocked_period` in `daily_summary.jsonl`

**Benefits**:
- Explicit, auditable tracking
- No log parsing required
- One source of truth
- Phase D v0 just reads field

### Why Reuse crypto_price_loader?

✅ **Chosen**: `crypto.data.crypto_price_loader.load_crypto_price_data_two_timeframes()`

**Benefits**:
- Consistent with trading pipeline
- Same data source, same behavior
- No code duplication
- Graceful failure handling

### Why Feature-Flagged v1?

✅ **Chosen**: Deploy v0 first, enable v1 later

**Benefits**:
- Validate block detection for 1-2 weeks
- Catch data quality issues early
- v1 depends on v0 data being good
- Lower risk rollout

### Why 5-Rule Framework?

✅ **Chosen**: Simple, interpretable rules

**Benefits**:
- No black-box ML
- Easy to debug
- Rules align with trading logic
- Human-understandable

## Files Created

### Core Implementation (9 files)
1. `config/phase_d_settings.py` - Feature flags & thresholds
2. `phase_d/__init__.py` - Package exports
3. `phase_d/schemas.py` - Pydantic models (6 classes)
4. `phase_d/persistence.py` - Append-only storage
5. `phase_d/block_detector.py` - Block detection
6. `phase_d/evidence_collector.py` - Post-facto metrics
7. `phase_d/block_classifier.py` - Classification logic
8. `phase_d/eligibility_checker.py` - 5-rule evaluation
9. `phase_d/historical_analyzer.py` - Statistics computation
10. `phase_d/phase_d_loop.py` - Main orchestration

### Tests (2 files)
1. `tests/test_phase_d/__init__.py`
2. `tests/test_phase_d/test_phase_d_integration.py` - 9 integration tests

### Documentation (1 file)
1. `PHASE_D_IMPLEMENTATION.md` - This file

## Files Modified

1. `config/phase_d_settings.py` - NEW: Feature flags
2. `runtime/observability.py` - Added regime block tracking
3. `crypto/pipeline/crypto_pipeline.py` - Added observability hook
4. `ops_agent/response_generator.py` - Added Phase D context

## Next Steps (Post-Implementation)

### Week 1: Deploy v0
```bash
export PHASE_D_V0_ENABLED=true
export PHASE_D_V1_ENABLED=false
```
- Monitor block detection accuracy
- Verify evidence collection
- Check persistence

### Week 2: Validate v0 Data
- Review 5+ blocks detected
- Verify upside/drawdown metrics
- Check classification accuracy
- Confirm zero execution impact

### Week 3: Enable v1
```bash
export PHASE_D_V1_ENABLED=true
```
- Test eligibility computation
- Verify 24h auto-expiry
- Check Phase E integration
- Validate Telegram messages

### Future: Operational Dashboard
- Query Phase D data
- Visualize block timeline
- Track eligibility changes
- Historical analysis

## Troubleshooting

### "regime_blocked_period not found in daily_summary"
- Verify `runtime/observability.py` hook is called
- Check crypto_pipeline calls `on_strategies_selected()`
- Ensure daily summary is being written

### "No blocks detected"
- Check if strategy selection returns zero eligible
- Verify block duration > 60 seconds
- Ensure `PHASE_D_V0_ENABLED=true`

### "Eligibility always False"
- Verify at least 3 completed blocks exist
- Check block types (need COMPRESSION or STRUCTURAL)
- Verify current block duration > p90
- Ensure regime is not PANIC/SHOCK

## References

- **Phase C**: Constitutional AI Governance (governance_settings.py)
- **Phase E**: Ops Agent & Temporal Awareness (ops_settings.py)
- **Phase D**: Regime Gate Analysis (this document)

---

**Implementation Date**: 2026-02-09
**Status**: Complete ✅
**Tests**: 9/9 passing ✅
**Code Review**: Ready
