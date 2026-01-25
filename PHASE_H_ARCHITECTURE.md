# Phase H: Monitoring & Drift Detection

## Overview

Phase H implements comprehensive monitoring and auto-protection mechanisms to detect when trading system performance degrades. The system monitors WITHOUT modifying trading signals, ensuring safety and reversibility.

**Key Principle**: Monitoring observes system health without mutating trading decisions. All protection is reversible.

## Architecture

### 4 Core Monitoring Components

#### 1. **ConfidenceDistributionMonitor**
Tracks the distribution of confidence scores over time.

**What it monitors:**
- Rolling window of confidence signals (1-5 scale)
- Daily distribution snapshots
- Percentage of signals at each confidence level

**Anomalies detected:**
- **Confidence Inflation**: >30% of signals at confidence level 5
  - Indicates signal quality may be degrading (too many high-confidence trades)
  - May suggest overfitting or market regime change
- **Confidence Collapse**: <10% of signals at confidence level 4-5
  - Indicates insufficient high-confidence signals
  - May suggest poor signal quality or market change

**Configuration**:
```python
ENABLE_CONFIDENCE_MONITORING = True
CONFIDENCE_INFLATION_THRESHOLD = 0.30      # Flag if >30% are confidence 5
CONFIDENCE_COLLAPSE_THRESHOLD = 0.10       # Flag if <10% are confidence 4-5
CONFIDENCE_MIN_WINDOW_SIZE = 20            # Minimum signals before checking
```

#### 2. **PerformanceMonitor**
Tracks win rates, returns, and drawdowns per confidence tier.

**What it monitors:**
- Trade results broken down by confidence level (1-5)
- Win rate per tier
- Average return per tier
- Maximum drawdown per tier

**Anomalies detected:**
- **Tier Degradation**: Win rate drops below 40% OR average return drops below -1%
  - Indicates that a specific confidence level is underperforming
  - May suggest that trades at this confidence level need investigation

**Configuration**:
```python
ENABLE_PERFORMANCE_MONITORING = True
PERFORMANCE_MIN_TIER_TRADES = 10           # Min trades per tier before checking
WIN_RATE_ALERT_THRESHOLD = 0.40            # Flag if win rate < 40%
AVG_RETURN_ALERT_THRESHOLD = -0.01         # Flag if avg return < -1%
```

#### 3. **FeatureDriftMonitor**
Detects when input feature distributions shift away from historical baseline.

**What it monitors:**
- Mean and standard deviation of each feature
- Compares recent window vs long-term baseline
- Z-score distance between recent and baseline distributions

**Anomalies detected:**
- **Feature Drift**: Recent mean deviates >3 std devs from baseline
  - Indicates market regime has shifted
  - May suggest features are no longer predictive
  - Suggests data distribution has changed significantly

**Configuration**:
```python
ENABLE_FEATURE_DRIFT_MONITORING = True
FEATURE_DRIFT_ZSCORE_THRESHOLD = 3.0       # Flag if z-score > 3.0
FEATURE_DRIFT_LOOKBACK_WINDOW = 60         # Recent window (days)
FEATURE_DRIFT_BASELINE_WINDOW = 250        # Long-term baseline (days)
```

#### 4. **SystemGuard**
Orchestrates all 3 monitors and implements auto-protection logic.

**Responsibilities:**
- Runs all monitors regularly
- Aggregates alerts across all monitors
- Tracks consecutive alerts
- Triggers reversible auto-protection when thresholds exceeded
- Logs all monitoring decisions

**Auto-Protection Response**:
When consecutive alerts exceed threshold (default: 3):
- Disables ML-based confidence sizing
- Reverts to neutral position sizing
- Logs protection trigger reason
- Can be manually disabled after investigation

**Configuration**:
```python
RUN_MONITORING = True                      # Enable all monitoring
ENABLE_AUTO_PROTECTION = True              # Enable auto-protection responses
MAX_CONSECUTIVE_ALERTS = 3                 # Trigger protection after N alerts
AUTO_PROTECTION_DISABLES_ML_SIZING = True  # Protection disables ML confidence scaling
AUTO_PROTECTION_REVERSIBLE = True          # Can re-enable after investigation
```

## Integration with Execution Pipeline

### Data Flow

```
Day N:
  1. Load price data, compute features
  2. Generate confidence scores (rules)
  3. Score signals with optional ML confidence sizing
  4. Execute trades
  
  → Add to ConfidenceDistributionMonitor
  → Add to FeatureDriftMonitor (features)
  
Day N+1:
  5. Get trade results from yesterday
  6. Calculate PnL by confidence level
  
  → Add to PerformanceMonitor
  
Day N+5 (or daily):
  7. Run degradation checks
  8. Update daily snapshots
  
  → SystemGuard.check_degradation()
  → If severe: SystemGuard.trigger_auto_protection()
  
Day N+10+ (after investigation):
  9. If issue resolved:
  
  → SystemGuard.disable_auto_protection("Issue resolved")
  → Resume normal ML confidence sizing
```

