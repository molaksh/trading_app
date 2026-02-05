"""Crypto scope guardrails to prevent equity contamination."""

from __future__ import annotations

import logging
from typing import Iterable, List, Dict, Any

from config.scope import Scope
from config.scope_paths import ScopePathResolver
from crypto.universe import CryptoUniverse
from config.crypto.loader import load_crypto_config

logger = logging.getLogger(__name__)


def _is_crypto_scope(scope: Scope) -> bool:
    return scope.mode.lower() == "crypto" or scope.broker.lower() == "kraken"


def validate_crypto_universe_symbols(symbols: Iterable[str]) -> List[str]:
    universe = CryptoUniverse(symbols=list(symbols))
    return universe.all_canonical_symbols()


def enforce_crypto_scope_guard(
    scope: Scope,
    broker: object,
    scope_paths: ScopePathResolver,
) -> Dict[str, Any]:
    """
    Validate crypto scope invariants and fail fast on contamination.

    Returns a summary dict for logging/testing.
    """
    if not _is_crypto_scope(scope):
        return {
            "scope": str(scope),
            "guard_applied": False,
        }

    crypto_config = load_crypto_config(scope)
    provider = str(crypto_config.get("MARKET_DATA_PROVIDER", "")).upper()
    universe_symbols = crypto_config.get("CRYPTO_UNIVERSE", ["BTC", "ETH", "SOL"])

    # 1) Ensure provider is Kraken
    if provider != "KRAKEN":
        raise ValueError(
            f"CRYPTO_SCOPE_INVALID_MARKET_DATA_PROVIDER: expected=KRAKEN got={provider}"
        )

    # 2) Ensure symbols are crypto-only
    try:
        canonical = validate_crypto_universe_symbols(universe_symbols)
    except Exception as e:
        raise ValueError(f"CRYPTO_SCOPE_INVALID_UNIVERSE: {e}") from e

    # 3) Ensure no Alpaca broker instantiated
    broker_name = broker.__class__.__name__
    if "Alpaca" in broker_name:
        raise ValueError(
            f"CRYPTO_SCOPE_BROKER_CONTAMINATION: alpaca_adapter_detected={broker_name}"
        )

    # 4) Ensure crypto-only artifact roots (scope contains crypto)
    if "crypto" not in str(scope).lower():
        raise ValueError(f"CRYPTO_SCOPE_INVALID_SCOPE_STRING: {scope}")

    summary = {
        "scope": str(scope),
        "guard_applied": True,
        "market_data_provider": provider,
        "crypto_universe": canonical,
        "broker_adapter": broker_name,
        "scope_paths": scope_paths.get_scope_summary(),
    }

    logger.info(
        "crypto_scope_guard passed provider=%s symbols=%s broker=%s",
        provider,
        canonical,
        broker_name,
    )

    return summary
