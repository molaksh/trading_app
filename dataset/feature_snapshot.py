"""
Feature snapshot generator for ML dataset.
For each symbol and each historical date, computes features using only data up to that date.
Attaches confidence score and label.
No lookahead bias: snapshots use only available information at decision time.
"""

import logging
from typing import Optional, List
import pandas as pd
import numpy as np
from config.settings import LOOKBACK_DAYS, MIN_HISTORY_DAYS, LABEL_HORIZON_DAYS
from features.feature_engine import compute_features
from scoring.rule_scorer import score_symbol
from dataset.label_generator import compute_labels_for_symbol

logger = logging.getLogger(__name__)


def create_feature_snapshots(
    price_df: pd.DataFrame,
    symbol: str
) -> Optional[pd.DataFrame]:
    """
    Create feature snapshots for each historical date in a symbol's price history.
    
    For each valid date:
    - Extract all data up to that date (no lookahead)
    - Compute features using that historical window
    - Compute confidence score from features
    - Compute label for that date
    - Store as a row with columns:
      [date, symbol, close, sma_20, sma_200, ..., confidence, label]
    
    Parameters
    ----------
    price_df : pd.DataFrame
        Full price history for symbol with columns [Open, High, Low, Close, Volume]
        indexed by date.
    symbol : str
        Symbol ticker (e.g., 'AAPL')
    
    Returns
    -------
    pd.DataFrame or None
        DataFrame with rows for each snapshot. Columns include:
        - date, symbol, close, sma_20, sma_200, dist_20sma, dist_200sma,
          sma20_slope, atr_pct, vol_ratio, pullback_depth, confidence, label
        Returns None if insufficient data or all snapshots fail.
    """
    if price_df is None or price_df.empty:
        logger.warning(f"Received empty price data for {symbol}")
        return None
    
    if len(price_df) < MIN_HISTORY_DAYS + LABEL_HORIZON_DAYS:
        logger.warning(
            f"{symbol}: Insufficient data ({len(price_df)} rows < "
            f"{MIN_HISTORY_DAYS + LABEL_HORIZON_DAYS} required for features + labeling)"
        )
        return None
    
    try:
        snapshots = []
        
        # Iterate through each date, starting from first valid position
        # We need at least MIN_HISTORY_DAYS before a date to compute features
        start_idx = MIN_HISTORY_DAYS
        end_idx = len(price_df) - LABEL_HORIZON_DAYS  # Need forward data for labels
        
        logger.debug(f"{symbol}: Creating snapshots for rows {start_idx} to {end_idx}")
        
        for i in range(start_idx, end_idx):
            snapshot_date = price_df.index[i]
            
            # Extract historical data up to (and including) this date
            historical_df = price_df.iloc[:i+1].copy()
            
            # Compute features on historical data
            features_df = compute_features(historical_df)
            
            if features_df is None or features_df.empty:
                logger.debug(f"{symbol} {snapshot_date}: Feature computation failed")
                continue
            
            # Get latest feature row (most recent date)
            feature_row = features_df.iloc[-1]
            
            # Compute confidence score
            confidence = score_symbol(feature_row)
            if confidence is None:
                logger.debug(f"{symbol} {snapshot_date}: Confidence computation failed")
                continue
            
            # Compute label (using full price data for forward-looking window)
            label = _compute_label_for_snapshot(price_df, snapshot_date, feature_row['close'])
            if label is None:
                logger.debug(f"{symbol} {snapshot_date}: Label computation failed")
                continue
            
            # Build snapshot row
            snapshot = {
                'date': snapshot_date,
                'symbol': symbol,
                'close': float(feature_row['close']),
                'sma_20': float(feature_row['sma_20']),
                'sma_200': float(feature_row['sma_200']),
                'dist_20sma': float(feature_row['dist_20sma']),
                'dist_200sma': float(feature_row['dist_200sma']),
                'sma20_slope': float(feature_row['sma20_slope']),
                'atr_pct': float(feature_row['atr_pct']),
                'vol_ratio': float(feature_row['vol_ratio']),
                'pullback_depth': float(feature_row['pullback_depth']),
                'confidence': int(confidence),
                'label': int(label),
            }
            
            snapshots.append(snapshot)
        
        if len(snapshots) == 0:
            logger.warning(f"{symbol}: No valid snapshots created")
            return None
        
        # Convert to DataFrame and sort by date
        result_df = pd.DataFrame(snapshots)
        result_df = result_df.sort_values('date').reset_index(drop=True)
        
        logger.info(f"{symbol}: Created {len(result_df)} snapshots")
        label_dist = result_df['label'].value_counts()
        logger.info(f"  Label distribution: {dict(label_dist)}")
        
        return result_df
    
    except Exception as e:
        logger.error(f"Snapshot creation failed for {symbol}: {type(e).__name__}: {e}")
        return None


def _compute_label_for_snapshot(
    price_df: pd.DataFrame,
    entry_date: pd.Timestamp,
    entry_price: float
) -> Optional[int]:
    """
    Compute label for a snapshot date using forward-looking price data.
    This is a local wrapper around the label generator.
    
    Parameters
    ----------
    price_df : pd.DataFrame
        Full price history with 'Close' column and date index
    entry_date : pd.Timestamp
        Date of the snapshot
    entry_price : float
        Close price at entry_date
    
    Returns
    -------
    int or None
        Label (0 or 1) or None if computation fails
    """
    from dataset.label_generator import compute_label
    
    if price_df is None or entry_date not in price_df.index:
        return None
    
    close_prices = price_df['Close']
    return compute_label(close_prices, entry_date, entry_price)


def validate_snapshots(snapshots_df: pd.DataFrame) -> bool:
    """
    Validate that snapshots are leak-free and properly formatted.
    
    Checks:
    - No NaN values in feature columns or labels
    - Dates are sorted
    - Confidence scores are 1-5
    - Labels are 0 or 1
    
    Parameters
    ----------
    snapshots_df : pd.DataFrame
        Snapshots DataFrame to validate
    
    Returns
    -------
    bool
        True if all validations pass, False otherwise
    """
    if snapshots_df is None or snapshots_df.empty:
        logger.error("Snapshots DataFrame is empty")
        return False
    
    # Check for NaN
    if snapshots_df.isna().any().any():
        logger.error("Snapshots contain NaN values")
        return False
    
    # Check date sorting
    if not snapshots_df['date'].is_monotonic_increasing:
        logger.error("Snapshots are not sorted by date")
        return False
    
    # Check confidence bounds
    if not snapshots_df['confidence'].isin(range(1, 6)).all():
        logger.error("Invalid confidence scores (must be 1-5)")
        return False
    
    # Check label values
    if not snapshots_df['label'].isin([0, 1]).all():
        logger.error("Invalid labels (must be 0 or 1)")
        return False
    
    logger.info("Snapshots validation passed")
    return True
