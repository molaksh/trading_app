"""
Broker adapter factory for Phase 0.

Enables broker selection via configuration (SCOPE) only.
No hardcoded broker dependencies in core.

Supported brokers:
  - alpaca: Alpaca Markets (US, paper & live)
  - nse_simulator: NSE Simulated Broker (India, paper only)
  - ibkr: Interactive Brokers (US/intl, multi-mode)
  - zerodha: Zerodha (India)
  - crypto: Generic crypto exchange
"""

import logging
from typing import Optional

from broker.adapter import BrokerAdapter
from config.scope import Scope, get_scope
from config.scope_paths import get_scope_path

logger = logging.getLogger(__name__)


def get_broker_adapter(scope: Optional[Scope] = None) -> BrokerAdapter:
    """
    Factory: create broker adapter based on scope.
    
    Args:
        scope: Optional Scope; defaults to global scope
    
    Returns:
        BrokerAdapter instance
    
    Raises:
        ValueError: If broker not supported
    """
    if scope is None:
        scope = get_scope()
    
    broker_name = scope.broker.lower()
    
    logger.info(f"Creating broker adapter: {broker_name}")
    
    if broker_name == "alpaca":
        from broker.alpaca_adapter import AlpacaAdapter
        return AlpacaAdapter()
    
    elif broker_name == "nse_simulator":
        from broker.nse_simulator_adapter import NSESimulatedBrokerAdapter
        # Get state directory from scope paths
        state_dir = get_scope_path(scope, "state")
        return NSESimulatedBrokerAdapter(state_dir=state_dir)
    
    elif broker_name == "ibkr":
        from broker.ibkr_adapter import IBKRAdapter
        return IBKRAdapter(paper_mode=(scope.env == "paper"))
    
    elif broker_name == "zerodha":
        from broker.zerodha_adapter import ZerodhaAdapter
        return ZerodhaAdapter(paper_mode=(scope.env == "paper"))
    
    elif broker_name == "crypto":
        from broker.crypto_adapter import CryptoAdapter
        return CryptoAdapter(paper_mode=(scope.env == "paper"))
    
    else:
        raise ValueError(
            f"Unsupported broker: {broker_name}. "
            f"Supported: alpaca, ibkr, zerodha, crypto"
        )
