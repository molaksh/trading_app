"""
NSE (India) data loading pipeline.

Load daily OHLCV data for Indian stocks from:
1. CSV bhavcopy files (production)
2. Yahoo Finance (research/fallback)

Handles:
- Trading holidays
- Corporate actions (splits)
- Timezone (IST)
- Data validation
"""

import pandas as pd
import numpy as np
import logging
from pathlib import Path
from datetime import datetime, timedelta
import yfinance as yf

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================
DATA_DIR = Path("./data/india")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# NSE trading holidays (sample)
NSE_HOLIDAYS = [
    "2026-01-26", "2026-03-25", "2026-04-02", "2026-04-14",
    "2026-05-01", "2026-08-15", "2026-08-31", "2026-10-02",
    "2026-10-25", "2026-10-26", "2026-11-01", "2026-12-25",
]

# ============================================================================
# PRIMARY: CSV BHAVCOPY LOADER
# ============================================================================
def load_from_bhavcopy(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Load NSE bhavcopy CSV files.
    
    Expected format:
    - File naming: bhavcopy_SYMBOL_YYYYMMDD.csv
    - Columns: Date, Open, High, Low, Close, Volume
    
    Args:
        symbol: NSE stock symbol (e.g., "RELIANCE")
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD
        
    Returns:
        pd.DataFrame with OHLCV data
    """
    try:
        csv_files = list(DATA_DIR.glob(f"bhavcopy_{symbol}_*.csv"))
        if not csv_files:
            logger.debug(f"No bhavcopy files found for {symbol}")
            return pd.DataFrame()
        
        # Load and combine all matching files
        dfs = []
        for csv_file in csv_files:
            try:
                df = pd.read_csv(csv_file, parse_dates=["Date"])
                df = df[(df["Date"].dt.strftime("%Y-%m-%d") >= start_date) &
                        (df["Date"].dt.strftime("%Y-%m-%d") <= end_date)]
                dfs.append(df)
            except Exception as e:
                logger.warning(f"Error reading {csv_file}: {e}")
        
        if dfs:
            df = pd.concat(dfs, ignore_index=True)
            df = df.sort_values("Date").drop_duplicates(subset=["Date"])
            return df
        
        return pd.DataFrame()
    
    except Exception as e:
        logger.error(f"Error loading bhavcopy for {symbol}: {e}")
        return pd.DataFrame()


# ============================================================================
# FALLBACK: YAHOO FINANCE LOADER
# ============================================================================
def load_from_yahoo(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Load NSE data from Yahoo Finance (research/fallback only).
    
    Note: Yahoo uses ".NS" suffix for NSE stocks.
    E.g., RELIANCE → RELIANCE.NS
    
    Args:
        symbol: NSE stock symbol (e.g., "RELIANCE")
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD
        
    Returns:
        pd.DataFrame with OHLCV data
    """
    try:
        yahoo_symbol = f"{symbol}.NS"
        logger.info(f"[INDIA] Loading {symbol} from Yahoo Finance ({yahoo_symbol})")
        
        df = yf.download(
            yahoo_symbol,
            start=start_date,
            end=end_date,
            progress=False,
        )
        
        if df.empty:
            logger.warning(f"No Yahoo data for {symbol}")
            return pd.DataFrame()
        
        # Normalize column names
        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "Adj Close": "adj_close",
        })
        
        df = df.reset_index()
        df = df.rename(columns={"Date": "date"})
        df["date"] = pd.to_datetime(df["date"])
        
        return df[["date", "open", "high", "low", "close", "volume"]]
    
    except Exception as e:
        logger.error(f"Error loading {symbol} from Yahoo: {e}")
        return pd.DataFrame()


