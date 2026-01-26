"""
Price data loader using yfinance (US) and india_price_loader (India).
Handles OHLCV data fetching, validation, and error recovery.
"""

import logging
from typing import Optional
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import warnings

# Suppress yfinance warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)


def load_price_data(symbol: str, lookback_days: int) -> Optional[pd.DataFrame]:
    """
    Load daily OHLCV data for a symbol using appropriate data source.
    Automatically detects India (.NS suffix) vs US symbols.
    
    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g., 'AAPL' for US, 'RELIANCE.NS' for India)
    lookback_days : int
        Number of trading days to fetch (typically 252 for 1 year)
    
    Returns
    -------
    pd.DataFrame or None
        Clean DataFrame with columns [Open, High, Low, Close, Volume]
        indexed by date. Returns None if fetch fails or data insufficient.
    """
    # Route to appropriate loader based on symbol
    if '.NS' in symbol:
        # India NSE symbol
        from data.india_price_loader import load_price_data_india
        return load_price_data_india(symbol, lookback_days)
    else:
        # US symbol - use yfinance
        return _load_us_price_data(symbol, lookback_days)


def _load_us_price_data(symbol: str, lookback_days: int) -> Optional[pd.DataFrame]:
    """Load US stock data using yfinance."""
    try:
        # Calculate end date as today and start date as lookback_days ago
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days * 1.5)  # Buffer for weekends/holidays
        
        logger.debug(f"Fetching {symbol} from {start_date.date()} to {end_date.date()}")
        
        # Download OHLCV data
        df = yf.download(
            symbol,
            start=start_date,
            end=end_date,
            interval='1d',
            progress=False
        )
        
        # Handle case where yfinance returns empty or Series
        if df is None or df.empty:
            logger.warning(f"No data returned for {symbol}")
            return None
        
        if isinstance(df, pd.Series):
            logger.warning(f"Single-row data for {symbol}, insufficient history")
            return None
        
        # Ensure we have standard column names
        df.columns = ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
        
        # Drop Adj Close (use Close instead)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        
        # Remove any rows with NaN values
        df = df.dropna()
        
        if len(df) == 0:
            logger.warning(f"All rows were NaN for {symbol}")
            return None
        
        # Keep only the last lookback_days rows
        if len(df) > lookback_days:
            df = df.iloc[-lookback_days:]
        
        logger.debug(f"Successfully loaded {len(df)} days for {symbol}")
        return df
    
    except Exception as e:
        logger.warning(f"Error loading data for {symbol}: {type(e).__name__}: {e}")
        return None
