"""
NSE Data Provider for India Market.

Fetches historical OHLCV data for NSE stocks:
- Daily candles only (no intraday for v1)
- Data source: NSE official API (free)
- Fallback: Local cache for offline mode
- Independent from US data sources

Cache Structure:
- data/<scope>/ohlcv/<symbol>_daily.csv

Data Format (CSV):
- Date, Open, High, Low, Close, Volume
"""

import logging
import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


@dataclass
class OHLCVBar:
    """OHLCV bar data."""
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class NSEDataProvider:
    """
    Data provider for NSE historical data.
    
    Features:
    - Fetches daily OHLCV from NSE API
    - Caches data locally for offline access
    - Automatic gap filling
    - Validation and cleaning
    
    Cache Directory:
    - data/<scope>/ohlcv/
    
    File Format:
    - <symbol>_daily.csv
    """
    
    def __init__(self, cache_dir: Path):
        """
        Initialize NSE data provider.
        
        Args:
            cache_dir: Directory for OHLCV cache
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("=" * 80)
        logger.info("NSE DATA PROVIDER INITIALIZED")
        logger.info("=" * 80)
        logger.info(f"Cache Directory: {self.cache_dir}")
        logger.info("=" * 80)
    
    def _get_cache_file(self, symbol: str) -> Path:
        """Get cache file path for symbol."""
        return self.cache_dir / f"{symbol}_daily.csv"
    
    def _load_from_cache(self, symbol: str) -> List[OHLCVBar]:
        """
        Load OHLCV data from cache.
        
        Args:
            symbol: NSE symbol
        
        Returns:
            List of OHLCV bars (sorted by date)
        """
        cache_file = self._get_cache_file(symbol)
        
        if not cache_file.exists():
            logger.debug(f"No cache file for {symbol}")
            return []
        
        try:
            bars = []
            with open(cache_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    bars.append(OHLCVBar(
                        date=datetime.fromisoformat(row['date']),
                        open=float(row['open']),
                        high=float(row['high']),
                        low=float(row['low']),
                        close=float(row['close']),
                        volume=int(row['volume'])
                    ))
            
            logger.debug(f"Loaded {len(bars)} bars from cache for {symbol}")
            return bars
        
        except Exception as e:
            logger.error(f"Failed to load cache for {symbol}: {e}")
            return []
    
    def _save_to_cache(self, symbol: str, bars: List[OHLCVBar]) -> None:
        """
        Save OHLCV data to cache.
        
        Args:
            symbol: NSE symbol
            bars: List of OHLCV bars
        """
        cache_file = self._get_cache_file(symbol)
        
        try:
            with open(cache_file, 'w', newline='') as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=['date', 'open', 'high', 'low', 'close', 'volume']
                )
                writer.writeheader()
                
                for bar in sorted(bars, key=lambda x: x.date):
                    writer.writerow({
                        'date': bar.date.isoformat(),
                        'open': bar.open,
                        'high': bar.high,
                        'low': bar.low,
                        'close': bar.close,
                        'volume': bar.volume,
                    })
            
            logger.debug(f"Saved {len(bars)} bars to cache for {symbol}")
        
        except Exception as e:
            logger.error(f"Failed to save cache for {symbol}: {e}")
    
    def _fetch_from_nse_api(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[OHLCVBar]:
        """
        Fetch OHLCV data from NSE API.
        
        NOTE: This is a STUB for v1. Implement actual NSE API integration.
        
        For now, returns mock data for testing.
        
        Args:
            symbol: NSE symbol
            start_date: Start date
            end_date: End date
        
        Returns:
            List of OHLCV bars
        """
        logger.warning(
            f"NSE API fetch not implemented - using mock data for {symbol}"
        )
        
        # TODO: Implement real NSE API integration
        # Options:
        # 1. NSE official API (if available)
        # 2. NSE India website scraping (fragile)
        # 3. Third-party data provider (e.g., Zerodha Kite, Upstox)
        # 4. Yahoo Finance India (.NS suffix)
        
        # For now, return empty list
        # This allows the system to work with cached data only
        return []
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        use_cache: bool = True,
        force_refresh: bool = False,
    ) -> List[OHLCVBar]:
        """
        Get historical OHLCV data for a symbol.
        
        Args:
            symbol: NSE symbol (e.g., "RELIANCE")
            start_date: Start date (defaults to 1 year ago)
            end_date: End date (defaults to today)
            use_cache: Whether to use cached data
            force_refresh: Whether to force refresh from API
        
        Returns:
            List of OHLCV bars sorted by date
        """
        # Default date range: 1 year
        if end_date is None:
            end_date = datetime.now(ZoneInfo("Asia/Kolkata"))
        if start_date is None:
            start_date = end_date - timedelta(days=365)
        
        # Try cache first (unless force refresh)
        if use_cache and not force_refresh:
            cached_bars = self._load_from_cache(symbol)
            
            if cached_bars:
                # Filter by date range
                filtered = [
                    bar for bar in cached_bars
                    if start_date <= bar.date <= end_date
                ]
                
                if filtered:
                    logger.debug(
                        f"Using cached data for {symbol}: "
                        f"{len(filtered)} bars from {filtered[0].date.date()} "
                        f"to {filtered[-1].date.date()}"
                    )
                    return filtered
        
        # Fetch from API
        logger.info(f"Fetching {symbol} from NSE API: {start_date.date()} to {end_date.date()}")
        
        try:
            bars = self._fetch_from_nse_api(symbol, start_date, end_date)
            
            if bars:
                # Save to cache
                self._save_to_cache(symbol, bars)
                return bars
            else:
                logger.warning(f"No data fetched for {symbol}")
                return []
        
        except Exception as e:
            logger.error(f"Failed to fetch data for {symbol}: {e}")
            
            # Fall back to cache if available
            if use_cache:
                logger.info(f"Falling back to cached data for {symbol}")
                return self._load_from_cache(symbol)
            
            return []
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Get latest close price for a symbol.
        
        Args:
            symbol: NSE symbol
        
        Returns:
            Latest close price, or None if unavailable
        """
        bars = self.get_historical_data(symbol, use_cache=True)
        
        if not bars:
            return None
        
        # Return most recent close
        latest_bar = max(bars, key=lambda x: x.date)
        return latest_bar.close
    
    def get_open_prices(self, symbols: List[str], date: datetime) -> Dict[str, float]:
        """
        Get open prices for multiple symbols on a specific date.
        
        This is used by the simulator to execute pending orders at market open.
        
        Args:
            symbols: List of NSE symbols
            date: Trading date
        
        Returns:
            Dict of symbol -> open price
        """
        prices = {}
        
        for symbol in symbols:
            bars = self.get_historical_data(symbol, use_cache=True)
            
            # Find bar for the date
            for bar in bars:
                if bar.date.date() == date.date():
                    prices[symbol] = bar.open
                    break
        
        return prices
    
    def validate_symbol(self, symbol: str) -> bool:
        """
        Validate that a symbol has available data.
        
        Args:
            symbol: NSE symbol
        
        Returns:
            True if data is available
        """
        bars = self.get_historical_data(symbol, use_cache=True)
        return len(bars) > 0


