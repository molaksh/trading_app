"""
Demo screener using synthetic data (no network required).
This shows the complete pipeline working end-to-end.
Production-grade with logging, error handling, and validation.
"""

import logging
import pandas as pd
from datetime import datetime

from config.settings import (
    LOOKBACK_DAYS,
    TOP_N_CANDIDATES,
    PRINT_WIDTH,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
)
from universe.symbols import SYMBOLS
from features.feature_engine import compute_features
from scoring.rule_scorer import score_symbol
from data.synthetic_data import generate_synthetic_ohlcv


# Configure logging
def _setup_logging():
    """Configure logging for the application."""
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)
    
    handler = logging.StreamHandler()
    handler.setLevel(LOG_LEVEL)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    handler.setFormatter(formatter)
    
    logger.handlers.clear()
    logger.addHandler(handler)
    
    return logger


logger = _setup_logging()


def main_demo():
    """
    Demo screener pipeline using synthetic data:
    1. Generate synthetic price data for all symbols
    2. Compute features
    3. Score each symbol with validation
    4. Rank by confidence (deterministically)
    5. Display results
    """
    logger.info("=" * PRINT_WIDTH)
    logger.info(f"Trading Screener (DEMO - Synthetic Data) | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * PRINT_WIDTH)
    
    results = []
    
    # Step 1 & 2: Generate synthetic data and compute features
    logger.info(f"\nGenerating and screening {len(SYMBOLS)} symbols...")
    
    for i, symbol in enumerate(SYMBOLS):
        try:
            # Generate synthetic data
            df = generate_synthetic_ohlcv(symbol, num_days=LOOKBACK_DAYS)
            
            # Compute features
            features_df = compute_features(df)
            if features_df is None or len(features_df) == 0:
                logger.warning(f"[{i+1:2d}/{len(SYMBOLS)}] {symbol:6s} - SKIP (insufficient history)")
                continue
            
            # Take latest row only
            latest_row = features_df.iloc[-1].copy()
            
            # Validate
            if latest_row.isna().any():
                logger.warning(f"[{i+1:2d}/{len(SYMBOLS)}] {symbol:6s} - SKIP (NaN values)")
                continue
            
            # Step 3: Score
            confidence = score_symbol(latest_row)
            
            if confidence is None:
                logger.warning(f"[{i+1:2d}/{len(SYMBOLS)}] {symbol:6s} - SKIP (score failed)")
                continue
            
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
            logger.info(f"[{i+1:2d}/{len(SYMBOLS)}] {symbol:6s} - OK (confidence {confidence})")
        
        except Exception as e:
            logger.error(f"[{i+1:2d}/{len(SYMBOLS)}] {symbol:6s} - Unexpected error: {type(e).__name__}: {e}")
            continue
    
    # Step 4: Rank by confidence (deterministically)
    if len(results) == 0:
        logger.error("No valid candidates found.")
        return pd.DataFrame()
    
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values(
        by=['confidence', 'symbol'],
        ascending=[False, True]
    ).reset_index(drop=True)
    results_df['rank'] = range(1, len(results_df) + 1)
    
    # Step 5: Display top candidates
    logger.info("\n" + "=" * PRINT_WIDTH)
    logger.info("TOP CANDIDATES")
    logger.info("=" * PRINT_WIDTH)
    
    display_df = results_df.head(TOP_N_CANDIDATES)[[
        'rank', 'symbol', 'confidence',
        'dist_200sma', 'vol_ratio', 'atr_pct'
    ]].copy()
    
    # Pretty print
    logger.info(f"\n{'Rank':<6} {'Symbol':<8} {'Conf':<6} {'Dist200SMA':<12} {'VolRatio':<10} {'ATRPct':<10}")
    logger.info("-" * 65)
    
    for _, row in display_df.iterrows():
        logger.info(
            f"{int(row['rank']):<6} "
            f"{row['symbol']:<8} "
            f"{int(row['confidence']):<6} "
            f"{row['dist_200sma']:>11.2%} "
            f"{row['vol_ratio']:>9.2f} "
            f"{row['atr_pct']:>9.2%}"
        )
    
    # Summary statistics
    logger.info("\n" + "=" * PRINT_WIDTH)
    logger.info(f"Summary: {len(results_df)} symbols scored")
    logger.info(f"\nConfidence Distribution:")
    conf_counts = results_df['confidence'].value_counts().sort_index(ascending=False)
    for conf, count in conf_counts.items():
        pct = 100 * count / len(results_df)
        logger.info(f"  Confidence {int(conf)}: {count:3d} symbols ({pct:5.1f}%)")
    logger.info("=" * PRINT_WIDTH)
    
    return results_df


if __name__ == '__main__':
    results = main_demo()
