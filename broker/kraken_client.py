"""
Kraken REST API HTTP client.

Handles:
- Request signing
- Rate limiting with exponential backoff + jitter
- Response parsing and error handling
- Timeout enforcement
- Connection pooling
"""

import logging
import time
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from broker.kraken_signing import KrakenSigner

logger = logging.getLogger(__name__)


@dataclass
class KrakenConfig:
    """Configuration for Kraken client."""
    base_url: str = "https://api.kraken.com"
    api_key: str = ""
    api_secret: str = ""
    timeout_sec: int = 10
    max_retries: int = 3
    backoff_factor: float = 0.5  # 0.5s, 1s, 2s
    max_requests_per_sec: float = 3.0  # Kraken rate limit: 15-20 per 15sec
    enable_ws: bool = False


class KrakenClient:
    """Production-grade Kraken REST client."""
    
    def __init__(self, config: KrakenConfig):
        """
        Initialize Kraken client.
        
        Args:
            config: KrakenConfig with API credentials and settings
        
        Raises:
            ValueError: If config is invalid
        """
        if not config.api_key or not config.api_secret:
            raise ValueError("API key and secret required")
        
        self.config = config
        self.signer = KrakenSigner(config.api_secret)
        self._session = self._create_session()
        self._last_request_time = 0.0
        self._request_count = 0
        
        logger.info(
            f"KrakenClient initialized: "
            f"url={config.base_url}, "
            f"timeout={config.timeout_sec}s, "
            f"max_retries={config.max_retries}"
        )
    
    def _create_session(self) -> requests.Session:
        """Create requests session with connection pooling and retries."""
        session = requests.Session()
        
        # Connection pooling
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=Retry(
                total=self.config.max_retries,
                backoff_factor=self.config.backoff_factor,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET", "POST"]
            )
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        return session
    
    def ping(self) -> bool:
        """
        Check connectivity (public endpoint).
        
        Returns:
            True if Kraken is reachable
        """
        try:
            response = self.request_public("SystemStatus", {})
            return response.get("status") == "online"
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return False
    
    def request_public(
        self,
        endpoint: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Make public API request (no authentication).
        
        Args:
            endpoint: API endpoint name (e.g., "SystemStatus")
            params: Request parameters
        
        Returns:
            Parsed JSON response
        
        Raises:
            KrakenAPIError: If API returns error
            RequestException: If network/timeout error
        """
        url = f"{self.config.base_url}/0/public/{endpoint}"
        
        self._apply_rate_limit()
        
        logger.debug(f"GET {endpoint}")
        
        response = self._session.get(
            url,
            params=params,
            timeout=self.config.timeout_sec
        )
        
        return self._parse_response(response, endpoint)
    
    def request_private(
        self,
        endpoint: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Make private API request (requires authentication).
        
        Args:
            endpoint: API endpoint name (e.g., "Balance")
            params: Request parameters
        
        Returns:
            Parsed JSON response
        
        Raises:
            KrakenAPIError: If API returns error (including auth failures)
            RequestException: If network/timeout error
        """
        urlpath = f"/0/private/{endpoint}"
        url = f"{self.config.base_url}{urlpath}"
        
        # Sign request
        signed = self.signer.sign_request(urlpath, params)
        postdata = signed["postdata"]
        nonce = signed["nonce"]
        api_sign = signed["API-Sign"]
        
        headers = {
            "API-Key": self.config.api_key,
            "API-Sign": api_sign
        }
        
        self._apply_rate_limit()
        
        logger.debug(f"POST {endpoint} (nonce={nonce})")
        
        response = self._session.post(
            url,
            data=postdata,
            headers=headers,
            timeout=self.config.timeout_sec
        )
        
        return self._parse_response(response, endpoint)
    
    def _apply_rate_limit(self) -> None:
        """Apply client-side rate limiting (exponential backoff + jitter)."""
        now = time.time()
        time_since_last = now - self._last_request_time
        min_interval = 1.0 / self.config.max_requests_per_sec
        
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            # Add jitter (±10%)
            jitter = sleep_time * 0.1 * (2 * (time.time() % 1) - 1)
            sleep_time += jitter
            
            if sleep_time > 0:
                logger.debug(f"Rate limit: sleeping {sleep_time:.3f}s")
                time.sleep(max(0, sleep_time))
        
        self._last_request_time = time.time()
    
    def _parse_response(
        self,
        response: requests.Response,
        endpoint: str
    ) -> Dict[str, Any]:
        """
        Parse Kraken JSON response.
        
        Kraken format:
        {
            "error": [...],  // List of errors (empty if success)
            "result": {...}  // Result data
        }
        
        Args:
            response: requests.Response object
            endpoint: Endpoint name (for logging)
        
        Returns:
            Result dict (if success) or raises exception
        
        Raises:
            KrakenAPIError: If API returned error
            HTTPError: If HTTP status error
            JSONDecodeError: If response not valid JSON
        """
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse {endpoint} response: {e}")
            logger.debug(f"Response body: {response.text[:500]}")
            raise KrakenAPIError(f"Invalid JSON response: {e}")
        
        # Check HTTP status
        response.raise_for_status()
        
        # Check Kraken-specific errors
        errors = data.get("error", [])
        if errors:
            error_msg = "; ".join(errors)
            logger.error(f"Kraken API error in {endpoint}: {error_msg}")
            raise KrakenAPIError(error_msg)
        
        result = data.get("result", {})
        logger.debug(f"{endpoint} success: {type(result).__name__}")
        
        return result
    
    def close(self) -> None:
        """Close HTTP session."""
        self._session.close()
        logger.info("KrakenClient session closed")


class KrakenAPIError(Exception):
    """Kraken API error."""
    pass