### Minimal Integration Changes

Add to trading loop:

```python
# Initialize monitoring
if config.RUN_MONITORING:
    guard = SystemGuard(
        use_ml_sizing=config.ENABLE_ML_SIZING,
        enable_confidence_monitoring=config.ENABLE_CONFIDENCE_MONITORING,
        enable_performance_monitoring=config.ENABLE_PERFORMANCE_MONITORING,
        enable_feature_drift_monitoring=config.ENABLE_FEATURE_DRIFT_MONITORING,
    )
    guard.initialize_feature_drift_monitor(feature_names)

# During backtest loop:
for date, symbol in backtest_dates_symbols:
    # Normal trading logic...
    confidence = score_symbol(features)
    
    # Monitor signal
    if config.RUN_MONITORING:
        guard.add_signal(confidence)
        guard.add_features(feature_dict, date)
    
    # Execute trade (possibly with protection disabled)
    sizing_multiplier = 1.0  # Neutral
    if config.ENABLE_ML_SIZING and not guard.protection_active:
        sizing_multiplier = get_ml_sizing_multiplier(confidence)
    
    position_size = base_risk * sizing_multiplier
    # ... execute trade ...
    
    # Monitor result (next day)
    if config.RUN_MONITORING:
        guard.add_trade(confidence, entry, exit, size)
        
    # Check degradation periodically
    if config.RUN_MONITORING and date.day_of_week == 4:  # Friday
        result = guard.check_degradation()
        if result['should_trigger_protection']:
            guard.trigger_auto_protection(result['reason'])
```

## Monitoring Metrics

### ConfidenceDistributionMonitor Output

```python
summary = monitor.get_summary()
# Returns:
{
    "anomalies_detected": 2,
    "daily_snapshots": [
        {"date": "2024-01-05", "distribution": {1: 0.1, 2: 0.2, 3: 0.3, 4: 0.2, 5: 0.2}},
        ...
    ]
}
```

### PerformanceMonitor Output

```python
summary = monitor.get_summary()
# Returns:
{
    "tiers": {
        1: {"count": 8, "win_rate": 0.375, "avg_return": -0.002},
        2: {"count": 15, "win_rate": 0.467, "avg_return": 0.001},
        3: {"count": 22, "win_rate": 0.545, "avg_return": 0.003},
        4: {"count": 18, "win_rate": 0.611, "avg_return": 0.005},
        5: {"count": 12, "win_rate": 0.667, "avg_return": 0.008},
    },
    "total_trades": 75
}
```

### FeatureDriftMonitor Output

```python
summary = monitor.get_summary()
# Returns:
{
    "drifts_detected": 0,
    "features_monitored": 8,
    "baseline_stats": {
        "momentum": {"mean": 0.524, "std": 0.087},
        ...
    },
    "recent_stats": {
        "momentum": {"mean": 0.531, "std": 0.092},
        ...
    }
}
```

### SystemGuard Output

```python
summary = guard.get_summary()
# Returns:
{
    "system_guard": {
        "protection_active": False,
        "ml_sizing_enabled": True,
        "consecutive_alerts": 0,
        "total_alerts": 3,
        "degradations_detected": 2,
        "protection_activations": 0
    },
    "protection": {
        "active": False,
        "triggered_at": None
    },
    "confidence_monitor": {...},
    "performance_monitor": {...},
    "feature_drift_monitor": {...}
}
```

## Auto-Protection Behavior

### Trigger Conditions

Protection activates when:
1. At least one monitor detects an anomaly
2. AND consecutive alerts exceed `MAX_CONSECUTIVE_ALERTS` (default: 3)
3. AND `ENABLE_AUTO_PROTECTION` is True

### What Protection Does

```python
guard.trigger_auto_protection(reason="Performance degradation in tiers 4-5")

# Results in:
- guard.protection_active = True
- guard.ml_sizing_enabled = False  # Disables confidence-based scaling
- All subsequent trades use neutral (1.0x) sizing multiplier
- Logs full degradation reason for investigation
```

### Reversibility

Protection is **fully reversible**:

```python
guard.disable_auto_protection(reason="Issue resolved - reverting to normal")

# Results in:
- guard.protection_active = False
- guard.ml_sizing_enabled = True  # Re-enables confidence-based scaling
- Consecutive alert counter resets
- Resumes normal trading with ML confidence sizing
```

## Configuration Reference

### Monitoring Enable/Disable

```python
# config/settings.py
RUN_MONITORING = True  # Master switch
ENABLE_CONFIDENCE_MONITORING = True
ENABLE_PERFORMANCE_MONITORING = True
ENABLE_FEATURE_DRIFT_MONITORING = True
ENABLE_AUTO_PROTECTION = True
```

