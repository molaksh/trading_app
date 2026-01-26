"""
Price data loader with Alpaca-first data, yfinance fallback.
Handles OHLCV data fetching, validation, and error recovery.
"""

import logging
import os
from typing import Optional
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone
import warnings

# Suppress yfinance warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)


def _load_from_alpaca(symbol: str, lookback_days: int) -> Optional[pd.DataFrame]:
    """Load daily bars from Alpaca Data API if credentials are present."""
    api_key = os.getenv("APCA_API_KEY_ID")
    secret_key = os.getenv("APCA_API_SECRET_KEY")

    if not api_key or not secret_key:
        return None

    try:
        from alpaca.data.historical.stock import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        from alpaca.data.enums import DataFeed, Adjustment
    except Exception as e:
        logger.debug(f"Alpaca data client unavailable: {e}")
        return None

    try:
        client = StockHistoricalDataClient(api_key, secret_key)

        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=int(lookback_days * 1.6))

        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start_dt,
            end=end_dt,
            limit=lookback_days * 2,
            adjustment=Adjustment.RAW,
            feed=DataFeed.IEX,
        )

        bars = client.get_stock_bars(req)
        df = bars.df if hasattr(bars, "df") else None

        if df is None or df.empty:
            logger.debug(f"Alpaca returned no data for {symbol}")
            return None

        # Drop symbol level if multi-index
        if isinstance(df.index, pd.MultiIndex):
            try:
                df = df.xs(symbol, level="symbol")
            except Exception:
                return None

        df = df.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        })

        df = df[["Open", "High", "Low", "Close", "Volume"]].sort_index()
        df = df.dropna()

        if len(df) > lookback_days:
            df = df.iloc[-lookback_days:]

        logger.debug(f"Successfully loaded {len(df)} days for {symbol} via Alpaca")
        return df
    except Exception as e:
        logger.warning(f"Alpaca data error for {symbol}: {type(e).__name__}: {e}")
        return None


def load_price_data(symbol: str, lookback_days: int) -> Optional[pd.DataFrame]:
    """
    Load daily OHLCV data for a symbol.
    Preference order: Alpaca Data API (if credentials set), else yfinance.
    
    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g., 'AAPL')
    lookback_days : int
        Number of trading days to fetch (typically 252 for 1 year)
    
    Returns
    -------
    pd.DataFrame or None
        Clean DataFrame with columns [Open, High, Low, Close, Volume]
        indexed by date. Returns None if fetch fails or data insufficient.
    """
    # 1) Try Alpaca first
    alpaca_df = _load_from_alpaca(symbol, lookback_days)
    if alpaca_df is not None and not alpaca_df.empty:
        return alpaca_df

    # 2) Fallback to yfinance
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days * 1.5)  # Buffer for weekends/holidays

        logger.debug(f"Fetching {symbol} from {start_date.date()} to {end_date.date()} via yfinance")

        df = yf.download(
            symbol,
            start=start_date,
            end=end_date,
            interval='1d',
            progress=False
        )

        if df is None or df.empty:
            logger.warning(f"No data returned for {symbol}")
            return None

        if isinstance(df, pd.Series):
            logger.warning(f"Single-row data for {symbol}, insufficient history")
            return None

        df.columns = ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        df = df.dropna()

        if len(df) == 0:
            logger.warning(f"All rows were NaN for {symbol}")
            return None

        if len(df) > lookback_days:
            df = df.iloc[-lookback_days:]

        logger.debug(f"Successfully loaded {len(df)} days for {symbol} via yfinance")
        return df

    except Exception as e:
        logger.warning(f"Error loading data for {symbol}: {type(e).__name__}: {e}")
        return None
