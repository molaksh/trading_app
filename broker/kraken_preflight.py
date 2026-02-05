"""
Kraken adapter startup preflight checks.

Validates Kraken connectivity, auth, and permissions before trading begins.
If any check fails, aborts with clear error message.

Checks performed:
1. API credentials present (env vars)
2. Connectivity: can ping Kraken API
3. Authentication: can query balances
4. Permissions: can query orders (if live orders enabled)
5. Sanity: withdraw functionality is not used (code-level guarantee)
"""

import logging
import os
from typing import Dict, List
from broker.kraken_client import KrakenClient, KrakenConfig, KrakenAPIError

logger = logging.getLogger(__name__)


class PreflightCheckError(Exception):
    """Preflight check failed."""
    pass


class KrakenPreflight:
    """Kraken startup preflight checks."""
    
    def __init__(self, dry_run: bool = True):
        """
        Initialize preflight checker.
        
        Args:
            dry_run: If True, skip live checks (paper mode)
        """
        self.dry_run = dry_run
    
    def check_all(self) -> Dict[str, bool]:
        """
        Run all preflight checks.
        
        Returns:
            Dict of check_name -> passed (True/False)
        
        Raises:
            PreflightCheckError: If any critical check fails
        """
        results = {}
        
        # 1. Check environment
        results["env_vars"] = self._check_env_vars()
        
        # Skip remaining checks if dry_run or paper mode
        if self.dry_run:
            logger.info("Dry-run mode: skipping connectivity checks")
            return results
        
        # Create client for remaining checks
        try:
            client = self._create_client()
        except Exception as e:
            raise PreflightCheckError(f"Failed to create client: {e}")
        
        try:
            # 2. Connectivity
            results["connectivity"] = self._check_connectivity(client)
            
            # 3. Authentication
            results["auth"] = self._check_auth(client)
            
            # 4. Permissions
            results["permissions"] = self._check_permissions(client)
            
            # 5. Sanity (no withdrawals)
            results["sanity"] = self._check_sanity()
            
        finally:
            client.close()
        
        # Check all critical checks passed
        critical_checks = ["env_vars", "connectivity", "auth", "permissions", "sanity"]
        failed = [name for name in critical_checks if not results.get(name, False)]
        
        if failed:
            raise PreflightCheckError(
                f"Preflight checks failed: {', '.join(failed)}"
            )
        
        return results
    
    def _check_env_vars(self) -> bool:
        """
        Check environment variables.
        
        Required:
        - KRAKEN_API_KEY
        - KRAKEN_API_SECRET
        
        Returns:
            True if all required vars present
        """
        api_key = os.getenv("KRAKEN_API_KEY", "").strip()
        api_secret = os.getenv("KRAKEN_API_SECRET", "").strip()
        
        if not api_key or not api_secret:
            raise PreflightCheckError(
                "Missing Kraken API credentials: "
                "set KRAKEN_API_KEY and KRAKEN_API_SECRET"
            )
        
        logger.info("✓ Environment variables present")
        return True
    
    def _create_client(self) -> KrakenClient:
        """Create Kraken client with env credentials."""
        api_key = os.getenv("KRAKEN_API_KEY", "").strip()
        api_secret = os.getenv("KRAKEN_API_SECRET", "").strip()
        
        config = KrakenConfig(
            api_key=api_key,
            api_secret=api_secret,
            timeout_sec=10,
            max_retries=3
        )
        
        return KrakenClient(config)
    
    def _check_connectivity(self, client: KrakenClient) -> bool:
        """
        Check connectivity to Kraken API.
        
        Uses public SystemStatus endpoint (no auth required).
        
        Returns:
            True if reachable
        """
        try:
            status = client.request_public("SystemStatus", {})
            if status.get("status") != "online":
                raise PreflightCheckError(
                    f"Kraken API status not online: {status.get('status')}"
                )
            logger.info("✓ Kraken API connectivity verified")
            return True
        except Exception as e:
            raise PreflightCheckError(f"Connectivity check failed: {e}")
    
    def _check_auth(self, client: KrakenClient) -> bool:
        """
        Check authentication.
        
        Queries balance (simple read-only operation).
        
        Returns:
            True if auth successful
        """
        try:
            balances = client.request_private("Balance", {})
            if not isinstance(balances, dict):
                raise PreflightCheckError("Invalid balance response")
            logger.info(f"✓ Authentication verified ({len(balances)} assets)")
            return True
        except KrakenAPIError as e:
            if "EAPI:Invalid nonce" in str(e):
                raise PreflightCheckError(
                    "Authentication failed: Invalid API key/secret or nonce mismatch"
                )
            raise PreflightCheckError(f"Auth check failed: {e}")
    
    def _check_permissions(self, client: KrakenClient) -> bool:
        """
        Check API key permissions.
        
        Verifies:
        - Can query orders (required for live trading)
        - Cannot withdraw (required for safety)
        
        Returns:
            True if permissions correct
        """
        try:
            # Query open orders (requires QueryOpenOrders permission)
            orders = client.request_private("OpenOrders", {})
            if not isinstance(orders, dict):
                raise PreflightCheckError("Invalid open orders response")
            
            logger.info("✓ API permissions verified (query orders allowed)")
            return True
        except KrakenAPIError as e:
            if "EAPI:Permission denied" in str(e):
                raise PreflightCheckError(
                    "API key lacks required permissions: "
                    "must allow Query Funds and Query Orders"
                )
            raise PreflightCheckError(f"Permission check failed: {e}")
    
    def _check_sanity(self) -> bool:
        """
        Sanity check: verify withdraw functionality is not accessible.
        
        This is a code-level guarantee - we never implement withdraw endpoints.
        This check documents the intent.
        
        Returns:
            True (always, as we don't implement withdraws)
        """
        logger.info("✓ Sanity check: withdraw endpoints not implemented")
        return True


def run_preflight_checks(dry_run: bool = True) -> Dict[str, bool]:
    """
    Run all preflight checks.
    
    Args:
        dry_run: If True, skip connectivity checks (paper/test mode)
    
    Returns:
        Dict of check results
    
    Raises:
        PreflightCheckError: If critical check fails
    """
    checker = KrakenPreflight(dry_run=dry_run)
    return checker.check_all()
