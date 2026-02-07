"""Kraken market data provider (REST OHLC)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import urlopen, Request

import pandas as pd

from config.scope import Scope
from config.scope_paths import ScopePathResolver
from crypto.universe import CryptoUniverse
from runtime.observability import get_observability

logger = logging.getLogger(__name__)


@dataclass
class KrakenOHLCConfig:
    base_url: str = "https://api.kraken.com"
    interval: str = "1d"  # 1m/5m/15m/1h/4h/1d
    enable_ws: bool = False
    cache_enabled: bool = True
    max_staleness_seconds: Optional[int] = None


class KrakenMarketDataProvider:
    """Fetches OHLCV from Kraken REST API for crypto scopes."""

    _INTERVAL_MAP = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
    }

    def __init__(self, scope: Scope, config: KrakenOHLCConfig):
        self.scope = scope
        self.config = config
        self.scope_paths = ScopePathResolver(scope)
        self.universe = CryptoUniverse()

        if config.enable_ws:
            logger.warning("ENABLE_WS_MARKETDATA=true but WS feed not implemented; using REST only")

        logger.info(
            "crypto_market_data_provider initialized provider=KRAKEN interval=%s cache=%s",
            config.interval,
            config.cache_enabled,
        )

    def _interval_minutes(self) -> int:
        interval = self.config.interval.lower()
        if interval not in self._INTERVAL_MAP:
            raise ValueError(f"Unsupported Kraken OHLC interval: {interval}")
        return self._INTERVAL_MAP[interval]

    def _cache_path(self, canonical_symbol: str) -> Path:
        cache_dir = self.scope_paths.get_dataset_dir() / "ohlcv"
        cache_dir.mkdir(parents=True, exist_ok=True)
        interval = self.config.interval.lower()
        return cache_dir / f"{canonical_symbol}_{interval}.csv"

    def _max_staleness_seconds(self, interval_minutes: int) -> int:
        if self.config.max_staleness_seconds is None:
            if self.scope.env.lower() == "live":
                return 0
            return interval_minutes * 60 * 2
        try:
            return max(int(self.config.max_staleness_seconds), 0)
        except Exception:
            return 0

    def _is_cache_fresh(self, df: pd.DataFrame, interval_minutes: int) -> bool:
        if df is None or df.empty:
            return False
        last_ts = df.index.max()
        if last_ts is None:
            return False
        if getattr(last_ts, "tzinfo", None) is None:
            last_ts = last_ts.tz_localize(timezone.utc)
        now = datetime.now(timezone.utc)
        age_seconds = max(0.0, (now - last_ts).total_seconds())
        interval_seconds = interval_minutes * 60
        max_staleness_seconds = self._max_staleness_seconds(interval_minutes)
        allowed_age_seconds = interval_seconds + max_staleness_seconds
        return age_seconds <= allowed_age_seconds

    def _load_from_cache(self, canonical_symbol: str) -> Optional[pd.DataFrame]:
        if not self.config.cache_enabled:
            return None
        path = self._cache_path(canonical_symbol)
        if not path.exists():
            return None
        try:
            df = pd.read_csv(path)
            if df.empty:
                return None
            df["Date"] = pd.to_datetime(df["Date"], utc=True)
            df = df.set_index("Date").sort_index()
            logger.info("crypto_market_data cache_hit symbol=%s path=%s", canonical_symbol, path)
            return df
        except Exception as e:
            logger.warning("crypto_market_data cache_read_failed symbol=%s error=%s", canonical_symbol, e)
            return None

    def _save_to_cache(self, canonical_symbol: str, df: pd.DataFrame) -> None:
        if not self.config.cache_enabled:
            return
        path = self._cache_path(canonical_symbol)
        try:
            df_to_save = df.reset_index()
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            df_to_save.to_csv(tmp_path, index=False)
            tmp_path.replace(path)
            logger.info("crypto_market_data cache_write symbol=%s path=%s", canonical_symbol, path)
        except Exception as e:
            logger.warning("crypto_market_data cache_write_failed symbol=%s error=%s", canonical_symbol, e)

    def fetch_ohlcv(self, canonical_symbol: str, lookback_days: int) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data for a canonical symbol from Kraken REST.
        """
        # Validate symbol and get Kraken pair
        kraken_pair = self.universe.get_kraken_pair(canonical_symbol)

        interval = self._interval_minutes()
        cached = self._load_from_cache(canonical_symbol)
        required_rows = max(1, lookback_days)
        log_event = "OHLC_API_FETCH"
        fetch_reason = "cache_missing_or_insufficient"
        if not self.config.cache_enabled:
            fetch_reason = "cache_disabled"
        if cached is not None and len(cached) >= required_rows:
            if self._is_cache_fresh(cached, interval):
                logger.info(
                    "OHLC_CACHE_HIT_FRESH symbol=%s interval=%s rows=%s",
                    canonical_symbol,
                    self.config.interval,
                    len(cached),
                )
                return cached.tail(lookback_days)
            logger.warning(
                "OHLC_CACHE_STALE symbol=%s interval=%s last_ts=%s",
                canonical_symbol,
                self.config.interval,
                cached.index.max(),
            )
            get_observability().mark_market_data_stale()
            log_event = "OHLC_CACHE_STALE_REFRESH"
            fetch_reason = "stale_cache"
        params = {
            "pair": kraken_pair,
            "interval": interval,
        }
        url = f"{self.config.base_url}/0/public/OHLC?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": "trading_app/kraken-provider"})

        if log_event == "OHLC_CACHE_STALE_REFRESH":
            logger.info(
                "OHLC_CACHE_STALE_REFRESH symbol=%s interval=%s reason=%s url=%s",
                canonical_symbol,
                self.config.interval,
                fetch_reason,
                url,
            )
        else:
            logger.info(
                "OHLC_API_FETCH symbol=%s interval=%s reason=%s url=%s",
                canonical_symbol,
                self.config.interval,
                fetch_reason,
                url,
            )

        try:
            with urlopen(request, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error("crypto_market_data fetch_failed pair=%s error=%s", kraken_pair, e)
            if self.scope.env.lower() == "live":
                logger.error(
                    "MARKET_DATA_BLOCKED symbol=%s interval=%s reason=fetch_failed",
                    canonical_symbol,
                    self.config.interval,
                )
            return None

        if payload.get("error"):
            logger.error("crypto_market_data api_error pair=%s error=%s", kraken_pair, payload.get("error"))
            if self.scope.env.lower() == "live":
                logger.error(
                    "MARKET_DATA_BLOCKED symbol=%s interval=%s reason=api_error",
                    canonical_symbol,
                    self.config.interval,
                )
            return None

        result = payload.get("result", {})
        ohlc_key = None
        for key in result.keys():
            if key != "last":
                ohlc_key = key
                break

        if not ohlc_key:
            logger.error("crypto_market_data missing_ohlc_key pair=%s", kraken_pair)
            if self.scope.env.lower() == "live":
                logger.error(
                    "MARKET_DATA_BLOCKED symbol=%s interval=%s reason=missing_ohlc_key",
                    canonical_symbol,
                    self.config.interval,
                )
            return None

        rows = result.get(ohlc_key, [])
        if not rows:
            logger.warning("crypto_market_data empty_response pair=%s", kraken_pair)
            if self.scope.env.lower() == "live":
                logger.error(
                    "MARKET_DATA_BLOCKED symbol=%s interval=%s reason=empty_response",
                    canonical_symbol,
                    self.config.interval,
                )
            return None

        # Kraken OHLC row: [time, open, high, low, close, vwap, volume, count]
        data = []
        for row in rows:
            try:
                ts = datetime.fromtimestamp(int(row[0]), tz=timezone.utc)
                data.append(
                    {
                        "Date": ts,
                        "Open": float(row[1]),
                        "High": float(row[2]),
                        "Low": float(row[3]),
                        "Close": float(row[4]),
                        "Volume": float(row[6]),
                    }
                )
            except Exception:
                continue

        df = pd.DataFrame(data)
        if df.empty:
            if self.scope.env.lower() == "live":
                logger.error(
                    "MARKET_DATA_BLOCKED symbol=%s interval=%s reason=empty_dataframe",
                    canonical_symbol,
                    self.config.interval,
                )
            return None

        df = df.set_index("Date").sort_index()

        if len(df) > lookback_days:
            df = df.iloc[-lookback_days:]

        self._save_to_cache(canonical_symbol, df)
        return df
