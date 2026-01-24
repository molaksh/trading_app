# ML-Ready Dataset Pipeline

## Overview

The trading system now includes a complete **leak-free, reproducible** dataset pipeline that prepares feature snapshots and labels for machine learning training. No models are trained yet—only data preparation.

## Key Components

### 1. Label Configuration (`config/settings.py`)

Added ML-specific parameters:

```python
LABEL_HORIZON_DAYS = 5           # Forward-looking window (5 trading days)
LABEL_TARGET_RETURN = 0.02       # +2% profit target
LABEL_MAX_DRAWDOWN = -0.01       # -1% max loss tolerance
DATASET_OUTPUT_DIR = "./data"    # Where to save datasets
DATASET_FILE_FORMAT = "parquet"  # CSV or Parquet format
```

**Label Definition:**
- **Label = 1** if price reaches `(entry_price × 1.02)` within 5 days WITHOUT falling below `(entry_price × 0.99)`
- **Label = 0** otherwise

### 2. Label Generator (`dataset/label_generator.py`)

**Purpose:** Computes binary labels for historical entry points.

**Key Functions:**
- `compute_label()` - Computes label for a single entry date
- `compute_labels_for_symbol()` - Batch label computation for a symbol

**No Lookahead Bias:**
- Labels use only forward-looking price data (after entry date)
- Cannot see past entry point when computing label

**Example:**
```python
label = compute_label(
    price_series=df['Close'],
    entry_date=pd.Timestamp('2025-09-22'),
    entry_price=100.0
)
# Returns 1 if price hits 102 within 5 days without touching 99 first
```

### 3. Feature Snapshots (`dataset/feature_snapshot.py`)

**Purpose:** Creates feature snapshots for each historical date—one row per (symbol, date) pair.

**Workflow for each snapshot:**
1. Extract all price data **up to and including** the date (no future data)
2. Compute technical features from historical window
3. Assign confidence score (1-5) based on rules
4. Compute label using forward-looking prices
5. Store as one row in the dataset

**Leak-Free Design:**
- Features computed using only data available on decision date
- Labels use only prices after decision date
- No circular dependencies

**Output Row:**
```
{
  'date': 2025-09-22,
  'symbol': 'AAPL',
  'close': 100.50,
  'sma_20': 99.80,
  'sma_200': 98.50,
  'dist_20sma': 0.007,       # Distance to 20-day SMA
  'dist_200sma': 0.020,      # Distance to 200-day SMA
  'sma20_slope': 0.002,      # Slope of 20-day SMA
  'atr_pct': 0.025,          # Volatility (ATR % of price)
  'vol_ratio': 1.15,         # Current volume / avg volume
  'pullback_depth': 0.03,    # % drop from 20-day high
  'confidence': 4,           # Rule-based score (1-5)
  'label': 1                 # Forward-looking label (0 or 1)
}
```

### 4. Dataset Builder (`dataset/dataset_builder.py`)

**Purpose:** Aggregates feature snapshots across all symbols and saves to disk.

**Key Class:** `DatasetBuilder`

**Workflow:**
```python
builder = DatasetBuilder(output_dir="./data", file_format="parquet")

# Build dataset
dataset = builder.build_dataset(symbols=['AAPL', 'MSFT', 'GOOGL'])

# OR build and save in one call
filepath = builder.build_and_save(symbols, lookback_days=252)
```

**Output Statistics:**
- Total rows: number of (symbol, date) snapshots
- Label distribution: count of 0s vs 1s
- Confidence distribution: count per confidence level
- Date range: earliest to latest snapshot date

**Deterministic Ordering:**
- Rows sorted by date, then symbol (reproducible)
- Same inputs always produce same dataset

### 5. Main Entry Point (`main.py`)

Added `BUILD_DATASET` flag:

