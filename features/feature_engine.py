"""
Feature computation engine.
Computes technical indicators and features from OHLCV data.
Guarantees no lookahead bias and validates all outputs.

PHASE: Future-proofing refactor
- Added RSI, MACD, EMA, Bollinger Bands, ADX, OBV
- New indicators are COMPUTED and STORED only
- NOT automatically used in strategy logic (opt-in required)
- Maintains backward compatibility with existing features
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


def compute_features(df: pd.DataFrame, include_extended: bool = False) -> Optional[pd.DataFrame]:
    """
    Compute technical indicators and features from OHLCV data.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with columns [Open, High, Low, Close, Volume]
        indexed by date.
    include_extended : bool, default False
        If True, compute extended indicators (RSI, MACD, EMA, Bollinger, ADX, OBV)
        Default False maintains backward compatibility
    
    Returns
    -------
    pd.DataFrame or None
        Feature DataFrame with original columns:
        - close, sma_20, sma_200, dist_20sma, dist_200sma
        - sma20_slope, atr_pct, vol_ratio, pullback_depth
        
        If include_extended=True, also includes:
        - rsi_14, macd, macd_signal, macd_hist
        - ema_12, ema_26, bb_upper, bb_middle, bb_lower, bb_width
        - adx_14, obv
        
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
        
        # ====================================================================
        # ORIGINAL INDICATORS (backward compatible, always computed)
        # ====================================================================
        
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
        
        # Original output columns (backward compatible)
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
        
        # ====================================================================
        # EXTENDED INDICATORS (optional, for future use)
        # ====================================================================
        if include_extended:
            logger.debug("Computing extended indicators (RSI, MACD, EMA, Bollinger, ADX, OBV)")
            
            # RSI (Relative Strength Index)
            result['rsi_14'] = _compute_rsi(result['Close'], period=14)
            
            # MACD (Moving Average Convergence Divergence)
            macd_data = _compute_macd(result['Close'], fast=12, slow=26, signal=9)
            result['macd'] = macd_data['macd']
            result['macd_signal'] = macd_data['signal']
            result['macd_hist'] = macd_data['histogram']
            
            # EMA (Exponential Moving Average)
            result['ema_12'] = result['Close'].ewm(span=12, adjust=False).mean()
            result['ema_26'] = result['Close'].ewm(span=26, adjust=False).mean()
            
            # Bollinger Bands
            bb_data = _compute_bollinger_bands(result['Close'], period=20, std_dev=2)
            result['bb_upper'] = bb_data['upper']
            result['bb_middle'] = bb_data['middle']
            result['bb_lower'] = bb_data['lower']
            result['bb_width'] = bb_data['width']
            
            # ADX (Average Directional Index)
            result['adx_14'] = _compute_adx(result, period=14)
            
            # OBV (On-Balance Volume)
            result['obv'] = _compute_obv(result['Close'], result['Volume'])
            
            # Add extended columns to output
            output_cols.extend([
                'rsi_14',
                'macd', 'macd_signal', 'macd_hist',
                'ema_12', 'ema_26',
                'bb_upper', 'bb_middle', 'bb_lower', 'bb_width',
                'adx_14',
                'obv'
            ])
        
        # Select output columns
        result = result[output_cols].copy()
        
        # Rename columns to lowercase (backward compatible)
        rename_map = {
            'Close': 'close',
            'sma_20': 'sma_20',
            'sma_200': 'sma_200',
            'dist_20sma': 'dist_20sma',
            'dist_200sma': 'dist_200sma',
            'sma20_slope': 'sma20_slope',
            'atr_pct': 'atr_pct',
            'vol_ratio': 'vol_ratio',
            'pullback_depth': 'pullback_depth',
        }
        result.rename(columns=rename_map, inplace=True)
        
        # Drop rows with NaN (insufficient history for indicators)
        result = result.dropna()
        
        if len(result) == 0:
            logger.error("All rows became NaN after feature computation")
            return None
        
        logger.debug(f"Computed features for {len(result)} rows (extended={include_extended})")
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


# =============================================================================
# EXTENDED INDICATORS (Phase: Future-proofing)
# =============================================================================
# These indicators are COMPUTED but NOT automatically used in strategies.
# Strategies must explicitly opt-in to use them.
# =============================================================================