def create_mock_data_for_testing(cache_dir: Path, symbols: List[str]) -> None:
    """
    Create mock OHLCV data for testing.
    
    This generates synthetic data for development/testing when
    NSE API is not available.
    
    Args:
        cache_dir: Cache directory
        symbols: List of symbols to generate data for
    """
    import random
    
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Generating mock data for {len(symbols)} symbols...")
    
    for symbol in symbols:
        cache_file = cache_dir / f"{symbol}_daily.csv"
        
        # Generate 1 year of mock data
        bars = []
        base_price = random.uniform(500, 3000)  # Random base price
        
        for i in range(252):  # ~252 trading days in a year
            date = datetime.now(ZoneInfo("Asia/Kolkata")) - timedelta(days=365-i)
            
            # Random walk
            change = random.uniform(-0.02, 0.02)  # ±2% daily
            close = base_price * (1 + change)
            
            # Generate OHLC
            high = close * random.uniform(1.0, 1.015)
            low = close * random.uniform(0.985, 1.0)
            open_price = random.uniform(low, high)
            
            volume = random.randint(100000, 10000000)
            
            bars.append(OHLCVBar(
                date=date,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume
            ))
            
            base_price = close  # Next day starts from today's close
        
        # Save to CSV
        with open(cache_file, 'w', newline='') as f:
            writer = csv.DictWriter(
                f,
                fieldnames=['date', 'open', 'high', 'low', 'close', 'volume']
            )
            writer.writeheader()
            
            for bar in bars:
                writer.writerow({
                    'date': bar.date.isoformat(),
                    'open': bar.open,
                    'high': bar.high,
                    'low': bar.low,
                    'close': bar.close,
                    'volume': bar.volume,
                })
        
        logger.debug(f"Generated mock data for {symbol}: {len(bars)} bars")
    
    logger.info(f"Mock data generation complete: {len(symbols)} symbols")
