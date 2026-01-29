"""
NSEProvider - Real NSE daily OHLCV ingestion (no credentials).

Uses official NSE public endpoints with cookie bootstrap:
- Bootstrap: https://www.nseindia.com
- Historical: https://www.nseindia.com/api/historical/cm/equity

Features:
- Daily candles only
- Cookie + header handling
- Retry with backoff
- Aggressive persistent caching per symbol
- Scope-isolated storage under <PERSISTENCE_ROOT>/<scope>/data/ohlcv/
"""

import json
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Iterable
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError, URLError
from http.cookiejar import CookieJar
import gzip
import zlib
import io

from config.scope import get_scope, Scope
from config.scope_paths import get_scope_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NSEBar:
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class NSEProvider:
    """
    Real NSE daily OHLCV provider (no credentials).

    - Bootstrap cookies from nseindia.com
    - Fetch historical data from NSE official endpoint
    - Cache per symbol in scope-isolated storage
    """

    BASE_URL = "https://www.nseindia.com"
    HISTORICAL_URL = "https://www.nseindia.com/api/historical/cm/equity"

    def __init__(
        self,
        scope: Optional[Scope] = None,
        cache_root: Optional[Path] = None,
        timeout: int = 15,
        max_retries: int = 3,
        backoff_base: float = 1.5,
    ) -> None:
        self.scope = scope or get_scope()
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base

        # Resolve cache root: <PERSISTENCE_ROOT>/<scope>/data/ohlcv/
        if cache_root is None:
            scope_dir = get_scope_path(self.scope, "logs").parent
            cache_root = scope_dir / "data" / "ohlcv"

        self.cache_root = cache_root
        self.cache_root.mkdir(parents=True, exist_ok=True)

        self._cookie_jar = CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self._cookie_jar))
        self._bootstrapped = False

        logger.info("NSEProvider initialized")
        logger.info(f"  scope={self.scope}")
        logger.info(f"  cache_root={self.cache_root}")

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def get_daily_ohlcv(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[NSEBar]:
        """
        Fetch daily OHLCV for symbol between start_date and end_date.

        Uses cache first and only fetches missing dates.
        """
        symbol = self._normalize_symbol(symbol)
        start_date = self._normalize_date(start_date)
        end_date = self._normalize_date(end_date)

        cached = self._load_cache(symbol)
        cached_map = {b.date.date(): b for b in cached}

        missing_dates = [
            d for d in self._iter_trading_days(start_date, end_date)
            if d.date() not in cached_map
        ]

        if not missing_dates:
            logger.info(f"market=india provider=nse symbol={symbol} cache_hit=true cache_miss=false")
            return self._filter_range(cached, start_date, end_date)

        logger.info(
            f"market=india provider=nse symbol={symbol} cache_hit=false cache_miss=true "
            f"missing_dates={len(missing_dates)}"
        )

        fetch_start = min(missing_dates)
        fetch_end = max(missing_dates)

        try:
            fetched = self._fetch_from_nse(symbol, fetch_start, fetch_end)
        except Exception as e:
            if cached:
                logger.warning(
                    f"NSE fetch failed for {symbol}; using cached data only: {e}"
                )
                return self._filter_range(cached, start_date, end_date)
            raise RuntimeError(f"NSE fetch failed and no cache available for {symbol}: {e}") from e

        if not fetched:
            if cached:
                logger.warning(
                    f"NSE returned empty data for {symbol}; using cached data only"
                )
                return self._filter_range(cached, start_date, end_date)
            raise RuntimeError(f"NSE returned empty data for {symbol}")

        # Merge and persist
        merged = {b.date.date(): b for b in cached}
        for bar in fetched:
            merged[bar.date.date()] = bar

        merged_list = sorted(merged.values(), key=lambda b: b.date)
        self._save_cache(symbol, merged_list)

        return self._filter_range(merged_list, start_date, end_date)

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _normalize_symbol(self, symbol: str) -> str:
        s = symbol.strip().upper()
        if s.endswith(".NS"):
            s = s[:-3]
        return s

    def _normalize_date(self, dt: datetime) -> datetime:
        if dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt

    def _cache_file(self, symbol: str) -> Path:
        return self.cache_root / f"{symbol}.json"

    def _load_cache(self, symbol: str) -> List[NSEBar]:
        cache_file = self._cache_file(symbol)
        if not cache_file.exists():
            return []
        try:
            raw = json.loads(cache_file.read_text())
            bars = []
            for row in raw:
                bars.append(NSEBar(
                    date=datetime.fromisoformat(row["date"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                ))
            return bars
        except Exception as e:
            logger.warning(f"Failed to load cache for {symbol}: {e}")
            return []

    def _save_cache(self, symbol: str, bars: List[NSEBar]) -> None:
        cache_file = self._cache_file(symbol)
        payload = [
            {
                "date": b.date.date().isoformat(),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ]
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(payload, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save cache for {symbol}: {e}")

    def _filter_range(self, bars: List[NSEBar], start_date: datetime, end_date: datetime) -> List[NSEBar]:
        return [
            b for b in bars
            if start_date.date() <= b.date.date() <= end_date.date()
        ]

    def _iter_trading_days(self, start_date: datetime, end_date: datetime) -> Iterable[datetime]:
        current = start_date.date()
        end = end_date.date()
        while current <= end:
            if current.weekday() < 5:
                yield datetime.combine(current, datetime.min.time())
            current += timedelta(days=1)

    def _bootstrap_session(self) -> None:
        if self._bootstrapped:
            return
        headers = self._bootstrap_headers()
        req = Request(self.BASE_URL, headers=headers)
        self._open_request(req, "bootstrap")
        self._bootstrapped = True
        logger.info("NSE cookie bootstrap successful")

    def _fetch_from_nse(self, symbol: str, start_date: datetime, end_date: datetime) -> List[NSEBar]:
        self._bootstrap_session()

        params = {
            "symbol": symbol,
            "series": json.dumps(["EQ"]),
            "from": start_date.strftime("%d-%m-%Y"),
            "to": end_date.strftime("%d-%m-%Y"),
        }
        url = f"{self.HISTORICAL_URL}?{urlencode(params)}"

        for attempt in range(1, self.max_retries + 1):
            try:
                headers = self._default_headers(symbol=symbol)
                req = Request(url, headers=headers)
                payload = self._open_request(req, f"historical attempt={attempt}")
                data = json.loads(payload)
                rows = data.get("data", [])
                bars = self._parse_rows(rows)
                if not bars:
                    logger.warning(f"NSE returned 0 bars for {symbol} from {start_date.date()} to {end_date.date()}")
                else:
                    logger.info(
                        f"market=india provider=nse symbol={symbol} fetched={len(bars)} "
                        f"range={start_date.date()}..{end_date.date()}"
                    )
                return bars
            except (HTTPError, URLError) as e:
                # Re-bootstrap on access issues
                if isinstance(e, HTTPError) and e.code in (401, 403, 429):
                    logger.warning(f"NSE access blocked (HTTP {e.code}). Rebootstrapping session.")
                    self._bootstrapped = False
                    self._bootstrap_session()
            except Exception as e:
                if attempt >= self.max_retries:
                    raise
                backoff = self.backoff_base ** attempt + random.uniform(0, 0.25)
                logger.warning(f"NSE fetch failed (attempt {attempt}): {e}. Retrying in {backoff:.2f}s")
                time.sleep(backoff)
        return []

    def _parse_rows(self, rows: List[Dict]) -> List[NSEBar]:
        bars: List[NSEBar] = []
        for row in rows:
            try:
                date_raw = row.get("CH_TIMESTAMP") or row.get("DATE")
                dt = self._parse_date(date_raw)
                if not dt:
                    continue

                open_px = float(row.get("CH_OPENING_PRICE") or row.get("OPEN") or 0)
                high_px = float(row.get("CH_TRADE_HIGH_PRICE") or row.get("HIGH") or 0)
                low_px = float(row.get("CH_TRADE_LOW_PRICE") or row.get("LOW") or 0)
                close_px = float(row.get("CH_CLOSING_PRICE") or row.get("CLOSE") or 0)
                vol = int(float(row.get("CH_TOT_TRADED_QTY") or row.get("VOLUME") or 0))

                if not (open_px and high_px and low_px and close_px):
                    continue

                bars.append(NSEBar(
                    date=dt,
                    open=open_px,
                    high=high_px,
                    low=low_px,
                    close=close_px,
                    volume=vol,
                ))
            except Exception:
                continue
        return bars

    def _parse_date(self, raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt)
            except Exception:
                continue
        return None

    def _default_headers(self, symbol: Optional[str] = None) -> Dict[str, str]:
        referer = self.BASE_URL + "/"
        if symbol:
            referer = f"{self.BASE_URL}/get-quotes/equity?symbol={symbol}"
        return {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            "sec-ch-ua": "\"Not A(Brand\";v=\"99\", \"Google Chrome\";v=\"121\", \"Chromium\";v=\"121\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"macOS\"",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Referer": referer,
            "Origin": self.BASE_URL,
            "X-Requested-With": "XMLHttpRequest",
            "DNT": "1",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }

    def _bootstrap_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1",
        }

    def _open_request(self, req: Request, context: str) -> str:
        with self._opener.open(req, timeout=self.timeout) as resp:
            raw = resp.read()
            encoding = resp.headers.get("Content-Encoding", "")
            if encoding == "gzip":
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            elif encoding == "deflate":
                raw = zlib.decompress(raw)
            return raw.decode("utf-8")
