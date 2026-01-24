"""
Main trading screener orchestration.
Loads data, computes features, scores symbols, and ranks candidates.
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
from data.price_loader import load_price_data
from features.feature_engine import compute_features
from scoring.rule_scorer import score_symbol

# ============================================================================
# EXECUTION MODE FLAGS
# ============================================================================
RUN_BACKTEST = False        # Set to True to run diagnostic backtest
BUILD_DATASET = False       # Set to True to build ML-ready dataset


# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
def _setup_logging():
    """Configure logging for the application."""
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)
    
    # Console handler
    handler = logging.StreamHandler()
    handler.setLevel(LOG_LEVEL)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    handler.setFormatter(formatter)
    
    # Remove any existing handlers to avoid duplicates
    logger.handlers.clear()
    logger.addHandler(handler)
    
    return logger


logger = _setup_logging()


def main():
    """
    Main screener pipeline:
    1. Load price data for all symbols
    2. Compute features
    3. Score each symbol with validation
    4. Rank by confidence (deterministically)
    5. Display results
    """
    logger.info("=" * PRINT_WIDTH)
    logger.info(f"Trading Screener | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * PRINT_WIDTH)
    
    results = []
    failed_symbols = []
    skipped_symbols = []
    
    # Step 1 & 2: Load price data and compute features for each symbol
    logger.info(f"Scanning {len(SYMBOLS)} symbols...")
    
    for i, symbol in enumerate(SYMBOLS):
        logger.info(f"[{i+1:2d}/{len(SYMBOLS)}] Processing {symbol}")
        
        try:
            # Load data
            df = load_price_data(symbol, LOOKBACK_DAYS)
            if df is None or len(df) == 0:
                logger.warning(f"  {symbol}: Skipping (no data)")
                skipped_symbols.append((symbol, "no_data"))
                continue
            
            # Compute features
            features_df = compute_features(df)
            if features_df is None or len(features_df) == 0:
                logger.warning(f"  {symbol}: Skipping (insufficient history)")
                skipped_symbols.append((symbol, "insufficient_history"))
                continue
            
            # Take latest row only
            latest_row = features_df.iloc[-1].copy()
            
            # Validate latest row
            if latest_row.isna().any():
                logger.warning(f"  {symbol}: Skipping (NaN values in features)")
                skipped_symbols.append((symbol, "nan_values"))
                continue
            
            # Step 3: Score
            confidence = score_symbol(latest_row)
            
            if confidence is None:
                logger.warning(f"  {symbol}: Skipping (score computation failed)")
                skipped_symbols.append((symbol, "score_failed"))
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
            logger.info(f"  {symbol}: OK (confidence={confidence})")
        
        except Exception as e:
            logger.error(f"  {symbol}: Unexpected error: {type(e).__name__}: {e}")
            failed_symbols.append((symbol, str(e)))
            continue
    
    # Step 4: Rank by confidence (deterministically)
    if len(results) == 0:
        logger.error("No valid candidates found. Cannot continue.")
        logger.info("=" * PRINT_WIDTH)
        return pd.DataFrame()
    
    results_df = pd.DataFrame(results)
    
    # Sort deterministically: confidence (descending), then symbol (ascending)
    results_df = results_df.sort_values(
        by=['confidence', 'symbol'],
        ascending=[False, True]
    ).reset_index(drop=True)
    
    results_df['rank'] = range(1, len(results_df) + 1)
    
    # Step 5: Display top candidates
    logger.info("=" * PRINT_WIDTH)
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
    
    # Summary
    logger.info("\n" + "=" * PRINT_WIDTH)
    logger.info("SUMMARY")
    logger.info("=" * PRINT_WIDTH)
    logger.info(f"Total symbols scanned: {len(SYMBOLS)}")
    logger.info(f"Successfully scored: {len(results_df)}")
    logger.info(f"Skipped: {len(skipped_symbols)}")
    logger.info(f"Failed: {len(failed_symbols)}")
    
    if skipped_symbols:
        logger.info(f"\nSkipped symbols:")
        for symbol, reason in skipped_symbols[:5]:
            logger.info(f"  {symbol}: {reason}")
        if len(skipped_symbols) > 5:
            logger.info(f"  ... and {len(skipped_symbols) - 5} more")
    
    if failed_symbols:
        logger.warning(f"\nFailed symbols:")
        for symbol, error in failed_symbols[:5]:
            logger.warning(f"  {symbol}: {error}")
        if len(failed_symbols) > 5:
            logger.warning(f"  ... and {len(failed_symbols) - 5} more")
    
    # Confidence distribution
    logger.info(f"\nConfidence distribution:")
    conf_counts = results_df['confidence'].value_counts().sort_index(ascending=False)
    for conf, count in conf_counts.items():
        pct = 100 * count / len(results_df)
        logger.info(f"  Confidence {int(conf)}: {count:3d} symbols ({pct:5.1f}%)")
    
    logger.info("=" * PRINT_WIDTH)
    
    return results_df


if __name__ == '__main__':
    # Execute dataset building if enabled
    if BUILD_DATASET:
        logger.info("\n")
        from dataset.dataset_builder import build_dataset_pipeline
        
        filepath = build_dataset_pipeline(SYMBOLS, LOOKBACK_DAYS)
        if filepath:
            logger.info(f"\n✓ Dataset successfully built and saved to: {filepath}")
        else:
            logger.error("Dataset building failed")
    
    else:
        # Run regular screener
        results = main()
        
        # Optional: Run diagnostic backtest with capital simulation
        if RUN_BACKTEST:
            logger.info("\n")
            from backtest.simple_backtest import run_backtest
            from backtest.metrics import print_metrics, print_capital_metrics
            from backtest.capital_simulator import simulate_capital_growth
            
            trades = run_backtest(SYMBOLS)
            print_metrics(trades)
            
            # Run capital simulation
            metrics, equity_curve = simulate_capital_growth(trades)
            print_capital_metrics(metrics)