```python
# Set to True to build dataset, False for regular screener
BUILD_DATASET = True  

if __name__ == '__main__':
    if BUILD_DATASET:
        from dataset.dataset_builder import build_dataset_pipeline
        filepath = build_dataset_pipeline(SYMBOLS, LOOKBACK_DAYS)
    else:
        # Run regular screener
        results = main()
```

## Quality Guarantees

### ✓ Leak-Free
- Feature window: all data up to decision date
- Label window: only data after decision date
- No circular dependencies
- Causality preserved

### ✓ Reproducible
- Deterministic date sorting
- Same symbol list → same dataset
- Seeded randomness in synthetic data
- Logged feature computation steps

### ✓ Explainable
- Every feature has documented formula
- Confidence scores trace back to rules
- Label computation explicitly defined
- Validation checks for NaN and bad values

### ✓ ML-Ready
- No missing values (NaN check)
- All numeric columns are float32/int8
- Labels are 0/1 binary
- Compatible with sklearn, XGBoost, PyTorch

## Usage

### Generate Dataset

```bash
# Edit main.py
BUILD_DATASET = True

# Run to create dataset
python3 main.py
```

### Load and Inspect Dataset

```python
import pandas as pd

# Load CSV
df = pd.read_csv('trading_dataset_20260124_031003.csv')

# Load Parquet (requires pyarrow)
df = pd.read_parquet('trading_dataset_20260124_031003.parquet')

# Check shape
print(f"Rows: {len(df)}, Columns: {len(df.columns)}")

# Label distribution
print(df['label'].value_counts(normalize=True))

# Features ready for training
X = df[['close', 'sma_20', 'sma_200', 'dist_20sma', 'dist_200sma',
         'sma20_slope', 'atr_pct', 'vol_ratio', 'pullback_depth', 'confidence']]
y = df['label']
```

### Train ML Model (Future)

```python
from sklearn.ensemble import GradientBoostingClassifier

X = df[feature_columns]
y = df['label']

model = GradientBoostingClassifier(random_state=42)
model.fit(X, y)

# Now you can make predictions on new trading opportunities
```

## Configuration Parameters

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `LABEL_HORIZON_DAYS` | 5 | Days to look ahead for label |
| `LABEL_TARGET_RETURN` | 0.02 | +2% profit target |
| `LABEL_MAX_DRAWDOWN` | -0.01 | -1% max loss |
| `DATASET_OUTPUT_DIR` | `./data` | Where to save files |
| `DATASET_FILE_FORMAT` | `parquet` | CSV or Parquet |

All can be modified in `config/settings.py`.

## Testing

Run the synthetic data test:

```bash
python3 test_dataset_synthetic.py
```

This test:
1. Creates synthetic price data for 3 symbols
2. Generates feature snapshots
3. Aggregates into a dataset
4. Saves and reloads to verify integrity
5. Checks for NaN values and validates label distribution

Output: CSV file in `/tmp/ml_dataset/`

## File Structure

```
dataset/
├── __init__.py
├── label_generator.py       # Label computation logic
├── feature_snapshot.py      # Feature snapshot creation
└── dataset_builder.py       # Aggregation and saving

config/
└── settings.py              # Includes LABEL_* and DATASET_* config

main.py                       # BUILD_DATASET flag and pipeline entry
```

## Next Steps (Not Implemented)

1. **Model Training**: Use sklearn/XGBoost to train on dataset
2. **Backtesting**: Run historical trades using predicted labels
3. **Hyperparameter Tuning**: Adjust LABEL_HORIZON_DAYS, thresholds, etc.
4. **Feature Engineering**: Add new derived features
5. **Cross-Validation**: Implement time-series CV to avoid lookahead

## Constraints

- **No ML frameworks added**: Dataset format is pure CSV/Parquet
- **No broker APIs**: Uses yfinance or synthetic data only
- **Python 3.10 only**: No deprecated code patterns
- **No model training**: Data preparation only
- **No confidence/feature changes**: Uses existing rules and indicators

---

**Status**: ✓ Complete and tested. Ready for ML training when needed.
