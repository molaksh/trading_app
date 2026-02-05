"""
Kraken API request signing.

Implements HMAC-SHA512 signing per Kraken specification:
- Request nonce (typically current timestamp in milliseconds)
- API-Sign header: HMAC-SHA512(urlpath + SHA256(nonce + postdata), base64_api_secret)
- Deterministic for testing with fixed nonce
"""

import hashlib
import hmac
import base64
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class KrakenSigner:
    """Deterministic request signer for Kraken API."""
    
    def __init__(self, api_secret: str):
        """
        Initialize signer with API secret.
        
        Args:
            api_secret: Base64-encoded Kraken API secret
        """
        if not api_secret:
            raise ValueError("API secret required")
        self.api_secret = api_secret
    
    @staticmethod
    def get_nonce() -> str:
        """
        Get current nonce (milliseconds since epoch).
        
        Returns:
            Nonce as string
        """
        import time
        return str(int(time.time() * 1000))
    
    def sign_request(
        self,
        urlpath: str,
        data: Dict[str, Any],
        nonce: str = None
    ) -> Dict[str, str]:
        """
        Sign a request and return API headers.
        
        Args:
            urlpath: API endpoint path (e.g., "/0/private/AddOrder")
            data: Request parameters
            nonce: Optional nonce for deterministic testing; auto-generated if None
        
        Returns:
            Dict with "API-Sign" header and updated data with nonce
            
        Raises:
            ValueError: If inputs are invalid
        """
        if not urlpath:
            raise ValueError("urlpath required")
        if not isinstance(data, dict):
            raise ValueError("data must be dict")
        
        # Use provided nonce or generate new one
        if nonce is None:
            nonce = self.get_nonce()
        
        # Add nonce to data
        data = dict(data)  # Copy to avoid modifying caller's dict
        data["nonce"] = nonce
        
        # Create postdata string (URL-encoded)
        postdata = "&".join(
            f"{k}={v}" for k, v in sorted(data.items())
        )
        
        # Compute signature
        signature = self._compute_signature(
            urlpath,
            postdata,
            nonce
        )
        
        return {
            "API-Sign": signature,
            "postdata": postdata,
            "nonce": nonce
        }
    
    def _compute_signature(
        self,
        urlpath: str,
        postdata: str,
        nonce: str
    ) -> str:
        """
        Compute HMAC-SHA512 signature per Kraken spec.
        
        Signature = HMAC-SHA512(
            urlpath + SHA256(nonce + postdata),
            base64_decode(api_secret)
        )
        
        Args:
            urlpath: API endpoint
            postdata: URL-encoded post body
            nonce: Request nonce
        
        Returns:
            Base64-encoded signature
        """
        # Compute SHA256 of nonce + postdata
        message = nonce.encode() + postdata.encode()
        sha256_hash = hashlib.sha256(message).digest()
        
        # Compute HMAC-SHA512 of urlpath + sha256_hash
        secret_decoded = base64.b64decode(self.api_secret)
        hmac_input = urlpath.encode() + sha256_hash
        signature = hmac.new(
            secret_decoded,
            hmac_input,
            hashlib.sha512
        ).digest()
        
        # Return base64-encoded signature
        return base64.b64encode(signature).decode()


def verify_signature(
    signature: str,
    urlpath: str,
    postdata: str,
    nonce: str,
    api_secret: str
) -> bool:
    """
    Verify a signature (for testing/audit).
    
    Args:
        signature: Base64-encoded signature to verify
        urlpath: API endpoint path
        postdata: URL-encoded post body
        nonce: Request nonce
        api_secret: Base64-encoded API secret
    
    Returns:
        True if signature matches
    """
    try:
        signer = KrakenSigner(api_secret)
        expected = signer._compute_signature(urlpath, postdata, nonce)
        return signature == expected
    except Exception as e:
        logger.error(f"Signature verification failed: {e}")
        return False
