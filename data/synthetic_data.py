"""
Synthetic test data generator for demo and testing.
Creates realistic OHLCV data without network dependencies.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def generate_synthetic_ohlcv(
    symbol: str,
    num_days: int = 252,
    start_price: float = 100.0,
    trend: float = 0.0005,
    volatility: float = 0.02
) -> pd.DataFrame:
    """
    Generate realistic synthetic OHLCV data for testing.
    
    Parameters
    ----------
    symbol : str
        Ticker symbol (for reference only)
    num_days : int
        Number of trading days to generate
    start_price : float
        Starting close price
    trend : float
        Daily trend (drift) in returns
    volatility : float
        Daily volatility (std dev of returns)
    
    Returns
    -------
    pd.DataFrame
        DataFrame with OHLCV data indexed by date
    """
    np.random.seed(hash(symbol) % 2**32)  # Reproducible per symbol
    
    # Generate dates (trading days)
    dates = pd.date_range(
        end=datetime.now(),
        periods=num_days,
        freq='B'  # Business days
    )
    
    # Generate daily returns
    returns = np.random.normal(trend, volatility, num_days)
    
    # Build price series from returns
    prices = [start_price]
    for r in returns[1:]:
        prices.append(prices[-1] * (1 + r))
    
    prices = np.array(prices)
    
    # Generate OHLC from close prices
    data = []
    for i, (date, close) in enumerate(zip(dates, prices)):
        # Intraday moves
        open_price = close * (1 + np.random.uniform(-0.005, 0.005))
        high = max(open_price, close) * (1 + np.random.uniform(0, 0.01))
        low = min(open_price, close) * (1 - np.random.uniform(0, 0.01))
        
        # Volume: average 1M shares, with noise
        base_volume = 1_000_000
        volume = int(base_volume * np.random.uniform(0.7, 1.3))
        
        data.append({
            'Open': open_price,
            'High': high,
            'Low': low,
            'Close': close,
            'Volume': volume
        })
    
    df = pd.DataFrame(data, index=dates)
    df.index.name = 'Date'
    return df


def generate_multiple_symbols(symbols: list, num_days: int = 252) -> dict:
    """
    Generate synthetic data for multiple symbols.
    
    Parameters
    ----------
    symbols : list
        List of ticker symbols
    num_days : int
        Number of trading days
    
    Returns
    -------
    dict
        Dictionary mapping symbol -> DataFrame
    """
    data = {}
    for symbol in symbols:
        # Vary parameters per symbol for realism
        trend = np.random.uniform(-0.0005, 0.0015)
        vol = np.random.uniform(0.015, 0.035)
        start_price = np.random.uniform(50, 300)
        
        data[symbol] = generate_synthetic_ohlcv(
            symbol,
            num_days=num_days,
            trend=trend,
            volatility=vol,
            start_price=start_price
        )
    
    return data
