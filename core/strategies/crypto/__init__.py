"""
Crypto trading strategies for Kraken global markets.
"""

from core.strategies.crypto.crypto_momentum import CryptoMomentumStrategy
from core.strategies.crypto.crypto_trend import CryptoTrendStrategy

__all__ = [
    "CryptoMomentumStrategy",
    "CryptoTrendStrategy",
]
