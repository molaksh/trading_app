"""
Execution feature builder - uses 5m candles for strategy signals.

TIMEFRAME: 5 minute candles ONLY
PURPOSE: Generate trading signals, entry/exit logic
CONSUMERS: All crypto strategies (trend, mean reversion, volatility, etc.)
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ExecutionFeatureContext:
    """
    Feature context for strategy execution (5m candles).
    
    Contains technical indicators and metrics for generating trade signals.
    """
    symbol: str
    timestamp_utc: pd.Timestamp
    
    # Price action
    close: float
    high_20: float
    low_20: float
    
    # Trend indicators
    sma_20: float
    sma_50: float
    sma_200: float
    trend_strength: float  # 0..1, based on MA alignment
    momentum: float  # Recent price momentum
    
    # Volatility
    atr: float
    atr_pct: float
    bb_width: float  # Bollinger band width
    
    # Volume
    volume_ratio: float  # Current vs average
    
    # Mean reversion metrics
    distance_from_sma20_pct: float
    rsi_14: float
    
    # Metadata
    candle_count: int
    timeframe: str = "5m"


def build_execution_features(
    symbol: str,
    bars_5m: pd.DataFrame,
    lookback_periods: int = 200,
) -> ExecutionFeatureContext:
    """
    Build execution features from 5m candles.
    
    Args:
        symbol: Trading symbol
        bars_5m: DataFrame with OHLCV data, 5m timeframe
        lookback_periods: Number of periods for moving averages
    
    Returns:
        ExecutionFeatureContext with computed features
    """
    if bars_5m.empty or len(bars_5m) < lookback_periods:
        raise ValueError(f"Insufficient 5m data for {symbol}: need {lookback_periods}, got {len(bars_5m)}")
    
    df = bars_5m.copy()
    
    # Ensure sorted by time
    if 'timestamp' in df.columns:
        df = df.sort_values('timestamp')
    else:
        df = df.sort_index()
    
    # Moving averages
    df['sma_20'] = df['Close'].rolling(window=20, min_periods=20).mean()
    df['sma_50'] = df['Close'].rolling(window=50, min_periods=50).mean()
    df['sma_200'] = df['Close'].rolling(window=200, min_periods=200).mean()
    
    # ATR (5m)
    df['high_low'] = df['High'] - df['Low']
    df['high_close'] = abs(df['High'] - df['Close'].shift(1))
    df['low_close'] = abs(df['Low'] - df['Close'].shift(1))
    df['true_range'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
    df['atr'] = df['true_range'].rolling(window=14, min_periods=14).mean()
    
    # Bollinger Bands
    df['bb_middle'] = df['Close'].rolling(window=20).mean()
    df['bb_std'] = df['Close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_middle'] + (2 * df['bb_std'])
    df['bb_lower'] = df['bb_middle'] - (2 * df['bb_std'])
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
    
    # RSI
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi_14'] = 100 - (100 / (1 + rs))
    
    # Volume ratio
    df['volume_ma'] = df['Volume'].rolling(window=20, min_periods=20).mean()
    df['volume_ratio'] = df['Volume'] / df['volume_ma'].replace(0, np.nan)
    
    # Momentum (rate of change over 10 periods)
    df['momentum'] = df['Close'].pct_change(periods=10)
    
    # Trend strength (based on MA alignment)
    # 1.0 = perfect uptrend (close > sma20 > sma50 > sma200)
    # 0.0 = neutral/mixed
    # -1.0 = perfect downtrend
    df['ma_align_score'] = 0.0
    close = df['Close'].iloc[-1]
    sma20 = df['sma_20'].iloc[-1]
    sma50 = df['sma_50'].iloc[-1]
    sma200 = df['sma_200'].iloc[-1]
    
    if pd.notna([sma20, sma50, sma200]).all():
        if close > sma20 > sma50 > sma200:
            trend_strength = 1.0
        elif close < sma20 < sma50 < sma200:
            trend_strength = -1.0
        elif close > sma20 and sma20 > sma50:
            trend_strength = 0.6
        elif close < sma20 and sma20 < sma50:
            trend_strength = -0.6
        else:
            trend_strength = 0.0
    else:
        trend_strength = 0.0
    
    # Get latest values
    latest = df.iloc[-1]
    
    # Distance from SMA20
    distance_pct = ((latest['Close'] - latest['sma_20']) / latest['sma_20'] * 100) if pd.notna(latest['sma_20']) and latest['sma_20'] > 0 else 0.0
    
    # High/Low over 20 periods
    high_20 = df['High'].iloc[-20:].max()
    low_20 = df['Low'].iloc[-20:].min()
    
    return ExecutionFeatureContext(
        symbol=symbol,
        timestamp_utc=latest.name if isinstance(latest.name, pd.Timestamp) else pd.Timestamp(latest['timestamp'], tz='UTC'),
        close=float(latest['Close']),
        high_20=float(high_20),
        low_20=float(low_20),
        sma_20=float(latest['sma_20']) if pd.notna(latest['sma_20']) else 0.0,
        sma_50=float(latest['sma_50']) if pd.notna(latest['sma_50']) else 0.0,
        sma_200=float(latest['sma_200']) if pd.notna(latest['sma_200']) else 0.0,
        trend_strength=float(trend_strength),
        momentum=float(latest['momentum']) if pd.notna(latest['momentum']) else 0.0,
        atr=float(latest['atr']) if pd.notna(latest['atr']) else 0.0,
        atr_pct=float(latest['atr'] / latest['Close'] * 100) if pd.notna(latest['atr']) and latest['Close'] > 0 else 0.0,
        bb_width=float(latest['bb_width']) if pd.notna(latest['bb_width']) else 0.0,
        volume_ratio=float(latest['volume_ratio']) if pd.notna(latest['volume_ratio']) else 1.0,
        distance_from_sma20_pct=float(distance_pct),
        rsi_14=float(latest['rsi_14']) if pd.notna(latest['rsi_14']) else 50.0,
        candle_count=len(df),
        timeframe="5m",
    )
