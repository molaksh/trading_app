"""Crypto price loader using Kraken market data provider."""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import pandas as pd

from config.scope import get_scope
from config.crypto.loader import load_crypto_config
from core.data.providers.kraken_provider import KrakenMarketDataProvider, KrakenOHLCConfig
from crypto.scope_guard import validate_crypto_universe_symbols
from runtime.trade_permission import get_trade_permission

logger = logging.getLogger(__name__)


def load_crypto_price_data(symbol: str, lookback_days: int) -> Optional[pd.DataFrame]:
    scope = get_scope()
    crypto_config = load_crypto_config(scope)
    permission = get_trade_permission()

    provider_name = str(crypto_config.get("MARKET_DATA_PROVIDER", "")).upper()
    if provider_name != "KRAKEN":
        raise ValueError(
            f"CRYPTO_SCOPE_INVALID_MARKET_DATA_PROVIDER: expected=KRAKEN got={provider_name}"
        )

    universe_symbols = crypto_config.get("CRYPTO_UNIVERSE", ["BTC", "ETH", "SOL"])
    canonical = validate_crypto_universe_symbols(universe_symbols)
    if symbol not in canonical:
        raise ValueError(
            f"CRYPTO_SCOPE_SYMBOL_NOT_ALLOWED: symbol={symbol} allowed={canonical}"
        )

    enable_cache = bool(crypto_config.get("ENABLE_OHLC_CACHE", True))
    max_staleness = crypto_config.get("MAX_OHLC_STALENESS_SECONDS", None)
    if isinstance(max_staleness, str) and max_staleness.strip().lower() == "auto":
        max_staleness = None
    config = KrakenOHLCConfig(
        interval=str(crypto_config.get("KRAKEN_OHLC_INTERVAL", "1d")),
        enable_ws=bool(crypto_config.get("ENABLE_WS_MARKETDATA", False)),
        cache_enabled=enable_cache,
        max_staleness_seconds=max_staleness,
    )

    provider = KrakenMarketDataProvider(scope=scope, config=config)
    df = provider.fetch_ohlcv(symbol, lookback_days)
    if scope.env.lower() == "live":
        if df is None or df.empty:
            permission.set_block(
                "MARKET_DATA_BLOCKED",
                f"OHLC unavailable symbol={symbol} interval={config.interval}",
            )
        else:
            permission.clear_block(
                "MARKET_DATA_BLOCKED",
                f"OHLC fresh symbol={symbol} interval={config.interval}",
            )
    return df


def load_crypto_price_data_interval(
    symbol: str,
    lookback_bars: int,
    interval: str,
) -> Optional[pd.DataFrame]:
    """
    Load crypto OHLCV data for a specific interval.

    Args:
        symbol: Canonical symbol (BTC, ETH, etc.)
        lookback_bars: Number of bars to fetch
        interval: Interval string ("5m", "1h", "4h", "1d")
    """
    scope = get_scope()
    crypto_config = load_crypto_config(scope)
    permission = get_trade_permission()

    provider_name = str(crypto_config.get("MARKET_DATA_PROVIDER", "")).upper()
    if provider_name != "KRAKEN":
        raise ValueError(
            f"CRYPTO_SCOPE_INVALID_MARKET_DATA_PROVIDER: expected=KRAKEN got={provider_name}"
        )

    universe_symbols = crypto_config.get("CRYPTO_UNIVERSE", ["BTC", "ETH", "SOL"])
    canonical = validate_crypto_universe_symbols(universe_symbols)
    if symbol not in canonical:
        raise ValueError(
            f"CRYPTO_SCOPE_SYMBOL_NOT_ALLOWED: symbol={symbol} allowed={canonical}"
        )

    enable_cache = bool(crypto_config.get("ENABLE_OHLC_CACHE", True))
    max_staleness = crypto_config.get("MAX_OHLC_STALENESS_SECONDS", None)
    if isinstance(max_staleness, str) and max_staleness.strip().lower() == "auto":
        max_staleness = None
    config = KrakenOHLCConfig(
        interval=str(interval),
        enable_ws=bool(crypto_config.get("ENABLE_WS_MARKETDATA", False)),
        cache_enabled=enable_cache,
        max_staleness_seconds=max_staleness,
    )
    provider = KrakenMarketDataProvider(scope=scope, config=config)
    df = provider.fetch_ohlcv(symbol, lookback_bars)
    if scope.env.lower() == "live":
        if df is None or df.empty:
            permission.set_block(
                "MARKET_DATA_BLOCKED",
                f"OHLC unavailable symbol={symbol} interval={interval}",
            )
        else:
            permission.clear_block(
                "MARKET_DATA_BLOCKED",
                f"OHLC fresh symbol={symbol} interval={interval}",
            )
    return df


def load_crypto_price_data_two_timeframes(
    symbol: str,
    execution_lookback_bars: int,
    regime_lookback_bars: int,
    execution_interval: str = "5m",
    regime_interval: str = "4h",
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Load OHLCV for both execution and regime timeframes.

    Returns:
        (bars_5m, bars_4h)
    """
    # Execution timeframe (5m)
    bars_execution = load_crypto_price_data_interval(
        symbol=symbol,
        lookback_bars=execution_lookback_bars,
        interval=execution_interval,
    )

    # Regime timeframe (4h) with fallback resampling if needed
    bars_regime = load_crypto_price_data_interval(
        symbol=symbol,
        lookback_bars=regime_lookback_bars,
        interval=regime_interval,
    )

    if bars_regime is None or bars_regime.empty:
        # Fallback: resample from 1h or 5m
        fallback = load_crypto_price_data_interval(
            symbol=symbol,
            lookback_bars=regime_lookback_bars * 4,
            interval="1h",
        )
        if fallback is None or fallback.empty:
            fallback = load_crypto_price_data_interval(
                symbol=symbol,
                lookback_bars=regime_lookback_bars * 48,
                interval="5m",
            )
        if fallback is not None and not fallback.empty:
            bars_regime = _resample_to_4h(fallback)

    return bars_execution, bars_regime


def _resample_to_4h(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resample OHLCV to 4h candles deterministically.
    """
    if df is None or df.empty:
        return df

    resampled = df.resample("4H", label="right", closed="right").agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    )
    resampled = resampled.dropna()
    return resampled
