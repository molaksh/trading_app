"""
Regime feature builder - uses 4h candles for market regime detection.

TIMEFRAME: 4 hour candles ONLY
PURPOSE: Detect market regime (RISK_ON, NEUTRAL, RISK_OFF, PANIC)
CONSUMER: CryptoRegimeEngine ONLY

CRITICAL: This must NEVER use 5m candles. Regime detection requires higher timeframe
to filter out noise and focus on structural market conditions.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RegimeFeatureContext:
    """
    Feature context for regime detection (4h candles).
    
    Contains macro market metrics for determining overall market regime.
    """
    symbol: str
    timestamp_utc: pd.Timestamp
    
    # Volatility metrics
    realized_volatility_20: float  # Rolling 20-period volatility (annualized)
    realized_volatility_50: float  # Rolling 50-period volatility (annualized)
    vol_percentile_100: float  # Current vol vs 100-period history (0..1)
    
    # Trend metrics
    trend_sma_slope_20: float  # SMA20 slope (% per period)
    trend_sma_slope_50: float  # SMA50 slope (% per period)
    price_vs_sma50_pct: float  # Distance from SMA50
    
    # Drawdown metrics
    drawdown_pct: float  # Current drawdown from recent peak
    drawdown_duration: int  # Periods in drawdown
    max_drawdown_100: float  # Max drawdown over 100 periods
    
    # Dispersion (optional, for multi-asset regimes)
    correlation_btc_eth: float  # Cross-asset correlation
    
    # Metadata
    candle_count: int
    timeframe: str = "4h"


def build_regime_features(
    symbol: str,
    bars_4h: pd.DataFrame,
    lookback_periods: int = 100,
    correlation_symbols: Dict[str, pd.DataFrame] = None,
) -> RegimeFeatureContext:
    """
    Build regime features from 4h candles.
    
    Args:
        symbol: Trading symbol
        bars_4h: DataFrame with OHLCV data, 4h timeframe
        lookback_periods: Number of periods for rolling calculations
        correlation_symbols: Optional dict of other symbols' 4h bars for correlation
    
    Returns:
        RegimeFeatureContext with computed regime metrics
    """
    if bars_4h.empty or len(bars_4h) < lookback_periods:
        raise ValueError(f"Insufficient 4h data for {symbol}: need {lookback_periods}, got {len(bars_4h)}")
    
    df = bars_4h.copy()
    
    # Ensure sorted by time
    if 'timestamp' in df.columns:
        df = df.sort_values('timestamp')
    else:
        df = df.sort_index()
    
    # Log returns
    df['log_return'] = np.log(df['Close'] / df['Close'].shift(1))
    
    # Realized volatility (rolling std of log returns, annualized)
    # 4h candles: 6 candles/day, sqrt(6*365) ≈ 46.9 for annualization
    annualization_factor = np.sqrt(6 * 365)
    df['vol_20'] = df['log_return'].rolling(window=20, min_periods=20).std() * annualization_factor
    df['vol_50'] = df['log_return'].rolling(window=50, min_periods=50).std() * annualization_factor
    
    # Volatility percentile (current vol vs 100-period history)
    df['vol_rank'] = df['vol_20'].rolling(window=100, min_periods=100).apply(
        lambda x: (x[-1] - x.min()) / (x.max() - x.min()) if x.max() > x.min() else 0.5,
        raw=True
    )
    
    # Trend: SMA slopes
    df['sma_20'] = df['Close'].rolling(window=20, min_periods=20).mean()
    df['sma_50'] = df['Close'].rolling(window=50, min_periods=50).mean()
    
    # SMA slope = % change per period
    df['sma20_slope'] = df['sma_20'].pct_change(periods=5) * 100  # % per 5 periods
    df['sma50_slope'] = df['sma_50'].pct_change(periods=10) * 100  # % per 10 periods
    
    # Price vs SMA50
    df['price_vs_sma50'] = ((df['Close'] - df['sma_50']) / df['sma_50'] * 100)
    
    # Drawdown calculation
    df['cummax'] = df['Close'].cummax()
    df['drawdown'] = (df['Close'] - df['cummax']) / df['cummax'] * 100  # Negative values
    
    # Drawdown duration (consecutive periods in drawdown)
    df['in_drawdown'] = df['drawdown'] < 0
    df['dd_streak'] = df.groupby((df['in_drawdown'] != df['in_drawdown'].shift()).cumsum())['in_drawdown'].cumsum()
    
    # Max drawdown over lookback
    df['max_dd_100'] = df['drawdown'].rolling(window=100, min_periods=100).min()
    
    # Correlation with other assets (optional)
    correlation = 0.0
    if correlation_symbols and 'ETH' in correlation_symbols:
        try:
            eth_bars = correlation_symbols['ETH']
            if len(eth_bars) >= len(df):
                # Align timestamps
                btc_returns = df['log_return'].iloc[-50:]
                eth_returns = eth_bars['log_return'].iloc[-50:] if 'log_return' in eth_bars.columns else eth_bars['Close'].pct_change().iloc[-50:]
                if len(btc_returns) == len(eth_returns):
                    correlation = btc_returns.corr(eth_returns)
        except Exception as e:
            logger.warning(f"Could not compute BTC-ETH correlation: {e}")
            correlation = 0.0
    
    # Get latest values
    latest = df.iloc[-1]
    
    return RegimeFeatureContext(
        symbol=symbol,
        timestamp_utc=latest.name if isinstance(latest.name, pd.Timestamp) else pd.Timestamp(latest['timestamp'], tz='UTC'),
        realized_volatility_20=float(latest['vol_20']) if pd.notna(latest['vol_20']) else 0.0,
        realized_volatility_50=float(latest['vol_50']) if pd.notna(latest['vol_50']) else 0.0,
        vol_percentile_100=float(latest['vol_rank']) if pd.notna(latest['vol_rank']) else 0.5,
        trend_sma_slope_20=float(latest['sma20_slope']) if pd.notna(latest['sma20_slope']) else 0.0,
        trend_sma_slope_50=float(latest['sma50_slope']) if pd.notna(latest['sma50_slope']) else 0.0,
        price_vs_sma50_pct=float(latest['price_vs_sma50']) if pd.notna(latest['price_vs_sma50']) else 0.0,
        drawdown_pct=float(latest['drawdown']) if pd.notna(latest['drawdown']) else 0.0,
        drawdown_duration=int(latest['dd_streak']) if pd.notna(latest['dd_streak']) else 0,
        max_drawdown_100=float(latest['max_dd_100']) if pd.notna(latest['max_dd_100']) else 0.0,
        correlation_btc_eth=float(correlation),
        candle_count=len(df),
        timeframe="4h",
    )
