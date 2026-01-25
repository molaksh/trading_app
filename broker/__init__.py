"""
Broker integration module for paper trading.

Provides abstract broker adapter interface and concrete implementations.
Isolates broker-specific code behind adapter pattern.

Currently supported:
- Alpaca (paper trading)

All adapters:
- Support market orders at open only
- Provide order status polling
- Enable position queries
- Are fully tested and validated
"""

from broker.adapter import BrokerAdapter, OrderStatus, OrderResult
from broker.alpaca_adapter import AlpacaAdapter

__all__ = [
    'BrokerAdapter',
    'OrderStatus',
    'OrderResult',
    'AlpacaAdapter',
]