### Confidence Monitoring Thresholds

```python
CONFIDENCE_INFLATION_THRESHOLD = 0.30   # Alert if >30% at confidence 5
CONFIDENCE_COLLAPSE_THRESHOLD = 0.10    # Alert if <10% at confidence 4-5
CONFIDENCE_MIN_WINDOW_SIZE = 20         # Need 20+ signals to check
```

### Performance Monitoring Thresholds

```python
PERFORMANCE_MIN_TIER_TRADES = 10        # Need 10+ trades per tier to check
WIN_RATE_ALERT_THRESHOLD = 0.40         # Alert if win rate < 40%
AVG_RETURN_ALERT_THRESHOLD = -0.01      # Alert if avg return < -1%
```

### Feature Drift Thresholds

```python
FEATURE_DRIFT_ZSCORE_THRESHOLD = 3.0    # Alert if z-score > 3.0 (rare event)
FEATURE_DRIFT_LOOKBACK_WINDOW = 60      # Recent 60-day window
FEATURE_DRIFT_BASELINE_WINDOW = 250     # Long-term 250-day baseline
```

### Auto-Protection Settings

```python
MAX_CONSECUTIVE_ALERTS = 3              # Trigger after 3 consecutive alerts
AUTO_PROTECTION_DISABLES_ML_SIZING = True
AUTO_PROTECTION_REVERSIBLE = True       # Can always be disabled manually
```

## Usage Examples

### Basic Monitoring Setup

```python
from monitoring import SystemGuard
from config.settings import (
    RUN_MONITORING,
    ENABLE_CONFIDENCE_MONITORING,
    ENABLE_PERFORMANCE_MONITORING,
    ENABLE_FEATURE_DRIFT_MONITORING,
)

# Initialize guard
guard = SystemGuard(
    use_ml_sizing=True,
    enable_confidence_monitoring=ENABLE_CONFIDENCE_MONITORING,
    enable_performance_monitoring=ENABLE_PERFORMANCE_MONITORING,
    enable_feature_drift_monitoring=ENABLE_FEATURE_DRIFT_MONITORING,
)

# Initialize feature drift with your feature names
guard.initialize_feature_drift_monitor([
    "sma_slope", "atr_pct", "vol_ratio", "pullback_depth"
])
```

### Adding Signals

```python
# As you generate confidence scores
confidence = score_symbol(features)
if RUN_MONITORING:
    guard.add_signal(confidence, signal_value)
```

### Adding Trade Results

```python
# At trade exit (next day)
pnl = exit_price - entry_price
if RUN_MONITORING:
    guard.add_trade(confidence, entry_price, exit_price, contract_count)
```

### Adding Features

```python
# As you compute features
if RUN_MONITORING:
    guard.add_features({
        "sma_slope": latest_row["sma20_slope"],
        "atr_pct": latest_row["atr_pct"],
        "vol_ratio": latest_row["vol_ratio"],
    }, date)
```

### Checking Degradation

```python
# Periodically (e.g., daily or weekly)
result = guard.check_degradation()

if result["has_degradation"]:
    logger.warning(f"Degradation detected: {result['degradation_events']}")
    
    if result["should_trigger_protection"]:
        guard.trigger_auto_protection("Degradation threshold exceeded")
```

### Getting Status

```python
# Anytime to check current state
status = guard.get_status()
print(f"Protection active: {status['protection_active']}")
print(f"ML sizing enabled: {status['ml_sizing_enabled']}")
print(f"Consecutive alerts: {status['consecutive_alerts']}")

# Get full summary
summary = guard.get_summary()
print(summary)  # Full monitoring report
```

## Design Principles

1. **Observe, Don't Mutate**: Monitoring tracks system health without changing trading signals
2. **Reversible**: All protection can be disabled if proven unnecessary
3. **Lightweight**: Minimal performance impact on backtests
4. **Deterministic**: Same inputs always produce same monitoring results
5. **Explainable**: Every alert includes clear reason and statistics
6. **Configurable**: All thresholds adjustable for different regimes
7. **Safe**: Defaults are conservative (better to over-protect than under-protect)

## Testing

See [test_monitoring.py](test_monitoring.py) for comprehensive test suite covering:
- All 4 monitor components
- Individual monitor functionality
- Integration between monitors
- Auto-protection triggering and reversibility
- Edge cases and error conditions

Run tests:
```bash
python -m pytest test_monitoring.py -v
```

## Next Steps

After Phase H deployment:
1. Monitor live trading for degradation events
2. Calibrate thresholds based on actual trading regime
3. Investigate each auto-protection trigger to understand causes
4. Document regime-specific threshold adjustments
5. Consider adaptive thresholds based on market volatility