def _compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Compute Relative Strength Index (RSI).
    
    RSI measures momentum, typically used to identify overbought/oversold conditions.
    Values range from 0-100:
    - RSI > 70: Overbought (potential reversal down)
    - RSI < 30: Oversold (potential reversal up)
    
    No lookahead bias: uses only past data.
    
    Parameters
    ----------
    series : pd.Series
        Price series (typically Close)
    period : int
        RSI period (default 14)
    
    Returns
    -------
    pd.Series
        RSI values (0-100)
    """
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def _compute_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """
    Compute MACD (Moving Average Convergence Divergence).
    
    MACD tracks trend strength and potential reversals:
    - MACD line: EMA(fast) - EMA(slow)
    - Signal line: EMA(MACD, signal period)
    - Histogram: MACD - Signal
    
    Crossovers indicate trend changes:
    - MACD crosses above signal: Bullish
    - MACD crosses below signal: Bearish
    
    No lookahead bias.
    
    Parameters
    ----------
    series : pd.Series
        Price series (typically Close)
    fast : int
        Fast EMA period (default 12)
    slow : int
        Slow EMA period (default 26)
    signal : int
        Signal line EMA period (default 9)
    
    Returns
    -------
    dict
        {
            'macd': MACD line,
            'signal': Signal line,
            'histogram': MACD histogram
        }
    """
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    return {
        'macd': macd_line,
        'signal': signal_line,
        'histogram': histogram
    }


def _compute_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> dict:
    """
    Compute Bollinger Bands.
    
    Bollinger Bands measure volatility and potential price extremes:
    - Middle band: SMA(period)
    - Upper band: Middle + (std_dev * standard deviation)
    - Lower band: Middle - (std_dev * standard deviation)
    - Width: (Upper - Lower) / Middle (normalized volatility)
    
    Price touching bands may signal reversals or breakouts.
    
    No lookahead bias.
    
    Parameters
    ----------
    series : pd.Series
        Price series (typically Close)
    period : int
        SMA period (default 20)
    std_dev : float
        Standard deviation multiplier (default 2.0)
    
    Returns
    -------
    dict
        {
            'upper': Upper band,
            'middle': Middle band (SMA),
            'lower': Lower band,
            'width': Band width (normalized)
        }
    """
    middle = series.rolling(window=period, min_periods=period).mean()
    std = series.rolling(window=period, min_periods=period).std()
    
    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)
    width = (upper - lower) / middle
    
    return {
        'upper': upper,
        'middle': middle,
        'lower': lower,
        'width': width
    }


def _compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Compute ADX (Average Directional Index).
    
    ADX measures trend strength (not direction):
    - ADX > 25: Strong trend
    - ADX < 20: Weak trend or ranging market
    - ADX rising: Trend strengthening
    - ADX falling: Trend weakening
    
    No lookahead bias.
    
    Parameters
    ----------
    df : pd.DataFrame
        Must have 'High', 'Low', 'Close' columns
    period : int
        ADX period (default 14)
    
    Returns
    -------
    pd.Series
        ADX values (0-100)
    """
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    # True Range (same as ATR calculation)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Directional Movement
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)
    
    # Smoothed TR and DM
    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)
    
    # Directional Index
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    
    # ADX (smoothed DX)
    adx = dx.ewm(span=period, adjust=False).mean()
    
    return adx


def _compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """
    Compute OBV (On-Balance Volume).
    
    OBV tracks cumulative volume flow:
    - Up day (close > close_prev): Add volume
    - Down day (close < close_prev): Subtract volume
    - Flat day: No change
    
    Used to detect volume-price divergences:
    - Price rising, OBV falling: Bearish divergence (weak rally)
    - Price falling, OBV rising: Bullish divergence (accumulation)
    
    No lookahead bias.
    
    Parameters
    ----------
    close : pd.Series
        Close prices
    volume : pd.Series
        Volume
    
    Returns
    -------
    pd.Series
        OBV values (cumulative volume)
    """
    direction = np.sign(close.diff())
    obv = (direction * volume).fillna(0).cumsum()
    
    return obv

