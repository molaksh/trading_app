"""
Feature computation engine.
Computes technical indicators and features from OHLCV data.
Guarantees no lookahead bias and validates all outputs.
"""

import logging
from typing import Optional
import pandas as pd
import numpy as np
from scipy import stats
from config.settings import (
    SMA_SHORT,
    SMA_LONG,
    ATR_PERIOD,
    VOLUME_LOOKBACK,
    SMA_SLOPE_WINDOW,
    MIN_HISTORY_DAYS,
)

logger = logging.getLogger(__name__)


def compute_features(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Compute technical indicators and features from OHLCV data.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with columns [Open, High, Low, Close, Volume]
        indexed by date.
    
    Returns
    -------
    pd.DataFrame or None
        Feature DataFrame with columns:
        - close, sma_20, sma_200, dist_20sma, dist_200sma
        - sma20_slope, atr_pct, vol_ratio, pullback_depth
        Returns None if insufficient history or validation fails.
    """
    if df is None or len(df) == 0:
        logger.error("Received empty DataFrame")
        return None
    
    if len(df) < MIN_HISTORY_DAYS:
        logger.warning(f"Insufficient history: {len(df)} days < {MIN_HISTORY_DAYS} required")
        return None
    
    try:
        result = df.copy()
        
        # SMA indicators
        result['sma_20'] = result['Close'].rolling(window=SMA_SHORT, min_periods=SMA_SHORT).mean()
        result['sma_200'] = result['Close'].rolling(window=SMA_LONG, min_periods=SMA_LONG).mean()
        
        # Distance to SMAs (percentage)
        result['dist_20sma'] = (result['Close'] - result['sma_20']) / result['sma_20']
        result['dist_200sma'] = (result['Close'] - result['sma_200']) / result['sma_200']
        
        # SMA20 slope (5-day linear regression)
        result['sma20_slope'] = _compute_slope(result['sma_20'], window=SMA_SLOPE_WINDOW)
        
        # ATR-based volatility (no lookahead)
        result['atr'] = _compute_atr(result, period=ATR_PERIOD)
        result['atr_pct'] = result['atr'] / result['Close']
        
        # Volume ratio
        result['vol_avg_20'] = result['Volume'].rolling(window=VOLUME_LOOKBACK, min_periods=VOLUME_LOOKBACK).mean()
        result['vol_ratio'] = result['Volume'] / result['vol_avg_20']
        
        # Pullback depth (% drop from 20-day rolling high)
        result['high_20'] = result['High'].rolling(window=SMA_SHORT, min_periods=SMA_SHORT).max()
        result['pullback_depth'] = (result['high_20'] - result['Close']) / result['high_20']
        
        # Select output columns
        output_cols = [
            'Close',
            'sma_20',
            'sma_200',
            'dist_20sma',
            'dist_200sma',
            'sma20_slope',
            'atr_pct',
            'vol_ratio',
            'pullback_depth'
        ]
        
        result = result[output_cols].copy()
        result.columns = [
            'close',
            'sma_20',
            'sma_200',
            'dist_20sma',
            'dist_200sma',
            'sma20_slope',
            'atr_pct',
            'vol_ratio',
            'pullback_depth'
        ]
        
        # Drop rows with NaN (insufficient history for indicators)
        result = result.dropna()
        
        if len(result) == 0:
            logger.error("All rows became NaN after feature computation")
            return None
        
        logger.debug(f"Computed features for {len(result)} rows")
        return result
    
    except Exception as e:
        logger.error(f"Feature computation failed: {type(e).__name__}: {e}")
        return None


def _compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """
    Compute Average True Range (ATR) without lookahead.
    
    Parameters
    ----------
    df : pd.DataFrame
        Must have 'High', 'Low', 'Close' columns
    period : int
        ATR period (typically 14)
    
    Returns
    -------
    pd.Series
        ATR values
    """
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    # True Range = max(High - Low, |High - Close_prev|, |Low - Close_prev|)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # ATR = EMA of TR over period
    atr = tr.ewm(span=period, adjust=False).mean()
    
    return atr


def _compute_slope(series: pd.Series, window: int) -> pd.Series:
    """
    Compute linear regression slope over a rolling window.
    No lookahead: each slope is computed from current and past data only.
    
    Parameters
    ----------
    series : pd.Series
        Input series
    window : int
        Window size for regression
    
    Returns
    -------
    pd.Series
        Slope values
    """
    def slope_func(x):
        if len(x) < window or x.isna().any():
            return np.nan
        x_vals = np.arange(len(x))
        y_vals = x.values
        # Linear regression: y = mx + b
        slope, _, _, _, _ = stats.linregress(x_vals, y_vals)
        return slope
    
    slopes = series.rolling(window=window, min_periods=window).apply(
        slope_func,
        raw=False
    )
    
    return slopes
