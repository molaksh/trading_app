"""
Rule-based confidence scorer for symbols.
Converts features into a 1-5 confidence score with validation.
"""

import logging
from typing import Optional
import pandas as pd
from config.settings import (
    MIN_CONFIDENCE,
    MAX_CONFIDENCE,
    THRESHOLD_PULLBACK,
    THRESHOLD_VOLUME_RATIO,
    THRESHOLD_ATR_PCT,
    THRESHOLD_SMA_SLOPE,
)

logger = logging.getLogger(__name__)


def score_symbol(features_row: pd.Series) -> Optional[int]:
    """
    Assign a confidence score (1-5) based on feature rules.
    
    Scoring rules (5 rules, +1 each):
    - +1 if close > sma_200 (above long-term trend)
    - +1 if sma20_slope > 0 (short-term momentum positive)
    - +1 if pullback_depth < threshold (shallow pullback)
    - +1 if vol_ratio > threshold (volume above average)
    - +1 if atr_pct < threshold (volatility below threshold)
    
    Parameters
    ----------
    features_row : pd.Series
        A row from the features DataFrame containing:
        close, sma_20, sma_200, dist_20sma, dist_200sma,
        sma20_slope, atr_pct, vol_ratio, pullback_depth
    
    Returns
    -------
    int or None
        Confidence score from 1 to 5, or None if validation fails
    """
    # Validate input
    if features_row is None:
        logger.error("Received None for features_row")
        return None
    
    required_cols = {
        'close', 'sma_20', 'sma_200', 'sma20_slope',
        'atr_pct', 'vol_ratio', 'pullback_depth'
    }
    
    if not required_cols.issubset(set(features_row.index)):
        logger.error(f"Missing required columns: {required_cols - set(features_row.index)}")
        return None
    
    # Check for NaN values
    if features_row[list(required_cols)].isna().any():
        logger.error(f"NaN values detected in features_row: {features_row[features_row.isna()]}")
        return None
    
    try:
        score = 0
        
        # Rule 1: Price above 200-day SMA (long-term uptrend)
        if features_row['close'] > features_row['sma_200']:
            score += 1
            logger.debug(f"Rule 1 triggered: close ({features_row['close']:.2f}) > sma_200 ({features_row['sma_200']:.2f})")
        
        # Rule 2: SMA20 slope positive (short-term momentum)
        if features_row['sma20_slope'] > THRESHOLD_SMA_SLOPE:
            score += 1
            logger.debug(f"Rule 2 triggered: sma20_slope ({features_row['sma20_slope']:.4f}) > {THRESHOLD_SMA_SLOPE}")
        
        # Rule 3: Shallow pullback (% drop from 20-day high)
        if features_row['pullback_depth'] < THRESHOLD_PULLBACK:
            score += 1
            logger.debug(f"Rule 3 triggered: pullback_depth ({features_row['pullback_depth']:.4f}) < {THRESHOLD_PULLBACK}")
        
        # Rule 4: Volume above average
        if features_row['vol_ratio'] > THRESHOLD_VOLUME_RATIO:
            score += 1
            logger.debug(f"Rule 4 triggered: vol_ratio ({features_row['vol_ratio']:.2f}) > {THRESHOLD_VOLUME_RATIO}")
        
        # Rule 5: Low volatility relative to price
        if features_row['atr_pct'] < THRESHOLD_ATR_PCT:
            score += 1
            logger.debug(f"Rule 5 triggered: atr_pct ({features_row['atr_pct']:.4f}) < {THRESHOLD_ATR_PCT}")
        
        # Clamp to [MIN_CONFIDENCE, MAX_CONFIDENCE]
        final_score = max(MIN_CONFIDENCE, min(score, MAX_CONFIDENCE))
        
        logger.debug(f"Score calculation: raw={score}, final={final_score}")
        
        return int(final_score)
    
    except Exception as e:
        logger.error(f"Score computation failed: {type(e).__name__}: {e}")
        return None


def score_candidates(features_df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Score all candidates in a features DataFrame.
    
    Parameters
    ----------
    features_df : pd.DataFrame
        DataFrame with features for each symbol (must have all required columns)
    
    Returns
    -------
    pd.DataFrame or None
        Input DataFrame with an additional 'confidence' column,
        or None if input validation fails
    """
    if features_df is None or features_df.empty:
        logger.error("Received empty features DataFrame")
        return None
    
    try:
        result = features_df.copy()
        result['confidence'] = result.apply(score_symbol, axis=1)
        
        # Check if any scores were successfully computed
        valid_scores = result['confidence'].notna().sum()
        if valid_scores == 0:
            logger.error("No valid confidence scores computed")
            return None
        
        logger.info(f"Scored {valid_scores}/{len(result)} candidates")
        return result
    
    except Exception as e:
        logger.error(f"Batch scoring failed: {type(e).__name__}: {e}")
        return None