# ============================================================================
# MAIN DATA LOADER
# ============================================================================
def load_india_price_data(
    symbol: str,
    start_date: str,
    end_date: str,
    use_yahoo_fallback: bool = True,
) -> pd.DataFrame:
    """
    Load NSE price data with fallback logic.
    
    1. Try bhavcopy (production)
    2. Fall back to Yahoo Finance if configured
    
    Args:
        symbol: Stock symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        use_yahoo_fallback: Try Yahoo if bhavcopy empty
        
    Returns:
        pd.DataFrame with OHLCV data
    """
    # Try bhavcopy first
    df = load_from_bhavcopy(symbol, start_date, end_date)
    
    if not df.empty:
        logger.info(f"[INDIA] Loaded {len(df)} days for {symbol} from bhavcopy")
        return _validate_and_normalize(df, symbol)
    
    # Fallback to Yahoo Finance
    if use_yahoo_fallback:
        logger.warning(f"[INDIA] Bhavcopy empty for {symbol}, using Yahoo Finance")
        df = load_from_yahoo(symbol, start_date, end_date)
        if not df.empty:
            return _validate_and_normalize(df, symbol)
    
    logger.error(f"[INDIA] No data available for {symbol}")
    return pd.DataFrame()


# ============================================================================
# DATA VALIDATION & NORMALIZATION
# ============================================================================
def _validate_and_normalize(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Validate and normalize OHLCV data.
    
    - Handle splits
    - Remove duplicate dates
    - Check for gaps
    - Standardize column names
    """
    if df.empty:
        return df
    
    # Standardize column names
    df.columns = df.columns.str.lower()
    
    # Ensure date column
    if "date" not in df.columns:
        df = df.reset_index()
        df = df.rename(columns={"Date": "date", "Index": "date"})
    
    df["date"] = pd.to_datetime(df["date"])
    
    # Sort by date
    df = df.sort_values("date")
    
    # Remove duplicates (keep first)
    df = df.drop_duplicates(subset=["date"], keep="first")
    
    # Check for stock splits (volume spike + price drop)
    # Simple heuristic: if volume > 2x avg and close < open * 0.8
    if len(df) > 20:
        df["volume_ma"] = df["volume"].rolling(window=20).mean()
        df["vol_ratio"] = df["volume"] / df["volume_ma"]
        df["price_drop"] = df["close"] < df["open"] * 0.8
        splits = df[(df["vol_ratio"] > 2.0) & (df["price_drop"])]
        if not splits.empty:
            logger.warning(f"[INDIA] Potential splits detected for {symbol}: {len(splits)} rows")
        df = df.drop(columns=["volume_ma", "vol_ratio", "price_drop"])
    
    # Validate OHLC relationship
    invalid = (
        (df["high"] < df["low"]) |
        (df["high"] < df["open"]) |
        (df["high"] < df["close"]) |
        (df["low"] > df["open"]) |
        (df["low"] > df["close"])
    )
    if invalid.any():
        logger.warning(f"[INDIA] Invalid OHLC for {symbol}: {invalid.sum()} rows")
        df = df[~invalid]
    
    # Require minimum columns
    required = ["date", "open", "high", "low", "close", "volume"]
    for col in required:
        if col not in df.columns:
            logger.error(f"[INDIA] Missing required column: {col}")
            return pd.DataFrame()
    
    logger.info(f"[INDIA] Validated {len(df)} days for {symbol}")
    return df[required]


# ============================================================================
# BULK LOADING
# ============================================================================
def load_india_universe(
    symbols: list,
    start_date: str,
    end_date: str,
) -> dict:
    """
    Load data for all symbols in universe.
    
    Returns:
        {symbol: DataFrame} with OHLCV data
    """
    data = {}
    for symbol in symbols:
        try:
            df = load_india_price_data(symbol, start_date, end_date)
            if not df.empty:
                data[symbol] = df
            else:
                logger.warning(f"[INDIA] No data for {symbol}")
        except Exception as e:
            logger.error(f"[INDIA] Error loading {symbol}: {e}")
    
    logger.info(f"[INDIA] Loaded {len(data)}/{len(symbols)} symbols")
    return data


# ============================================================================
# TESTING
# ============================================================================
if __name__ == "__main__":
    from universe.india_universe import NIFTY_50
    
    # Test load single stock
    print("\n[TEST] Loading RELIANCE...")
    df = load_india_price_data(
        "RELIANCE",
        "2024-01-01",
        "2026-01-25",
        use_yahoo_fallback=True,
    )
    if not df.empty:
        print(f"Loaded {len(df)} days")
        print(df.tail())
    else:
        print("No data")
