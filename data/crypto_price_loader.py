"""Crypto price loader using Kraken market data provider."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from config.scope import get_scope
from config.crypto.loader import load_crypto_config
from core.data.providers.kraken_provider import KrakenMarketDataProvider, KrakenOHLCConfig
from crypto.scope_guard import validate_crypto_universe_symbols

logger = logging.getLogger(__name__)


def load_crypto_price_data(symbol: str, lookback_days: int) -> Optional[pd.DataFrame]:
    scope = get_scope()
    crypto_config = load_crypto_config(scope)

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

    config = KrakenOHLCConfig(
        interval=str(crypto_config.get("KRAKEN_OHLC_INTERVAL", "1d")),
        enable_ws=bool(crypto_config.get("ENABLE_WS_MARKETDATA", False)),
        cache_enabled=True,
    )

    provider = KrakenMarketDataProvider(scope=scope, config=config)
    return provider.fetch_ohlcv(symbol, lookback_days)
