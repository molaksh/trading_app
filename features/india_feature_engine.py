"""
India-specific feature normalization (Phase B).

Reuses existing feature computation but normalizes India-specific metrics:
- ATR as percentile (not raw %)
- Volume as rolling percentile (not ratio)
- Preserves feature names for downstream compatibility

Key insight: India markets have different volatility/liquidity profiles than US.
Normalization ensures features are comparable across markets.
"""

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# INDIA FEATURE NORMALIZER
# ============================================================================
class IndiaFeatureNormalizer:
    """
    Normalize computed features for India market.
    
    Usage:
        normalizer = IndiaFeatureNormalizer()
        df_normalized = normalizer.normalize(df_raw)
    """
    
    def __init__(self):
        """Initialize normalizer with India market defaults."""
        self.atr_percentile_window = 60      # Days for percentile calc
        self.volume_percentile_window = 20   # Days for percentile calc
        
    def normalize(self, df: pd.DataFrame, symbol: str = "") -> pd.DataFrame:
        """
        Normalize raw features for India market.
        
        Args:
            df: DataFrame with raw features (from existing feature engine)
            symbol: Stock symbol (for logging)
            
        Returns:
            DataFrame with normalized features
        """
        df = df.copy()
        
        # Normalize ATR: convert to percentile
        if "atr" in df.columns and "close" in df.columns:
            df["atr_pct"] = df["atr"] / df["close"]
            df["atr_percentile"] = df["atr_pct"].rolling(
                window=self.atr_percentile_window
            ).apply(lambda x: (x[-1] < x[:-1]).sum() / len(x[:-1]) * 100)
            logger.debug(f"[INDIA] {symbol}: Normalized ATR to percentile")
        
        # Normalize Volume: convert to percentile
        if "volume" in df.columns:
            df["volume_percentile"] = df["volume"].rolling(
                window=self.volume_percentile_window
            ).apply(lambda x: (x[-1] > x[:-1]).sum() / len(x[:-1]) * 100)
            logger.debug(f"[INDIA] {symbol}: Normalized Volume to percentile")
        
        # Scale-invariant momentum (SMA slopes in % terms)
        if "sma20" in df.columns and "sma200" in df.columns:
            df["sma20_pct"] = (df["sma20"] - df["sma20"].shift(1)) / df["sma20"].shift(1) * 100
            df["sma200_pct"] = (df["sma200"] - df["sma200"].shift(1)) / df["sma200"].shift(1) * 100
            logger.debug(f"[INDIA] {symbol}: Scaled SMA slopes")
        
        return df


# ============================================================================
# INDIA-AWARE FEATURE ENGINEER
# ============================================================================
def compute_india_features(
    df: pd.DataFrame,
    symbol: str = "",
    lookback_days: int = 252,
    sma_short: int = 20,
    sma_long: int = 200,
    atr_period: int = 14,
    volume_lookback: int = 20,
) -> pd.DataFrame:
    """
    Compute features for India market.
    
    Reuses existing computation but normalizes outputs.
    Ensures compatibility with US feature names downstream.
    
    Args:
        df: OHLCV DataFrame
        symbol: Stock symbol
        lookback_days: Historical window
        sma_short: Short SMA period (days)
        sma_long: Long SMA period (days)
        atr_period: ATR period
        volume_lookback: Volume average period
        
    Returns:
        DataFrame with computed + normalized features
    """
    df = df.copy()
    
    # ========================================================================
    # STANDARD FEATURES (same as US)
    # ========================================================================
    
    # SMAs
    df["sma20"] = df["close"].rolling(window=sma_short).mean()
    df["sma200"] = df["close"].rolling(window=sma_long).mean()
    
    # True Range
    df["tr"] = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    
    # ATR
    df["atr"] = df["tr"].rolling(window=atr_period).mean()
    
    # Volume
    df["volume_ma"] = df["volume"].rolling(window=volume_lookback).mean()
    df["volume_ratio"] = df["volume"] / df["volume_ma"]
    
    # Pullback
    df["sma20_high"] = df["close"].rolling(window=sma_short).max()
    df["pullback"] = (df["sma20_high"] - df["close"]) / df["sma20_high"]
    
    # SMA Slope
    df["sma20_lag1"] = df["sma20"].shift(1)
    df["sma20_slope"] = (df["sma20"] - df["sma20_lag1"]) / df["sma20_lag1"]
    
    logger.debug(f"[INDIA] {symbol}: Computed {len(df)} days of features")
    
    # ========================================================================
    # INDIA-SPECIFIC NORMALIZATION
    # ========================================================================
    normalizer = IndiaFeatureNormalizer()
    df = normalizer.normalize(df, symbol)
    
    # Select final feature set (preserve US names for compatibility)
    feature_cols = [
        "close", "volume",
        "sma20", "sma200",
        "atr", "atr_pct",
        "volume_ratio", "pullback",
        "sma20_slope",
        "atr_percentile", "volume_percentile",  # India-specific
    ]
    
    available_cols = [c for c in feature_cols if c in df.columns]
    df = df[available_cols]
    
    logger.info(f"[INDIA] {symbol}: Generated {len(df)} feature rows")
    return df


# ============================================================================
# TESTING
# ============================================================================
if __name__ == "__main__":
    # Test feature computation
    print("\n[TEST] India feature computation...")
    
    # Create sample data
    np.random.seed(42)
    dates = pd.date_range(start="2024-01-01", periods=252, freq="D")
    close_price = 100 * np.exp(np.random.randn(252).cumsum() * 0.01)
    volume_data = np.random.randint(1_000_000, 10_000_000, 252)
    
    df_sample = pd.DataFrame({
        "date": dates,
        "open": close_price * 0.99,
        "high": close_price * 1.02,
        "low": close_price * 0.98,
        "close": close_price,
        "volume": volume_data,
    })
    
    # Compute features
    df_features = compute_india_features(df_sample, symbol="TEST")
    print(f"\nComputed {len(df_features)} rows, {len(df_features.columns)} features")
    print(df_features.tail())
