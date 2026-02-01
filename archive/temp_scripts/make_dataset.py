#!/usr/bin/env python3
"""Quick dataset creation without network dependencies."""

import logging
logging.basicConfig(level=logging.WARNING)  # Suppress yfinance logs

from data.synthetic_data import generate_synthetic_ohlcv
from dataset.feature_snapshot import create_feature_snapshots
from dataset.dataset_builder import DatasetBuilder
import pandas as pd

symbols = ['DEMO_A', 'DEMO_B', 'DEMO_C']
all_snapshots = []

print("Creating ML dataset...")
for symbol in symbols:
    print(f"  {symbol}...", end=" ", flush=True)
    df = generate_synthetic_ohlcv(symbol, num_days=300)
    snapshots = create_feature_snapshots(df, symbol)
    if snapshots is not None:
        all_snapshots.append(snapshots)
        print(f"✓")

dataset = pd.concat(all_snapshots, ignore_index=True)
dataset = dataset.sort_values(['date', 'symbol']).reset_index(drop=True)

print(f"\nDataset created:")
print(f"  Rows: {len(dataset)}")
print(f"  Symbols: {dataset['symbol'].nunique()}")
print(f"  Labels: {dict(dataset['label'].value_counts().sort_index())}")

builder = DatasetBuilder(output_dir='./data', file_format='csv')
filepath = builder.save_dataset(dataset, 'ml_dataset')
print(f"  Saved: {filepath}")
