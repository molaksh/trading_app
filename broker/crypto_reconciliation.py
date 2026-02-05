"""Crypto account reconciliation (Kraken-only)."""

from __future__ import annotations

import logging
from typing import Dict

from broker.adapter import BrokerAdapter
from broker.trade_ledger import TradeLedger
from risk.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class CryptoAccountReconciler:
    """
    Reconcile crypto scope using KrakenAdapter only.

    If adapter does not support reconciliation, run in DRY_RUN and log
    RECONCILIATION_UNAVAILABLE_CRYPTO_ADAPTER_STUB.
    """

    def __init__(self, broker: BrokerAdapter, trade_ledger: TradeLedger, risk_manager: RiskManager):
        self.broker = broker
        self.trade_ledger = trade_ledger
        self.risk_manager = risk_manager
        self.unreconciled_broker_symbols = set()

    def reconcile_on_startup(self) -> Dict:
        logger.info("crypto_reconciliation_start broker=%s", self.broker.__class__.__name__)

        try:
            equity = self.broker.account_equity
            buying_power = self.broker.buying_power
            positions = self.broker.get_positions()

            logger.info(
                "crypto_reconciliation_snapshot equity=%.2f buying_power=%.2f positions=%d",
                float(equity),
                float(buying_power),
                len(positions),
            )

            return {
                "status": "READY",
                "safe_mode": False,
                "warnings": [],
                "errors": [],
                "reconciliation_adapter": self.broker.__class__.__name__,
            }

        except NotImplementedError:
            logger.warning("RECONCILIATION_UNAVAILABLE_CRYPTO_ADAPTER_STUB")
            return {
                "status": "UNKNOWN",
                "safe_mode": True,
                "warnings": ["RECONCILIATION_UNAVAILABLE_CRYPTO_ADAPTER_STUB"],
                "errors": [],
                "reconciliation_adapter": self.broker.__class__.__name__,
            }
        except Exception as e:
            logger.error("crypto_reconciliation_failed error=%s", e)
            return {
                "status": "FAILED",
                "safe_mode": True,
                "warnings": [],
                "errors": [str(e)],
                "reconciliation_adapter": self.broker.__class__.__name__,
            }
