#!/usr/bin/env python3
"""Generate a sample ML dataset CSV file."""

from data.synthetic_data import generate_synthetic_ohlcv
from dataset.feature_snapshot import create_feature_snapshots
from dataset.dataset_builder import DatasetBuilder
import pandas as pd

# Generate synthetic data for 5 symbols
print("Generating ML dataset...")
symbols = ['DEMO_A', 'DEMO_B', 'DEMO_C', 'DEMO_D', 'DEMO_E']
all_snapshots = []

for i, symbol in enumerate(symbols, 1):
    print(f"  [{i}/{len(symbols)}] {symbol}...", end=" ", flush=True)
    df = generate_synthetic_ohlcv(symbol, num_days=300)
    snapshots = create_feature_snapshots(df, symbol)
    if snapshots is not None:
        all_snapshots.append(snapshots)
        print(f"✓ ({len(snapshots)} rows)")
    else:
        print("✗")

# Aggregate
print(f"\nAggregating snapshots...")
dataset = pd.concat(all_snapshots, ignore_index=True)
dataset = dataset.sort_values(['date', 'symbol']).reset_index(drop=True)

print(f"Dataset shape: {dataset.shape}")
print(f"Columns: {list(dataset.columns)}")

# Label distribution
label_counts = dataset['label'].value_counts().sort_index()
total = len(dataset)
print(f"\nLabel distribution:")
for label, count in label_counts.items():
    pct = 100 * count / total
    print(f"  Label {label}: {count:4d} ({pct:5.1f}%)")

# Save
print(f"\nSaving dataset...")
builder = DatasetBuilder(output_dir='./data', file_format='csv')
filepath = builder.save_dataset(dataset, 'ml_trading_dataset')

if filepath:
    print(f"✓ Successfully saved to: {filepath}")
else:
    print("✗ Failed to save dataset")
