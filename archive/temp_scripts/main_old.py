"""
Main trading screener orchestration.
Loads data, computes features, scores symbols, and ranks candidates.
"""

import pandas as pd
from datetime import datetime

from config.settings import (
    LOOKBACK_DAYS,
    TOP_N_CANDIDATES,
    PRINT_WIDTH,
)
from universe.symbols import SYMBOLS
from data.price_loader import load_price_data
from features.feature_engine import compute_features
from scoring.rule_scorer import score_symbol


def main():
    """
    Main screener pipeline:
    1. Load price data for all symbols
    2. Compute features
    3. Score each symbol
    4. Rank by confidence
    5. Display results
    """
    print("=" * PRINT_WIDTH)
    print(f"Trading Screener | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * PRINT_WIDTH)
    
    results = []
    failed_symbols = []
    
    # Step 1 & 2: Load price data and compute features for each symbol
    print(f"\nScanning {len(SYMBOLS)} symbols...")
    
    for i, symbol in enumerate(SYMBOLS):
        print(f"  [{i+1}/{len(SYMBOLS)}] {symbol:6s}", end='', flush=True)
        
        # Load data
        df = load_price_data(symbol, LOOKBACK_DAYS)
        if df is None or len(df) == 0:
            print(" -> SKIP (no data)")
            failed_symbols.append(symbol)
            continue
        
        # Compute features
        features_df = compute_features(df)
        if features_df is None or len(features_df) == 0:
            print(" -> SKIP (insufficient history)")
            failed_symbols.append(symbol)
            continue
        
        # Take latest row only
        latest_row = features_df.iloc[-1].copy()
        
        # Step 3: Score
        confidence = score_symbol(latest_row)
        
        # Store result
        result_dict = {
            'symbol': symbol,
            'confidence': confidence,
            'close': latest_row['close'],
            'sma_20': latest_row['sma_20'],
            'sma_200': latest_row['sma_200'],
            'dist_20sma': latest_row['dist_20sma'],
            'dist_200sma': latest_row['dist_200sma'],
            'sma20_slope': latest_row['sma20_slope'],
            'atr_pct': latest_row['atr_pct'],
            'vol_ratio': latest_row['vol_ratio'],
            'pullback_depth': latest_row['pullback_depth'],
        }
        results.append(result_dict)
        print(" -> OK")
    
    # Step 4: Rank by confidence (descending)
    if len(results) == 0:
        print("\nNo valid candidates found. Please check network connectivity or data sources.")
        return pd.DataFrame()
    
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('confidence', ascending=False).reset_index(drop=True)
    results_df['rank'] = range(1, len(results_df) + 1)
    
    # Step 5: Display top candidates
    print("\n" + "=" * PRINT_WIDTH)
    print("TOP CANDIDATES")
    print("=" * PRINT_WIDTH)
    
    display_df = results_df.head(TOP_N_CANDIDATES)[[
        'rank', 'symbol', 'confidence',
        'dist_200sma', 'vol_ratio', 'atr_pct'
    ]].copy()
    
    # Format columns for display
    display_df.columns = ['Rank', 'Symbol', 'Conf', 'Dist200SMA', 'VolRatio', 'ATRPct']
    
    # Pretty print
    print(f"\n{'Rank':<6} {'Symbol':<8} {'Conf':<6} {'Dist200SMA':<12} {'VolRatio':<10} {'ATRPct':<10}")
    print("-" * 65)
    
    for _, row in display_df.iterrows():
        print(
            f"{int(row['Rank']):<6} "
            f"{row['Symbol']:<8} "
            f"{int(row['Conf']):<6} "
            f"{row['Dist200SMA']:>11.2%} "
            f"{row['VolRatio']:>9.2f} "
            f"{row['ATRPct']:>9.2%}"
        )
    
    # Summary
    print("\n" + "=" * PRINT_WIDTH)
    print(f"Summary: {len(results_df)} symbols scored, {len(failed_symbols)} failed")
    if failed_symbols:
        print(f"Failed: {', '.join(failed_symbols[:10])}")
        if len(failed_symbols) > 10:
            print(f"  ... and {len(failed_symbols) - 10} more")
    print("=" * PRINT_WIDTH)
    
    return results_df


if __name__ == '__main__':
    results = main()
